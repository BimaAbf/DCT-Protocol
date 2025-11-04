import socket
import struct
import time
import sys
import random
from ConsoleColor import console
from constants import *


class Client:

    def __init__(self, server_host: str, server_port: int, mac: str, interval: float, duration: float,
                 seed: int = None):

        self.server_host = server_host
        self.server_port = (server_host, server_port)
        self.mac_str = mac
        self.interval = interval
        self.duration = duration

        if seed is not None:
            console.log.yellow(f"Using random seed: {seed}")
            random.seed(seed)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(5.0)
        self.device_id = None
        self.last_seq_num = 0
        self.base_time = 0
        self.current_value = 500
        self.running = False

    def _parse_mac(self, mac_str: str) -> bytes:
        try:
            return bytes.fromhex(mac_str.replace(":", ""))
        except (ValueError, TypeError):
            console.log.red(f"[FATAL] Invalid MAC address format: {mac_str}")
            console.log.yellow("Expected format: AA:BB:CC:DD:EE:FF")
            sys.exit(1)

    def _pack_header(self, msg_type: int, payload_len: int) -> bytes:

        device_id = 0 if msg_type == MSG_STARTUP else self.device_id

        offset = 0
        if self.base_time != 0:
            offset = int(time.time() - self.base_time)
            if not -32768 <= offset <= 32767:
                offset = 0

        ver_msgtype = (PROTOCOL_VERSION << 4) | msg_type
        flags = 0

        return struct.pack(
            HEADER_FORMAT,
            ver_msgtype,
            device_id,
            flags,
            self.last_seq_num,
            offset,
            payload_len
        )

    def _send_packet(self, msg_type: int, payload: bytes):
        try:
            header = self._pack_header(msg_type, len(payload))
            self.sock.sendto(header + payload, self.server_port)
            self.last_seq_num = (self.last_seq_num + 1) % 65536
        except socket.error as e:
            console.log.red(f"[Socket Error] Could not send packet: {e}")
            self.running = False

    def connect(self) -> bool:

        console.log.yellow(f"Sending STARTUP to {self.server_host}:{self.server_port[1]}...")
        mac_bytes = self._parse_mac(self.mac_str)

        self._send_packet(MSG_STARTUP, mac_bytes)

        try:
            data, _ = self.sock.recvfrom(MAX_PACKET_SIZE)

            header_data = data[:HEADER_SIZE]
            payload_data = data[HEADER_SIZE:]
            (ver_msgtype, _, _, _, _, payload_len) = struct.unpack(HEADER_FORMAT, header_data)

            msg_type = ver_msgtype & 0x0F

            if msg_type == MSG_STARTUP_ACK and len(payload_data) == 2:
                self.device_id = struct.unpack('!H', payload_data)[0]
                console.log.green(f"Successfully registered! Server assigned DeviceID: {self.device_id}")
                return True
            else:
                console.log.red(f"Received invalid STARTUP_ACK (Type: {msg_type})")
                return False

        except socket.timeout:
            console.log.red("[Error] No STARTUP_ACK received from server. Timed out.")
            return False
        except (struct.error, IndexError) as e:
            console.log.red(f"[Error] Failed to parse STARTUP_ACK: {e}")
            return False

    def _send_time_sync(self):
        console.log.text("Sending TIME_SYNC...")
        self.base_time = int(time.time())
        payload = struct.pack('!I', self.base_time)
        self._send_packet(MSG_TIME_SYNC, payload)

    def _send_keyframe(self):

        self.current_value = random.randint(400, 600)
        console.log.blue(f"Sending KEYFRAME -> {self.current_value}")
        payload = struct.pack('!h', self.current_value)
        self._send_packet(MSG_KEYFRAME, payload)

    def _send_data_delta(self):
        delta = random.randint(-10, 10)
        self.current_value += delta
        console.log.text(f"Sending DATA_DELTA -> {delta: >+3} (New Value: {self.current_value})")
        payload = struct.pack('!b', delta)
        self._send_packet(MSG_DATA_DELTA, payload)

    def _send_heartbeat(self):
        console.log.text("Sending HEARTBEAT...")
        self._send_packet(MSG_HEARTBEAT, b'')

    def run(self):
        if not self.connect():
            return

        self.running = True
        start_time = time.time()
        next_interval_time = start_time


        self._send_time_sync()
        time.sleep(0.01)
        self._send_keyframe()

        console.log.green(f"--- Client running for {self.duration} seconds ---")

        try:
            while self.running and (time.time() - start_time) < self.duration:
                sleep_time = next_interval_time - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                next_interval_time += self.interval

                # Send a TIME_SYNC every 100 packets or if base_time is 0
                if self.last_seq_num % 100 == 0 or self.base_time == 0:
                    self._send_time_sync()
                # Send a KEYFRAME every 10 packets
                elif self.last_seq_num % 10 == 0:
                    self._send_keyframe()
                # Send a HEARTBEAT every 5 packets
                elif self.last_seq_num % 5 == 0:
                    self._send_heartbeat()
                else:
                    self._send_data_delta()

        except KeyboardInterrupt:
            console.log.yellow("\nClient stopped by user.")
        finally:
            self.running = False
            console.log.yellow("--- Client shutting down ---")

    def close(self):
        self.sock.close()
        console.log.text("Socket closed.")