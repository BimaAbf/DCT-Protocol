#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}

# Static client launch parameters; override via environment variables if needed.
CLIENT_HOST=${CLIENT_HOST:-127.0.0.1}
CLIENT_PORT=${CLIENT_PORT:-5000}
CLIENT_INTERVAL=${CLIENT_INTERVAL:-1.0}
CLIENT_DURATION=${CLIENT_DURATION:-60.0}
CLIENT_MAC=${CLIENT_MAC:-AA:BB:CC:DD:EE:FF}
CLIENT_SEED=${CLIENT_SEED:-100}
CLIENT_BATCH_SIZE=${CLIENT_BATCH_SIZE:-1}
CLIENT_DELTA_THRESH=${CLIENT_DELTA_THRESH:-5}

if [[ $EUID -ne 0 ]]; then
	echo "This script must be run with sudo or as root so tcpdump can capture on lo." >&2
	exit 1
fi

for cmd in tmux tcpdump "$PYTHON_BIN"; do
	if ! command -v "$cmd" >/dev/null 2>&1; then
		echo "Required command '$cmd' was not found in PATH." >&2
		exit 1
	fi
done

SERVER_DIR="$SCRIPT_DIR/../Server"
CLIENT_DIR="$SCRIPT_DIR/../Client"
SERVER_MAIN="$SERVER_DIR/main.py"
CLIENT_MAIN="$CLIENT_DIR/main.py"

for file in "$SERVER_MAIN" "$CLIENT_MAIN"; do
	if [[ ! -f "$file" ]]; then
		echo "Expected file '$file' does not exist." >&2
		exit 1
	fi
done

if tmux has-session -t server_session 2>/dev/null; then
	echo "A tmux session named 'server_session' already exists." >&2
	exit 1
fi

if tmux has-session -t client_session 2>/dev/null; then
	echo "A tmux session named 'client_session' already exists." >&2
	exit 1
fi

RUN_ID=$(date +"%Y-%m-%d_%H-%M-%S")
RUN_DIR="$SCRIPT_DIR/Test_$RUN_ID"
mkdir -p "$RUN_DIR"

SERVER_LOG="$RUN_DIR/ServerTerminalOutput.txt"
CLIENT_LOG="$RUN_DIR/ClientTerminalOutput.txt"
TCPDUMP_STDERR="$RUN_DIR/tcpdump.log"
PCAP_FILE="$RUN_DIR/lo_capture.pcap"

: >"$SERVER_LOG"
: >"$CLIENT_LOG"
: >"$TCPDUMP_STDERR"

cleanup() {
	if tmux has-session -t client_session 2>/dev/null; then
		tmux kill-session -t client_session
	fi
	if tmux has-session -t server_session 2>/dev/null; then
		tmux kill-session -t server_session
	fi
	if [[ -n "${TCPDUMP_PID:-}" ]] && kill -0 "$TCPDUMP_PID" 2>/dev/null; then
		kill "$TCPDUMP_PID"
		wait "$TCPDUMP_PID" 2>/dev/null || true
	fi
}

trap cleanup EXIT

tcpdump -i lo -s 0 -w "$PCAP_FILE" >/dev/null 2>"$TCPDUMP_STDERR" &
TCPDUMP_PID=$!

tmux new-session -d -s server_session
tmux pipe-pane -o -t server_session "cat >> '$SERVER_LOG'"
tmux send-keys -t server_session "cd '$SERVER_DIR'" C-m
tmux send-keys -t server_session "exec $PYTHON_BIN main.py" C-m

sleep 1

tmux new-session -d -s client_session
tmux pipe-pane -o -t client_session "cat >> '$CLIENT_LOG'"
tmux send-keys -t client_session "cd '$CLIENT_DIR'" C-m

CLIENT_CMD=()
CLIENT_CMD+=("$PYTHON_BIN" "main.py" "$CLIENT_HOST" "--port" "$CLIENT_PORT" "--interval" "$CLIENT_INTERVAL" "--duration" "$CLIENT_DURATION" "--mac" "$CLIENT_MAC" "--seed" "$CLIENT_SEED" "--batching" "$CLIENT_BATCH_SIZE" "--delta-thresh" "$CLIENT_DELTA_THRESH")
printf -v CLIENT_CMD_STR '%q ' "${CLIENT_CMD[@]}"
CLIENT_CMD_STR=${CLIENT_CMD_STR% }
tmux send-keys -t client_session "exec ${CLIENT_CMD_STR}" C-m

while tmux has-session -t client_session 2>/dev/null; do
	sleep 1
done

cleanup
trap - EXIT

echo "Logs saved under $RUN_DIR"
