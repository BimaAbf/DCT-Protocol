import socket
import struct
import time
import random

# --- Constants from RFC ---
SERVER_HOST = '127.0.0.1'  # Change to server's IP if not on same machine
SERVER_PORT = 12345
MAX_PACKET_SIZE = 200  # Max UDP payload size per RFC [cite: 47]b 
SERVER_ADDRESS = (SERVER_HOST, SERVER_PORT)
HEADER_FORMAT = '!BHBHHH'  # 10-byte header format
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
PROTOCOL_VERSION = 0x01

# --- Message Types from RFC Table 3 ---
MSG_STARTUP = 0x01
MSG_STARTUP_ACK = 0x02
MSG_TIME_SYNC = 0x03
MSG_KEYFRAME = 0x04
MSG_DATA_DELTA = 0x05
MSG_HEARTBEAT = 0x06

# --- Client FSM Timer Constants ---
REPORT_INTERVAL_S = 5  # "Interval timeout": Check sensor every N sec
KEYFRAME_INTERVAL_S = 10 * REPORT_INTERVAL_S  # "KEY_FRAME TIMEOUT": Resync every 10N sec
HEARTBEAT_TIMEOUT_S = 5 * REPORT_INTERVAL_S  # "Heartbeat Timeout soon": Send liveness if idle for 15 sec

# --- Sensor Simulation Constants ---
DELTA_THRESHOLD = 5  # "Higher than Threshold"

# --- Client State Variables ---
initialized = False
client_sock = None
device_id = 0  # 0 = Unassigned
seq_num = 0  # Incremented per-packet
base_time = 0  # Our 4-byte Unix timestamp
last_sent_value = 0  # Last value we sent
current_sim_value = 100  # The "real" value of our sensor
last_packet_sent_time = 0  # For heartbeats


def create_header(msg_type, payload_len):
    """
    Creates a 10-byte header, increments the sequence number,
    and calculates the timestamp offset.
    """
    global seq_num

    # 1. Combine Version and MsgType
    ver_msgtype = (PROTOCOL_VERSION << 4) | msg_type

    # 2. Calculate Timestamp Offset
    # Offset in seconds from base time. Wraps every 65536s (about 18.2 hours)
    if initialized:
        now_s = int((time.time() - base_time))
        timestamp_offset = now_s % 65536  # 16-bit wrap-around
    else:
        timestamp_offset = 0
    flags = 0  # No batching in this simple client

    # 3. Pack the header
    header = struct.pack(HEADER_FORMAT,
                         ver_msgtype,
                         device_id,
                         flags,
                         seq_num,
                         timestamp_offset,
                         payload_len)

    # 4. Increment sequence number for next packet
    seq_num = (seq_num + 1) % 65536  # 16-bit wrap-around
    return header


def send_packet(header: bytes, payload: bytes = b''):
    """Helper function to send a packet and update liveness timer."""
    global last_packet_sent_time
    try:
        client_sock.sendto(header + payload, SERVER_ADDRESS)
        last_packet_sent_time = time.time()
    except socket.error as e:
        print(f"[Socket Error] Failed to send packet: {e}")


# --- FSM State Functions ---

def run_initialization() -> bool:
    """
    Corresponds to 'Initialization' state.
    Sends STARTUP, waits for STARTUP_ACK.
    """
    global device_id, seq_num
    print(f"[Initialization] Boot/Startup: Sending STARTUP to {SERVER_ADDRESS}...")

    # 1. Create STARTUP Packet
    seq_num = 0  # Sequence number is 0 for STARTUP
    payload = b'\xAA\xBB\xCC\xDD\xEE\xFF'  # 6-byte MAC (per RFC)
    header = create_header(MSG_STARTUP, len(payload))

    # 2. Send and wait for reply
    client_sock.sendto(header + payload, SERVER_ADDRESS)
    client_sock.settimeout(5.0)  # Wait 5 seconds for a reply

    try:
        data, _ = client_sock.recvfrom(MAX_PACKET_SIZE)

        # 3. Parse ACK
        if len(data) < HEADER_SIZE + 2:
            print("[Initialization] Received runt STARTUP_ACK. Exiting.")
            return False

        header_data = data[:HEADER_SIZE]
        payload_data = data[HEADER_SIZE:]

        # Unpack header
        (ver_msgtype, ack_dev_id, _, _, _,
         payload_len) = struct.unpack(HEADER_FORMAT, header_data)

        msg_type = ver_msgtype & 0x0F

        if msg_type != MSG_STARTUP_ACK:
            print(f"[Initialization] Expected STARTUP_ACK, got {msg_type}. Exiting.")
            return False

        # Unpack payload
        assigned_id = struct.unpack('!H', payload_data)[0]

        # 4. Set State
        device_id = assigned_id
        print(f"[Initialization] Finished. Server assigned DeviceID: {device_id}")
        global initialized
        initialized = True
        return True

    except socket.timeout:
        print("[Initialization] No response from server. Exiting.")
        return False


def send_time_sync():
    """
    Sends the TIME_SYNC (0x03) message. (Per RFC flow)
    """
    global base_time
    base_time = int(time.time())

    print(f"[TIME_SYNC] Sending base time: {time.ctime(base_time)}...")

    payload = struct.pack('!I', base_time)  # 4-byte Unix time
    header = create_header(MSG_TIME_SYNC, len(payload))
    send_packet(header, payload)


def send_keyframe():
    """
    Corresponds to 'Send KEY_FRAME' state.
    Sends the full, quantized sensor value.
    """
    global last_sent_value, current_sim_value

    value_to_send = int(current_sim_value)
    print(f"[KEY_FRAME] Sending KEY_FRAME with value: {value_to_send}")

    # Payload: [(1-byte SensorID, 2-byte Quantized Value), ...]
    payload = struct.pack('!h',  value_to_send)
    header = create_header(MSG_KEYFRAME, len(payload))

    send_packet(header, payload)

    # Update our state
    last_sent_value = value_to_send


def send_delta(new_value: int):
    """
    Corresponds to 'Send DELTA' state.
    Sends the 1-byte change in sensor value.
    """
    global last_sent_value

    # Calculate 1-byte signed delta
    delta = new_value - last_sent_value

    print(f"[DATA_DELTA] Sending DELTA. New: {new_value}, Old: {last_sent_value}, Delta: {delta}")

    # Payload: [(1-byte SensorID, 1-byte Quantized Delta), ...]
    payload = struct.pack('!b',  delta)  # 'b' is signed char
    header = create_header(MSG_DATA_DELTA, len(payload))

    send_packet(header, payload)

    # Update our state
    last_sent_value = new_value


def send_heartbeat():
    """
    Corresponds to 'send HEARTBEAT' state.
    Sends a liveness message with no payload.
    """
    print(f"[HEARTBEAT] Sending liveness HEARBEAT.")

    header = create_header(MSG_HEARTBEAT, 0)  # 0 payload length
    send_packet(header)


def simulate_sensor_reading() -> int:
    """
    Simulates a sensor value that drifts and occasionally jumps.
    Corresponds to 'Monitor (New Reading)'
    """
    global current_sim_value

    # 1. Slow drift
    current_sim_value += random.uniform(-0.5, 0.5)

    # 2. Occasional sharp change (to trigger DELTA)
    if random.random() < 0.1:  # 10% chance
        current_sim_value += random.uniform(-10, 10)

    # 3. Occasional jump (to test KEYFRAME recovery)
    if random.random() < 0.02:  # 2% chance
        current_sim_value = random.uniform(50, 150)

    return int(current_sim_value)


def run_telemetry_loop():
    """
    This is the main FSM loop after initialization.
    It implements 'IDLE', 'Monitor', 'Check Liveness', and all timers.
    """
    global last_packet_sent_time
    print("[IDLE] Entering main telemetry loop...")

    last_report_time = time.time()
    last_keyframe_time = time.time()
    last_packet_sent_time = time.time()

    while True:
        try:
            now = time.time()

            # --- FSM Timer 1: KEY_FRAME TIMEOUT ---
            if now - last_keyframe_time > KEYFRAME_INTERVAL_S:
                send_keyframe()
                last_keyframe_time = now
                last_report_time = now  # Don't report immediately after
                continue  # Go back to start of loop

            # --- FSM Timer 2: Interval timeout ---
            if now - last_report_time > REPORT_INTERVAL_S:
                last_report_time = now

                # --- 'Monitor (New Reading)' state ---
                new_value = simulate_sensor_reading()
                delta = abs(new_value - last_sent_value)

                # --- Decision: Threshold Check ---
                if delta > DELTA_THRESHOLD:
                    # 'Higher than Threshold' -> 'Send DELTA'
                    send_delta(new_value)
                else:
                    # 'Less than Threshold' -> 'Check Liveness'

                    # --- FSM Timer 3: Heartbeat Timeout soon ---
                    if now - last_packet_sent_time > HEARTBEAT_TIMEOUT_S:
                        # 'send HEARTBEAT'
                        send_heartbeat()
                    else:
                        # Still 'IDLE', do nothing
                        pass

            time.sleep(0.1)  # Be a good CPU citizen

        except KeyboardInterrupt:
            print("\n[Shutdown] Telemetry loop stopped.")
            break


# --- Main Execution ---
if __name__ == "__main__":
    try:
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        if run_initialization():
            send_time_sync()
            send_keyframe()  # Send initial keyframe
            run_telemetry_loop()

    except Exception as e:
        print(f"[FATAL] An unexpected error occurred: {e}")
    finally:
        if client_sock:
            client_sock.close()
            print("[Shutdown] Socket closed.")