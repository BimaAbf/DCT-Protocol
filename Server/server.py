import socket
import struct
import time
import sys
from typing import Dict, Any, Tuple
from constants import *
from ConsoleColor import console
from logger import Logger


class Server:

    def __init__(self, host: str, port: int, csv_log_dir: str):
        self.host = host
        self.port = port
        self.sock = None
        self.running = False
        self.start_time = time.time()

        self.device_db: Dict[int, Dict[str, Any]] = {}
        self.next_device_id = 1

        self.logger = Logger(csv_log_dir, "server_log")

        console.log.green(f"[Initialization] Booting server...")

        # 1. Start the logger
        if not self.logger.start(self.start_time):
            console.log.red("[Initialization] FATAL: Could not start CSV logger.")
            sys.exit(1)

        # 2. Create UDP Socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0) # Set a timeout for non-blocking loop

        # 3. Bind to host and port
        try:
            self.sock.bind((self.host, self.port))
            console.log.green(f"[Initialization] Server loaded and started. Binding to {self.host}:{self.port}.")
        except OSError as e:
            console.log.red(f"[Initialization] FATAL: Could not bind to port {self.port}. {e}")
            self.logger.close()
            sys.exit(1)

        console.log.blue(f"[IDLE] Server is now in IDLE state, waiting for packets...")
        self.running = True

    def run(self):

        if not self.sock:
            console.log.red("[Server Error] Server not started. Call start() first.")
            return

        try:
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(MAX_PACKET_SIZE)
                    arrival_time = time.time()

                    self.handle_packet(data, addr, arrival_time)

                except socket.timeout:
                    continue
                except socket.error as e:
                    console.log.red(f"[Socket Error] {e}. Server continues...")
                    time.sleep(1)

        except KeyboardInterrupt:
            console.log.yellow("\n[Shutdown] Keyboard interrupt received.")
        finally:
            self.stop()

    def handle_packet(self, data: bytes, addr: Tuple[str, int], arrival_time: float):

        # 1. Validate packet size
        if len(data) < HEADER_SIZE:
            console.log.yellow(f"[Packet Error] Runt packet received from {addr}. Discarding.")
            return

        # 2. Unpack the 10-byte header
        try:
            header_data = data[:HEADER_SIZE]
            payload_data = data[HEADER_SIZE:]

            (ver_msgtype, device_id, flags, seq_num,
             timestamp_offset, payload_len) = struct.unpack(HEADER_FORMAT, header_data)

            version = (ver_msgtype >> 4) & 0x0F
            msg_type = ver_msgtype & 0x0F

        except struct.error as e:
            console.log.red(f"[Packet Error] Could not parse header from {addr}. {e}. Discarding.")
            return

        # 3. Check protocol version
        if version != PROTOCOL_VERSION:
            console.log.yellow(f"[Packet Error] Wrong protocol version {version} from {addr}. Discarding.")
            return

        # 4. Check payload length integrity
        if len(payload_data) != payload_len:
            console.log.yellow(
                f"[Packet Error] Payload length mismatch from {addr}. Header says {payload_len}, got {len(payload_data)}. Discarding.")
            return

        # 5. Dispatch based on Message Type
        if msg_type == MSG_STARTUP:
            self.handle_startup(payload_data, addr)
        else:
            # All other messages from known devices
            self.handle_telemetry(
                (device_id, msg_type, seq_num, timestamp_offset, payload_len),
                payload_data,
                addr, arrival_time
            )

    def handle_startup(self, payload: bytes, addr: Tuple[str, int]):
        console.log.blue(f"[STARTUP] Received STARTUP request from {addr}.")

        new_id = self.next_device_id
        self.next_device_id += 1

        try:
            mac_addr_str = ":".join(f"{b:02X}" for b in payload)
        except struct.error:
            mac_addr_str = "INVALID_MAC"

        self.device_db[new_id] = {
            'client_address': addr,
            'MAC': mac_addr_str,
            'last_seq_num': -1,  # -1 indicates no packets received yet
            'base_time': 0,
            'last_seen': time.time(),
            'current_value': 0  # To store last KEYFRAME values
        }

        console.log.blue(f"[STARTUP] Assigning DeviceID {new_id} to {addr} - MAC: {mac_addr_str}.")

        try:
            # Header: Ver/MsgType, DeviceID, Flags, SeqNum, Timestamp, PayloadLen
            ack_header = struct.pack(HEADER_FORMAT,
                                     (PROTOCOL_VERSION << 4) | MSG_STARTUP_ACK,
                                     new_id, 0, 0, 0, 2)
            # Payload: 2-byte Assigned DeviceID
            ack_payload = struct.pack('!H', new_id)

            self.sock.sendto(ack_header + ack_payload, addr)
            console.log.green(f"[STARTUP_ACK] Sent ACK with DeviceID {new_id} to {addr}.")

        except socket.error as e:
            console.log.red(f"[Socket Error] Could not send STARTUP_ACK to {addr}. {e}")

    def handle_telemetry(self, header_info: tuple, payload: bytes, addr: Tuple[str, int], arrival_time: float):
        device_id, msg_type, seq_num, timestamp_offset, payload_len = header_info

        # 1. Check if device is registered
        if device_id not in self.device_db:
            console.log.yellow(f"[Packet Error] Received packet from unknown DeviceID {device_id} at {addr}. Discarding.")
            return

        device_state = self.device_db[device_id]

        is_duplicate = False
        is_gap = False
        base_time = device_state['base_time']
        full_timestamp_s = base_time + timestamp_offset

        expected_seq = (device_state['last_seq_num'] + 1) % 65536

        if device_state['last_seq_num'] == -1: # First packet from this device
            device_state['last_seq_num'] = seq_num
        elif seq_num == device_state['last_seq_num']:
            console.log.yellow(f"[Duplicate] Duplicate packet SeqNum {seq_num} from DeviceID {device_id}. Suppressing.")
            is_duplicate = True
        elif seq_num != expected_seq:
            packets_lost = (seq_num - device_state['last_seq_num'] - 1 + 65536) % 65536
            console.log.red(
                f"[Gap Detect] Packet loss for DeviceID {device_id}. Expected {expected_seq}, got {seq_num}. ({packets_lost} packet(s) lost).")
            is_gap = True
            device_state['last_seq_num'] = seq_num
        else:
            device_state['last_seq_num'] = seq_num

        self.logger.log_packet(
            device_id, seq_num, full_timestamp_s, arrival_time, is_duplicate, is_gap
        )

        if is_duplicate:
            return # Do not process payload

        device_state['last_seen'] = time.time()

        try:
            if msg_type == MSG_TIME_SYNC:  # 0x03
                base_time_val = struct.unpack('!I', payload)[0]  # 4-byte Unix time
                device_state['base_time'] = base_time_val
                console.log.blue(f"[TIME_SYNC] DeviceID {device_id} set base time to {time.ctime(base_time_val)}.")

            elif msg_type == MSG_KEYFRAME:  # 0x04
                for i in range(0, payload_len, 2):
                    value = int(struct.unpack('!h', payload[i:i + 2])[0])
                    device_state['current_value'] = value  # Store full value

            elif msg_type == MSG_DATA_DELTA:  # 0x05
                for i in range(0, payload_len, 1):
                    delta = int(struct.unpack('!b', payload[i:i + 1])[0])
                    old_value = device_state['current_value']
                    new_value = old_value + delta
                    device_state['current_value'] = new_value

            elif msg_type == MSG_HEARTBEAT:
                console.log.blue(f"[HEARTBEAT] Liveness ping from DeviceID {device_id}.")

            else:
                console.log.yellow(f"[Packet Error] Unknown message type {msg_type} from DeviceID {device_id}. Discarding.")

        except struct.error as e:
            console.log.red(f"[Payload Error] Could not parse payload for msg {msg_type} from DeviceID {device_id}. {e}")
        except IOError as e:
            console.log.red(f"[CSV Error] Failed to write to CSV file. {e}")

    def stop(self):

        console.log.yellow("[Shutdown] Server shutting down...")
        self.running = False
        if self.logger:
            self.logger.close()
        if self.sock:
            self.sock.close()
            console.log.yellow("[Shutdown] Socket closed. Server offline.")