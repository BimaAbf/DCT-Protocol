# DCT Protocol Test Harness

This repository contains the server, client, and automation scripts used to exercise the DCT protocol locally. Use the instructions below to get a clean environment, install dependencies, and execute the baseline test scenario that captures loopback traffic while running the server and five client instances.

---

## 1. Prerequisites

| Tool | Purpose | Install command (Ubuntu/Debian) |
|------|---------|---------------------------------|
| Python 3.10+ | Runs the server, client, and analysis tools | `sudo apt install python3 python3-pip python3-venv` |
| tmux | Manages background server/client sessions | `sudo apt install tmux` |
| tcpdump | Captures loopback packets | `sudo apt install tcpdump` |
| tc (iproute2) | Required for netem scripts | `sudo apt install iproute2` |



## 2. Prepare Environment

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Baseline Local Test 

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