import socket
import struct
import time
import sys
import random
from collections import deque

from ConsoleColor import console
from constants import *


class Client:

    def __init__(self, server_host: str, server_port: int, mac: str, interval: float, duration: float,
                 seed: int, delta_thresh: int, batch_size: int):
        self.server_host = server_host
        self.server_port = (server_host, server_port)
        self.mac_str = mac
        self.interval = interval
        self.duration = duration
        if seed is not None:
            console.log.yellow(f"Using random seed: {seed}")
            random.seed(seed)
        self.delta_thresh = delta_thresh
        self.batch_size = batch_size
        self.batching = batch_size > 1
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(5.0)
        self.device_id = None
        self.last_seq_num = 0
        self.last_sent_time = 0
        self.last_sent_msg_type = None
        self.base_time = 0
        self.current_value = 500
        self.running = False
        self.reconnect_attempts = 3

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
            offset = int(time.time() - self.base_time) % 65536
        ver_msgtype = (PROTOCOL_VERSION << 4) | msg_type
        return struct.pack(HEADER_FORMAT,ver_msgtype,device_id,self.last_seq_num,offset,payload_len)
    def _send_packet(self, msg_type: int, payload: bytes):
        try:
            self.sock.sendto(self._pack_header(msg_type, len(payload)) + payload, self.server_port)
            self.last_sent_msg_type = msg_type
            self.last_sent_time = time.time()
            self.last_seq_num = (self.last_seq_num + 1) % 65536
        except socket.error as e:
            console.log.red(f"[Socket Error] Could not send packet: {e}")
            self.running = False

    def connect(self) -> bool:

        console.log.yellow(f"Sending STARTUP to {self.server_host}:{self.server_port[1]}..." +
                           f"\nBatching enabled: Sending {self.batch_size} packets per batch." if self.batching else "")
        mac_bytes = self._parse_mac(self.mac_str)
        if self.batching:
           mac_bytes += struct.pack('!B', self.batch_size)
        self._send_packet(MSG_STARTUP, mac_bytes)
        try:
            for i in range(self.reconnect_attempts):
                try:
                    data = self.sock.recvfrom(MAX_PACKET_SIZE)[0]
                    break
                except socket.timeout:
                    console.log.yellow(f"[Warning] No response from server, retrying STARTUP ({i + 1}/{self.reconnect_attempts})...")
                    self._send_packet(MSG_STARTUP, mac_bytes)
                    if i == self.reconnect_attempts - 1:
                        console.log.red("[Error] Maximum STARTUP retries reached. Could not connect to server.")
                        return False
            header_data = data[:HEADER_SIZE]
            payload_data = data[HEADER_SIZE:]
            (ver_msgtype, deviceid, seq, offset, payload_len) = struct.unpack(HEADER_FORMAT, header_data)
            msg_type = ver_msgtype & 0x0F
            if msg_type != MSG_STARTUP_ACK:
                console.log.red(f"[Error] Unexpected message type received: {msg_type}. Expected STARTUP_ACK.")
                return False
            if payload_len == 2:
                self.device_id = struct.unpack('!H', payload_data)[0]
                console.log.green(f"Successfully registered! Server assigned DeviceID: {self.device_id}")
                return True
            elif payload_len == 4:
                self.device_id, self.last_seq_num = struct.unpack('!HH', payload_data)
                self.last_seq_num += 1
                console.log.green(f"Re-registered! DeviceID: {self.device_id}, Last SeqNum: {self.last_seq_num}")
                return True
            else:
                console.log.red(f"[Error] Invalid payload length for STARTUP_ACK: {payload_len}")
                return False
        except socket.timeout:
            console.log.red("[Error] No STARTUP_ACK received from server. Timed out.")
            return False
        except (struct.error, IndexError) as exception:
            console.log.red(f"[Error] Failed to parse STARTUP_ACK: {exception}")
            return False
    def _send_time_sync(self):
        console.log.text("Sending TIME_SYNC...")
        self.base_time = int(time.time())
        payload = struct.pack('!I', self.base_time)
        self._send_packet(MSG_TIME_SYNC, payload)
    def _send_keyframe(self):
        console.log.blue(f"Sending KEYFRAME -> {self.current_value}")
        payload = struct.pack('!h', self.current_value)
        self._send_packet(MSG_KEYFRAME, payload)
    def _send_data_delta(self,delta: int):
        console.log.text(f"Sending DATA_DELTA -> {delta: >+3} (New Value: {self.current_value})")
        payload = struct.pack('!b', delta)
        self._send_packet(MSG_DATA_DELTA, payload)
    def _send_heartbeat(self):
        console.log.text("Sending HEARTBEAT...")
        self._send_packet(MSG_HEARTBEAT, b'')
    # Batch contains time offset and corresponding deltas mixed with timeoffset and corresponding keyframe inside payload
    def _send_batch(self, packets: deque):
        payload = b''
        for pkt in packets:
            offset, msg_type, value = pkt
            payload += struct.pack('!H', offset)
            if msg_type == MSG_KEYFRAME:
                payload += struct.pack('!Bh', MSG_KEYFRAME, value)
            elif msg_type == MSG_DATA_DELTA:
                payload += struct.pack('!Bb', MSG_DATA_DELTA, value)
        console.log.text(f"Sending BATCH of {len(packets)} packets...")
        self._send_packet(MSG_BATCHED_DATA, payload)
    def _send_shutdown(self):
        console.log.yellow("Sending SHUTDOWN...")
        self._send_packet(MSG_SHUTDOWN, b'')
    def run(self):
        if not self.connect():
            return
        self.running = True
        start_time = time.time()
        next_interval_time = start_time
        if self.batching:
            batch_packets = deque()
            batch_value_change_counter = 0
            batch_time_sync_counter = 0
        self._send_time_sync()
        time.sleep(0.01)
        self.current_value = random.randint(400, 600)
        self._send_keyframe()
        console.log.green(f"--- Client running for {self.duration} seconds ---")
        try:
            while self.running and (time.time() - start_time) < self.duration:
                sleep_time = next_interval_time - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                next_interval_time += self.interval
                if self.batching:
                    offset = int(time.time() - self.base_time) % 65536
                    if batch_value_change_counter >= 10:
                        batch_packets.append((offset, MSG_KEYFRAME, self.current_value))
                        batch_value_change_counter = 0
                    else:
                        delta = random.randint(-10 * self.delta_thresh, 10 * self.delta_thresh)
                        batch_value_change_counter += 1
                        if abs(delta) > self.delta_thresh:
                            self.current_value += delta
                            if delta > 128 or delta < -127:
                                batch_packets.append((offset, MSG_KEYFRAME, self.current_value))
                            else:
                                batch_packets.append((offset, MSG_DATA_DELTA, delta))
                        else:
                            if time.time() - self.last_sent_time > self.interval * 5:
                                self._send_heartbeat()
                    if len(batch_packets) == self.batch_size:
                        self._send_batch(batch_packets)
                        batch_packets.clear()
                        batch_time_sync_counter += 1
                        if batch_time_sync_counter >= 10:
                            self._send_time_sync()
                            batch_time_sync_counter = 0
                else:
                    # Send a TIME_SYNC every 100 packets or if base_time is 0
                    if self.last_seq_num % 100 == 0 or self.base_time == 0:
                        self._send_time_sync()
                    # Send a KEYFRAME every 10 packets
                    if self.last_seq_num % 10 == 0 and self.last_sent_msg_type != MSG_KEYFRAME:
                        self._send_keyframe()
                    # Send a HEARTBEAT every 5 packets if no delta or keyframe sent
                    else:
                        delta = random.randint(-10 * self.delta_thresh, 10* self.delta_thresh)
                        if abs(delta) > self.delta_thresh:
                            self.current_value += delta
                            if delta > 128 or delta < -127:
                                self._send_keyframe()
                            else:
                                self._send_data_delta(delta)
                        else:
                            if time.time() - self.last_sent_time > self.interval * 5:
                                self._send_heartbeat()
        except KeyboardInterrupt:
            console.log.yellow("\nClient stopped by user.")
        finally:
            if self.batching and batch_packets:
                self._send_batch(batch_packets)
            self.running = False
            self._send_shutdown()
            console.log.yellow("--- Client shutting down ---")
    def close(self):
        self.sock.close()
        console.log.text("Socket closed.")