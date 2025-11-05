# Client Session Playground Guide

## Overview

`tmux.sh` orchestrates multiple `client.py` instances inside a dedicated tmux session. It provides both a one-shot CLI and an interactive shell so you can start, monitor, restart, and introspect each client window without memorising raw tmux commands. Supporting utilities include live log capture, packet sniffing via `tcpdump`, and network emulation overlays through `tc netem` profiles.

```
           ____  _   _ _____     ___ ___ _____
          |  _ \| \ | |_   _|   |_ _/ _ \_   _|
          | | | |  \| | | |  ___ | | | | || |
          | |_| | |\  | | | |___|| | |_| || |
          |____/|_| \_| |_|      |_|\___/ |_|

               DNT IOT Playground
```

## Requirements

- Linux host with `tmux`, `python3`, and `bash`
- Optional: `stdbuf` for line-buffered logging
- For packet capture: `tcpdump`
- For network emulation: `ip`, `tc`, and (when not root) `sudo`

## Quick Start

```bash
# Start all configured clients (uses CLIENTS array or active config)
./tmux.sh start

# Attach to the tmux session to watch panes live
./tmux.sh attach

# Stop every client and clean up
./tmux.sh stop
```

No CLI arguments launches the interactive shell:

```bash
./tmux.sh
```

Inside the shell type `help` to list commands, then `exit` when you are done.

## CLI Commands

| Command | Description |
| --- | --- |
| `start [session]` | Start all configured clients, optionally overriding the session name |
| `stop [window]` | Stop the session entirely or a single client window |
| `attach [window]` | Attach to the session; optionally select a specific window first |
| `status` / `list` | Show tmux window, pane, and client state |
| `add <host> <port> <mac> <seed> <duration> [interval]` | Launch an additional client and add it to the in-memory list |
| `kill <window>` | Kill an individual tmux window by index, name, or seed |
| `restart <window>` | Restart a client using its stored definition |
| `logs …` | Manage tmux pane logging (see **Logging**) |
| `tcpdump …` | Manage packet captures (see **Packet Capture**) |
| `netem …` | Apply or inspect network emulation profiles (see **Network Emulation**) |
| `config …` | Load, inspect, or reset client definitions |
| `session …` | Switch session names or list running tmux sessions |
| `shell` | Launch the interactive shell from the CLI |

## Interactive Shell Notes

The shell mirrors the CLI features and adds contextual feedback. Commands accept the same arguments, so you can use `start`, `logs enable`, `netem apply test1`, etc. Arrow keys and Ctrl-R history search work because the shell uses `read` from `bash`.

## Logging

Pane output can be piped into timestamped log files.

```bash
./tmux.sh logs enable               # auto-creates logs/<session>/<stamp>/
./tmux.sh logs enable /tmp/mylogs    # custom directory
./tmux.sh logs status                # show file paths for each window
./tmux.sh logs path client_2         # print the path for a specific window
./tmux.sh logs disable               # stop piping output
```

Logs are stored under `LOG_ROOT/<session>/<timestamp>/client_<seed>.log`. When the tmux session stops, logging automatically tears down.

You can run `logs enable` before launching clients—the script arms the configuration and automatically wires panes to the selected directory as soon as the session spins up.

## Packet Capture

You can launch or arm a background `tcpdump` capture tied to the current session.

```bash
# Arm tcpdump so it starts automatically when clients launch
./tmux.sh tcpdump enable eth0 port 5000
./tmux.sh start

# Start immediately (use sudo or setcap if your user lacks capture privileges)
sudo ./tmux.sh tcpdump start eth0 --output ./captures/run.pcap port 80

# Inspect and stop
./tmux.sh tcpdump status
./tmux.sh tcpdump stop           # keeps the configuration armed
./tmux.sh tcpdump disable        # stop and forget the configuration
```

State is persisted to `logs/tcpdump/<session>.state`, so arming and status survive script restarts. Armed captures are started automatically the next time clients spin up, while `tcpdump disable` clears the configuration altogether.

**Note:** tcpdump typically requires elevated privileges. Arm or start captures with `sudo` (or grant the binary `cap_net_raw,cap_net_admin`) so the automatic launch succeeds when clients start.

## Network Emulation

Netem overlays apply latency, jitter, or packet loss to a chosen interface using `tc`. Set the default interface once, then apply profiles as needed.

```bash
sudo ./tmux.sh netem use eth0
sudo ./tmux.sh netem apply test1 2%                   # lossy profile
sudo ./tmux.sh netem apply test2 100ms 40ms normal    # delay + jitter profile
sudo ./tmux.sh netem apply custom delay 50ms          # pass raw tc netem args
./tmux.sh netem status
sudo ./tmux.sh netem clear                            # remove qdisc
```

Netem state is tracked in `logs/netem/<session>.state`. The script prevents switching sessions while an overlay is active to avoid leaving qdiscs behind.

## Configuration Management

You can describe clients in JSON instead of editing the script. Example file (`clients.json`):

```json
{
  "clients": [
    {"host": "127.0.0.1", "port": 5000, "mac": "AA:BB:CC:DD:EE:10", "seed": 10, "duration": 120},
    {"host": "192.168.0.5", "port": 6000, "mac": "AA:BB:CC:DD:EE:11", "seed": 11, "duration": 300, "interval": 0.5}
  ]
}
```

Load it at runtime:

```bash
./tmux.sh --config ./clients.json start
./tmux.sh config show
./tmux.sh config clear
```

The loader validates required fields and falls back to the built-in defaults if you clear the active configuration.

## Environment Overrides

| Variable | Default | Purpose |
| --- | --- | --- |
| `SESSION_NAME` | `client_session` | tmux session name |
| `PYTHON_CMD` | `python3` | Python executable used to launch clients |
| `CLIENT_SCRIPT` | `./main.py` | Entry point passed to Python |
| `DEFAULT_INTERVAL` | `1.0` | Default interval seconds if a client omits one |
| `CONFIG_FILE` | *(empty)* | JSON file loaded on startup (same as `--config`) |
| `LOG_ROOT` | `./logs` | Base directory for logs, captures, and state files |
| `NETEM_INTERFACE` | *(empty)* | Default interface for netem commands |
| `NETEM_TEST1_LOSS` | `5%` | Default loss for `netem apply test1` |
| `NETEM_TEST2_DELAY` | `120ms` | Base latency for `netem apply test2` |
| `NETEM_TEST2_JITTER` | `30ms` | Jitter added by `netem apply test2` |
| `NETEM_TEST2_DIST` | `normal` | Distribution passed to `tc netem` for test2 |

Use standard shell syntax to override:

```bash
LOG_ROOT=/var/log/clients SESSION_NAME=demo ./tmux.sh start
```

## Example Workflows

### 1. Smoke Test a New Build

```bash
./tmux.sh start
./tmux.sh attach             # monitor behaviour
./tmux.sh logs enable        # capture evidence
./tmux.sh status             # confirm every pane is running
./tmux.sh stop
```

### 2. Investigate Packet Loss

```bash
sudo ./tmux.sh netem use eth0
sudo ./tmux.sh netem apply test1 10%
./tmux.sh logs enable
./tmux.sh tcpdump enable eth0 port 5000
./tmux.sh start
./tmux.sh attach
# observe clients under loss conditions
./tmux.sh tcpdump stop
sudo ./tmux.sh netem clear
./tmux.sh stop
```

### 3. Rolling Restart with Logs

```bash
./tmux.sh start
./tmux.sh logs enable
./tmux.sh restart client_2   # or ./tmux.sh restart 2
./tmux.sh logs path client_2
./tmux.sh stop
```

## State Files and Cleanup

- `logs/tcpdump/<session>.state` tracks active captures and armed tcpdump settings
- `logs/netem/<session>.state` records the last applied netem profile
- log directories live under `LOG_ROOT/<session>/<timestamp>/`

These files refresh automatically when captures or overlays stop. Remove the parent `logs/` directory to reset everything.

## Troubleshooting

- `tmux not found` ⇒ install tmux or adjust `PATH`
- `Python executable 'python3' not found` ⇒ set `PYTHON_CMD`
- `sudo privileges required for tc netem operations` ⇒ run as root or configure passwordless sudo for `tc`
- `Interface '<iface>' not found` ⇒ verify the interface name via `ip link`