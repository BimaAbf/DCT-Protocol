# DCT Protocol Test Harness

This repository contains the server, client, and automation scripts used to exercise the DCT protocol locally.

(DEMO VIDEO HERE!)[https://drive.google.com/file/d/1eU5GgXh4rePaPaVkoH674pTVsD122iGa/view?usp=drive_link]

---

## 1. Build Instructions

### Prerequisites

| Tool | Purpose | Install command (Ubuntu/Debian) |
|------|---------|---------------------------------|
| Python 3.10+ | Runs the server, client, and analysis tools | `sudo apt install python3 python3-pip python3-venv` |
| tmux | Manages background server/client sessions | `sudo apt install tmux` |
| tcpdump | Captures loopback packets | `sudo apt install tcpdump` |
| tc (iproute2) | Required for netem scripts | `sudo apt install iproute2` |



### Installation

1.  **Prepare Python Environment:**
    ```bash
    pip install --upgrade pip
    pip install -r requirements.txt
    ```

---

## 2. Usage Examples

### Running the Server
The server is configured via the `.env` file (e.g., HOST, PORT).
```bash
python3 Server/main.py
```

### Running a Client
The client connects to the server and simulates data transmission.
```bash
# Basic usage
python3 Client/main.py 127.0.0.1 --mac "AA:BB:CC:DD:EE:01"

# With custom options (port, interval, duration, batching)
python3 Client/main.py 127.0.0.1 --port 5000 --interval 0.1 --duration 30 --mac "AA:BB:CC:DD:EE:02" --batching 5
```

### Running the GUI Dashboard
Launch the graphical interface to monitor clients and logs.
```bash
python3 GUI/main.py
```

### Running the Automated Baseline Test


The baseline script (`test_script/initialTest.sh`) orchestrates the following:

1. Starts `tcpdump` on the loopback interface.
2. Launches the server (`Server/main.py`) in a tmux session and logs the output.
3. Spawns five client instances (`Client/main.py`) in separate tmux sessions with fixed seeds/MACs.
4. Waits for the clients to finish, then cleans up tmux sessions and `tcpdump`.
5. Stores all artefacts under a timestamped folder (`test_script/Test_<timestamp>`).

### Run the baseline test

```bash
cd test_script
sudo bash initialTest.sh
```

After completion, inspect the generated folder for:

- `ServerTerminalOutput.txt` – server console output
- `ClientTerminalOutput.txt` – concatenated client outputs
- `Client0X_TerminalOutput.txt` – per-client logs
- `lo_capture.pcap` – packet capture of loopback traffic
- `tcpdump.log` – tcpdump stderr

---

## 3. Protocol Implementation Details

### Field-Packing Strategy
To minimize bandwidth usage and packet size, the protocol uses a custom binary packing strategy (Big-Endian) rather than verbose text-based formats like JSON.

- **Header Structure (8 bytes):**
  - **Version & Type (1 byte):** High nibble for Protocol Version, Low nibble for Message Type.
  - **Device ID (2 bytes):** Unique identifier assigned by the server.
  - **Sequence Number (2 bytes):** Used for ordering and loss detection.
  - **Time Offset (2 bytes):** Relative timestamp from the base time.
  - **Payload Length (1 byte):** Size of the data payload.

- **Payload Packing:**
  - **Keyframes:** 2-byte signed integers (`!h`).
  - **Deltas:** 1-byte signed integers (`!b`).
  - **Time Sync:** 4-byte unsigned integers (`!I`).

### Batching Decision
To further reduce network overhead, especially for high-frequency data, the client implements a batching mechanism.

- **Mechanism:** When `batching` is enabled (size > 1), the client accumulates data updates (deltas or keyframes) in a queue instead of sending them immediately.
- **Trigger:** A `MSG_BATCHED_DATA` packet is transmitted once the queue length reaches the configured `batch_size`.
- **Structure:** The payload of a batched packet consists of concatenated updates. Each update within the batch preserves its own 2-byte time offset, 1-byte message type, and value.
- **Benefit:** This strategy significantly reduces the ratio of header overhead to payload data, improving throughput and reducing the packet rate on the network.


---
