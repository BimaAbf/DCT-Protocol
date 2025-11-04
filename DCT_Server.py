import socket
import struct
import time
import csv
import sys
from typing import Dict, Any, Tuple

# --- Constants from RFC ---
HOST = '0.0.0.0'  # Listen on all available interfaces
PORT = 12345  # Port to listen on (arbitrary)
MAX_PACKET_SIZE = 200  # Max UDP payload size per RFC [cite: 47]
HEADER_FORMAT = '!BHBHHH'  # Corrected header format
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
PROTOCOL_VERSION = 0x01  # Per RFC [cite: 86]

# --- Message Types from RFC Table 3  ---
MSG_STARTUP = 0x01
MSG_STARTUP_ACK = 0x02
MSG_TIME_SYNC = 0x03
MSG_KEYFRAME = 0x04
MSG_DATA_DELTA = 0x05
MSG_HEARTBEAT = 0x06

# --- Server State ---
# This dictionary will hold the state for each known device.
# This follows the FSM's need to track state (e.g., sequence numbers).
device_db: Dict[int, Dict[str, Any]] = {}
next_device_id = 1  # Simple unique ID generator
csv_writer = None
csv_file = None


# --- FSM Logic Implementation ---

def initialize_server() -> socket.socket:
    """
    Corresponds to the 'Initialization' state.
    Boots up, binds the socket, and prepares for the IDLE state.
    """
    print(f"[Initialization] Booting server...")

    # 1. Create UDP Socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # 2. Bind to host and port
    try:
        sock.bind((HOST, PORT))
        print(f"[Initialization] Server loaded and started. Binding to {HOST}:{PORT}.")
    except OSError as e:
        print(f"[Initialization] FATAL: Could not bind to port {PORT}. {e}")
        sys.exit(1)

    # 3. Prepare CSV logging (per 'Write Readings to CSV' state )
    global csv_writer, csv_file
    try:
        # Open in 'a+' (append mode) to avoid overwriting on restart
        csv_file = open('server_log.csv', 'a+', newline='')
        csv_writer = csv.writer(csv_file)
        # Write header if the file is new/empty
        if csv_file.tell() == 0:
            csv_writer.writerow(['DeviceID','Sequence Number','Value','Packet Timestamp','Arrival Time','Latency (ms)'])
        print("[Initialization] CSV logging is active.")
    except IOError as e:
        print(f"[Initialization] FATAL: Could not open CSV file. {e}")
        sys.exit(1)

    print(f"[IDLE] Server is now in IDLE state, waiting for packets...")
    return sock


def handle_packet(data: bytes, addr: Tuple[str, int], sock: socket.socket, arrival_time: float = None):
    """
    Corresponds to 'Packet Received' state.
    This function is the main entry point for parsing and dispatching.
    """

    # 1. Validate packet size
    if len(data) < HEADER_SIZE:
        print(f"[Packet Error] Runt packet received from {addr}. Discarding.")
        return

    # 2. Unpack the 10-byte header [cite: 77, 97]
    try:
        header_data = data[:HEADER_SIZE]
        payload_data = data[HEADER_SIZE:]

        (ver_msgtype, device_id, flags, seq_num,
         timestamp_offset, payload_len) = struct.unpack(HEADER_FORMAT, header_data)

        version = (ver_msgtype >> 4) & 0x0F
        msg_type = ver_msgtype & 0x0F

    except struct.error as e:
        print(f"[Packet Error] Could not parse header from {addr}. {e}. Discarding.")
        return

    # 3. Check protocol version
    if version != PROTOCOL_VERSION:
        print(f"[Packet Error] Wrong protocol version {version} from {addr}. Discarding.")
        return

    # 4. Check payload length integrity
    if len(payload_data) != payload_len:
        print(
            f"[Packet Error] Payload length mismatch from {addr}. Header says {payload_len}, got {len(payload_data)}. Discarding.")
        return

    # 5. Dispatch based on Message Type
    if msg_type == MSG_STARTUP:
        # Special case: STARTUP message (DeviceID is 0) [cite: 60, 86]
        handle_startup(payload_data, addr, sock)
    else:
        # All other messages from known devices
        handle_telemetry(
            (device_id, msg_type, seq_num, timestamp_offset, payload_len),
            payload_data,
            addr, arrival_time
        )


def handle_startup(payload: bytes, addr: Tuple[str, int], sock: socket.socket):
    """
    Handles a STARTUP (0x01) message.
    This enrolls a new device and sends a STARTUP_ACK (0x02)[cite: 61, 62].
    """
    global next_device_id, device_db

    print(f"[STARTUP] Received STARTUP request from {addr}.")

    # In a real system, you might check the payload for a MAC/Serial
    # For this example, we just assign the next available ID.

    new_id = next_device_id
    next_device_id += 1

    # Initialize state for the new device
    device_db[new_id] = {
        'client_address': addr,
        'MAC': struct.unpack("6s",payload),  # Store MAC from payload
        'last_seq_num': -1,  # -1 indicates no packets received yet
        'base_time': 0,
        'last_seen': time.time(),
        'current_value': -1  # To store last KEYFRAME values
    }

    print(f"[STARTUP] Assigning DeviceID {new_id} to {addr} - MAC: {device_db[new_id]['MAC']}.")

    # Send STARTUP_ACK (0x02)
    try:
        # Header: Ver/MsgType, DeviceID, Flags, SeqNum, Timestamp, PayloadLen
        ack_header = struct.pack(HEADER_FORMAT,
                                 (PROTOCOL_VERSION << 4) | MSG_STARTUP_ACK,
                                 new_id, 0, 0, 0, 2)
        # Payload: 2-byte Assigned DeviceID
        ack_payload = struct.pack('!H', new_id)

        sock.sendto(ack_header + ack_payload, addr)
        print(f"[STARTUP_ACK] Sent ACK with DeviceID {new_id} to {addr}.")

    except socket.error as e:
        print(f"[Socket Error] Could not send STARTUP_ACK to {addr}. {e}")


def handle_telemetry(header_info: tuple, payload: bytes, addr: Tuple[str, int],arrival_time: float = None):
    """
    Handles all messages from registered devices (TIME_SYNC, KEYFRAME, etc.)
    This function implements the main FSM logic from the diagram.
    """
    device_id, msg_type, seq_num, timestamp_offset, payload_len = header_info

    # 1. Check if device is registered
    if device_id not in device_db:
        print(f"[Packet Error] Received packet from unknown DeviceID {device_id} at {addr}. Discarding.")
        return

    device_state = device_db[device_id]

    # --- Sequence Number Check (State) [cite: 144] ---
    expected_seq = (device_state['last_seq_num'] + 1) % 65536  # Handle 16-bit wrap-around
    if seq_num == device_state['last_seq_num']:
        print(f"[Packet Error] Duplicate packet with SeqNum {seq_num} from DeviceID {device_id}. Suppressing.")
        return
    if seq_num == expected_seq:
        # --- Sequence Number Correct (Transition) [cite: 148] ---
        device_state['last_seq_num'] = seq_num
    else:
        # --- Sequence Number Incorrect (Transition) [cite: 146] ---
        """
        Handle out-of-order packets.
        """

        # 'Log Lost Packet' (State) [cite: 142]
        # RFC: "Loss is detected by the server via gaps in the Sequence Number field." [cite: 44]
        if device_state['last_seq_num'] != -1:  # Don't log loss on first packet
            packets_lost = (seq_num - device_state['last_seq_num'] - 1 + 65536) % 65536
            print(
                f"[Log Lost Packet] Packet loss for DeviceID {device_id}. Expected {expected_seq}, got {seq_num}. ({packets_lost} packet(s) lost).")

        # 'Report Back' (State) [cite: 143] -> IDLE
        # The RFC does not define a "Report Back" message.
        # We will log the loss and resynchronize to the new sequence number.
        device_state['last_seq_num'] = seq_num

    # --- Reset Liveness Timer (State) [cite: 136] ---
    # This happens on *any* valid packet from a known device.
    device_state['last_seen'] = time.time()

    # --- Handle Message Type (part of 'Write Readings' logic) ---
    base_time = device_state['base_time']
    full_timestamp_s = base_time + timestamp_offset # Calculate full timestamp [cite: 42, 86]

    try:
        if msg_type == MSG_TIME_SYNC:  # 0x03
            base_time = struct.unpack('!I', payload)[0]  # 4-byte Unix time
            device_state['base_time'] = base_time
            print(f"[TIME_SYNC] DeviceID {device_id} set base time to {time.ctime(base_time)}.")

        elif msg_type == MSG_KEYFRAME:  # 0x04
            print(f"[KEYFRAME] DeviceID {device_id} sent KEYFRAME.")
            # Payload: [(1-byte SensorID, 2-byte Quantized Value), ...]
            for i in range(0, payload_len, 2):
                value = int(struct.unpack('!h', payload[i:i + 2])[0])
                device_state['current_value'] = value  # Store full value
                # --- 'Write Readings to CSV' (State)  ---
                log_to_csv(full_timestamp_s,arrival_time, device_id, value, seq_num)

        elif msg_type == MSG_DATA_DELTA:  # 0x05
            print(f"[DATA_DELTA] DeviceID {device_id} sent DELTA.")
            # Payload: [(1-byte SensorID, 1-byte Quantized Delta), ...]
            for i in range(0, payload_len, 1):
                delta = int(struct.unpack('!b', payload[i:i + 1])[0])
                # Apply delta to stored value
                old_value = device_state['current_value']
                new_value = old_value + delta
                device_state['current_value'] = new_value  # Store new value
                # --- 'Write Readings to CSV' (State)  ---
                log_to_csv(full_timestamp_s,arrival_time, device_id, new_value, seq_num)

        elif msg_type == MSG_HEARTBEAT:  # 0x06
            # No payload. Liveness timer was already reset.
            print(f"[HEARTBEAT] Liveness ping from DeviceID {device_id}.")
            log_to_csv(full_timestamp_s,arrival_time, device_id, -1, seq_num)  # Log heartbeat with value -1

        else:
            print(f"[Packet Error] Unknown message type {msg_type} from DeviceID {device_id}. Discarding.")

    except struct.error as e:
        print(f"[Payload Error] Could not parse payload for msg {msg_type} from DeviceID {device_id}. {e}")
    except IOError as e:
        print(f"[CSV Error] Failed to write to CSV file. {e}")


def log_to_csv(timestamp_s: float,arrival_time: float, device_id: int, value: int = -1,seq_num: int = 0):
    """
    Helper function for the 'Write Readings to CSV' state.
    """
    global csv_writer, csv_file
    if csv_writer and csv_file:
        human_readable_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp_s))
        human_readable_arrival = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(arrival_time))
        csv_writer.writerow([device_id, seq_num, (value if value != -1 else 'Heartbeat'), human_readable_time,human_readable_arrival, int((arrival_time-timestamp_s) *1000)])
        csv_file.flush()  # Ensure data is written immediately


# --- Main Execution ---
if __name__ == "__main__":
    sock = initialize_server()

    try:
        # This is the main 'IDLE' loop [cite: 138]
        while True:
            try:
                # Wait for a packet
                data, addr = sock.recvfrom(MAX_PACKET_SIZE)
                last_arrival_time = time.time()
                # --- 'Packet Received' (Transition) [cite: 145] ---
                # Go to the 'handle_packet' logic
                handle_packet(data, addr, sock, last_arrival_time)

                # After handling, the server implicitly returns to the 'IDLE'
                # state by looping back to sock.recvfrom()

            except socket.error as e:
                # Handle non-fatal socket errors
                print(f"[Socket Error] {e}. Server continues...")
                time.sleep(1)

    except KeyboardInterrupt:
        print("\n[Shutdown] Server shutting down...")
    finally:
        if csv_file:
            csv_file.close()
            print("[Shutdown] CSV file closed.")
        sock.close()
        print("[Shutdown] Socket closed. Server offline.")