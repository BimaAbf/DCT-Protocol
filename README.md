# DCT-Protocol

A lightweight UDP-based telemetry protocol with batching, delta encoding, and CSV logging for analysis.

## Features

- UDP server that accepts device startup/registration, time sync, keyframes, deltas, heartbeats, and batched data
- Client simulator with configurable interval, duration, batching, MAC, and random seed
- Duplicate, gap, and delayed packet classification
- CSV logging with sorted, human-readable timestamps and CPU processing time (ms)
- Analysis helpers (pandas/matplotlib) for post-run insights

## Requirements

- Python 3.10+
- See `requirements.txt` for Python packages

Optional but useful for network tests (Linux): `tmux`, `tcpdump`

## Setup

1. Install dependencies
2. Create `.env` files


### 1) Install dependencies

```powershell
python -m pip install --upgrade pip ; pip install -r requirements.txt
```

### 2) Configure environment

Create `Server/.env` with:

```
HOST=127.0.0.1
PORT=5000
CSV_LOG_DIR=Server/logs
PROTOCOL_VERSION=1
MSG_STARTUP=0x1
MSG_STARTUP_ACK=0x2
MSG_TIME_SYNC=0x3
MSG_KEYFRAME=0x4
MSG_DATA_DELTA=0x5
MSG_HEARTBEAT=0x6
MSG_BATCHED_DATA=0x7
MSG_DATA_DELTA_QUANTIZED=0x8
MSG_KEYFRAME_QUANTIZED=0x9
MSG_BATCHED_DATA_QUANTIZED=0xA
MSG_BATCH_INCOMPLETE=0xB
MSG_SHUTDOWN=0xC
HEADER_FORMAT=!B H H I H
MAX_PACKET_SIZE=2048
```

> Adjust values as needed; `HEADER_FORMAT` must match client/server packing.

## Run

### Start the server

From `DCT-Protocol/Server`:

```powershell
python .\main.py
```

Logs will be written under `Server/logs/server_log_<timestamp>.csv`.

### Start a client

From `DCT-Protocol/Client`:

```powershell
# Template
python .\main.py <HOST> --port <PORT> --interval <SECONDS> --duration <SECONDS> --delta-thresh <INT> --mac "<MAC-ADDR>" --seed <INT> [--batching <N>]

# Example
python .\main.py 127.0.0.1 --port 5000 --interval 1.0 --duration 10 --delta-thresh 1 --mac "AA:BB:DC:DD:EE:fe" --seed 12
```

Common options:

- `--port` (int): server port, default 5000
- `--interval` (float): seconds between sends
- `--duration` (float): total run time in seconds
- `--mac` (str): MAC address used for registration
- `--seed` (int): RNG seed
- `--batching` (int): batch size (default 1)
- `--delta-thresh` (int): minimum change to emit a delta

## CSV Output

CSV header (Server):

```
msg_type,device_id,seq,timestamp,arrival_time,value,duplicate_flag,gap_flag,delayed_flag,cpu_time_ms
```

- `timestamp` and `arrival_time` are formatted as local time strings
- `cpu_time_ms` is the processing time per packet in milliseconds

## Troubleshooting

- If the server exits early, ensure `Server/.env` exists and all keys are valid
- If packets aren’t being processed, verify client host/port and firewall settings
- If CSV is empty or unsorted, check write permissions to `Server/logs` and that the run completed cleanly

## Development Notes

- The server sorts and rewrites the CSV on each write for convenience; for high-throughput scenarios, consider deferring sort and flush to shutdown
- Protocol constants are loaded from environment (`constants.py`)
