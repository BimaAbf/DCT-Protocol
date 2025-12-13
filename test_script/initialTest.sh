set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}

CLIENT_HOST=${CLIENT_HOST:-127.0.0.1}
CLIENT_PORT=${CLIENT_PORT:-5000}
CLIENT_INTERVAL=${CLIENT_INTERVAL:-1.0}
CLIENT_DURATION=${CLIENT_DURATION:-60.0}
CLIENT_BATCH_SIZE=${CLIENT_BATCH_SIZE:-1}
CLIENT_DELTA_THRESH=${CLIENT_DELTA_THRESH:-5}

declare -a CLIENT_SEED_LIST
if [[ -z "${CLIENT_SEEDS:-}" ]]; then
	CLIENT_SEED_LIST=(100 101 102 103 104)
else
	read -r -a CLIENT_SEED_LIST <<< "${CLIENT_SEEDS}"
fi

declare -a CLIENT_MAC_LIST
if [[ -z "${CLIENT_MACS:-}" ]]; then
	CLIENT_MAC_LIST=(AA:BB:CC:DD:EE:01 AA:BB:CC:DD:EE:02 AA:BB:CC:DD:EE:03 AA:BB:CC:DD:EE:04 AA:BB:CC:DD:EE:05)
else
	read -r -a CLIENT_MAC_LIST <<< "${CLIENT_MACS}"
fi

if [[ ${#CLIENT_SEED_LIST[@]} -eq 0 ]]; then
	echo "CLIENT_SEEDS produced an empty list; provide at least one seed." >&2
	exit 1
fi

if [[ ${#CLIENT_SEED_LIST[@]} -ne ${#CLIENT_MAC_LIST[@]} ]]; then
	echo "Mismatch between CLIENT_SEEDS (${#CLIENT_SEED_LIST[@]}) and CLIENT_MACS (${#CLIENT_MAC_LIST[@]})." >&2
	exit 1
fi

CLIENT_COUNT=${#CLIENT_SEED_LIST[@]}
declare -a CLIENT_SESSIONS=()

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

for idx in "${!CLIENT_SEED_LIST[@]}"; do
	session_name=$(printf "client_session_%02d" "$((idx + 1))")
	if tmux has-session -t "$session_name" 2>/dev/null; then
		echo "A tmux session named '$session_name' already exists." >&2
		exit 1
	fi
done

RUN_ID=$(date +"%Y-%m-%d_%H-%M-%S")
RUN_DIR="$SCRIPT_DIR/Test_$RUN_ID"
mkdir -p "$RUN_DIR"

SERVER_LOG="$RUN_DIR/ServerTerminalOutput.txt"
CLIENT_LOG="$RUN_DIR/ClientTerminalOutput.txt"
TCPDUMP_STDERR="$RUN_DIR/tcpdump.log"
PCAP_FILE="$RUN_DIR/lo_capture.pcap"

: >"$SERVER_LOG"
: >"$TCPDUMP_STDERR"
: >"$CLIENT_LOG"

cleanup() {
	for session in "${CLIENT_SESSIONS[@]}"; do
		if tmux has-session -t "$session" 2>/dev/null; then
			tmux kill-session -t "$session"
		fi
	done
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

for idx in "${!CLIENT_SEED_LIST[@]}"; do

	session_name=$(printf "client_session_%02d" "$((idx + 1))")
	client_log=$(printf "%s/Client%02d_TerminalOutput.txt" "$RUN_DIR" "$((idx + 1))")

	seed=${CLIENT_SEED_LIST[$idx]}
	mac=${CLIENT_MAC_LIST[$idx]}

	: >"$client_log"

	tmux new-session -d -s "$session_name"
	tmux pipe-pane -o -t "$session_name" "cat >> '$client_log'"
	tmux send-keys -t "$session_name" "cd '$CLIENT_DIR'" C-m

	CLIENT_CMD=("$PYTHON_BIN" "main.py" "$CLIENT_HOST" "--port" "$CLIENT_PORT" "--interval" "$CLIENT_INTERVAL" "--duration" "$CLIENT_DURATION" "--mac" "$mac" "--seed" "$seed" "--batching" "$CLIENT_BATCH_SIZE" "--delta-thresh" "$CLIENT_DELTA_THRESH")
	printf -v CLIENT_CMD_STR '%q ' "${CLIENT_CMD[@]}"

	CLIENT_CMD_STR=${CLIENT_CMD_STR% }

	tmux send-keys -t "$session_name" "exec ${CLIENT_CMD_STR}" C-m

	CLIENT_SESSIONS+=("$session_name")
	sleep 0.5
done

while :; do

	active=0
	for session in "${CLIENT_SESSIONS[@]}"; do

		if tmux has-session -t "$session" 2>/dev/null; then
			active=1
			break

		fi

	done

	if [[ $active -eq 0 ]]; then
		break
	fi

	sleep 1

done

{
	for idx in "${!CLIENT_SEED_LIST[@]}"; do

		client_log=$(printf "%s/Client%02d_TerminalOutput.txt" "$RUN_DIR" "$((idx + 1))")
		seed=${CLIENT_SEED_LIST[$idx]}
		printf '===== client %02d (seed %s) =====\n' "$((idx + 1))" "$seed"

		if [[ -f "$client_log" ]]; then
			cat "$client_log"
		fi
		printf '\n'

	done

} >"$CLIENT_LOG"

METRICS_SCRIPT="$SCRIPT_DIR/../Analysis/metrics.py"
if [[ -f "$METRICS_SCRIPT" ]]; then
	if ! "$PYTHON_BIN" "$METRICS_SCRIPT" --output "$RUN_DIR/metrics.csv"; then
		echo "Metric extraction failed" >&2
	fi
else
	echo "Warning: metrics script not found at $METRICS_SCRIPT" >&2
fi

cleanup
trap - EXIT

echo "Logs saved under $RUN_DIR"