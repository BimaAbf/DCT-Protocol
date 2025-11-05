#!/bin/bash

# Client Session Playground utilities for managing tmux-based client instances.

set -o pipefail

SCRIPT_NAME=$(basename "$0")
SESSION_NAME=${SESSION_NAME:-client_session}
PYTHON_CMD=${PYTHON_CMD:-python3}
CLIENT_SCRIPT=${CLIENT_SCRIPT:-./main.py}
DEFAULT_INTERVAL=${DEFAULT_INTERVAL:-1.0}
CONFIG_FILE=${CONFIG_FILE:-}
LOG_ROOT=${LOG_ROOT:-./logs}
LOGGING_ENABLED=0
LOG_SESSION_DIR=""

TCPDUMP_ENABLED=0
TCPDUMP_PID=""
TCPDUMP_INTERFACE=""
TCPDUMP_FILTER=""
TCPDUMP_FILE=""
TCPDUMP_STARTED=""
TCPDUMP_LOG=""
TCPDUMP_STATE_FILE=""
TCPDUMP_ARMED=0
TCPDUMP_ARMED_INTERFACE=""
TCPDUMP_ARMED_OUTPUT=""
TCPDUMP_ARMED_FILTER=""

NETEM_INTERFACE_DEFAULT=${NETEM_INTERFACE:-}
NETEM_INTERFACE="$NETEM_INTERFACE_DEFAULT"
NETEM_ENABLED=0
NETEM_PROFILE=""
NETEM_ARGS=""
NETEM_DESCRIPTION=""
NETEM_APPLIED=""
NETEM_STATE_FILE=""

NETEM_TEST1_LOSS=${NETEM_TEST1_LOSS:-5%}
NETEM_TEST2_DELAY=${NETEM_TEST2_DELAY:-120ms}
NETEM_TEST2_JITTER=${NETEM_TEST2_JITTER:-30ms}
NETEM_TEST2_DIST=${NETEM_TEST2_DIST:-normal}

PYTHON_BIN=""
CLIENT_PATH=""
ACTIVE_CONFIG=""

PIPE_CAT_CMD="cat"
if command -v stdbuf >/dev/null 2>&1; then
    PIPE_CAT_CMD="stdbuf -oL cat"
fi

# Each entry: host|port|mac|seed|duration(seconds)[|interval]
CLIENTS=(
    "127.0.0.1|5000|AA:BB:CC:DD:EE:00|0|300"
    "127.0.0.1|5000|AA:BB:CC:DD:EE:01|1|300"
    "127.0.0.1|5000|AA:BB:CC:DD:EE:02|2|300"
    "127.0.0.1|5000|AA:BB:CC:DD:EE:03|3|300"
    "127.0.0.1|5000|AA:BB:CC:DD:EE:04|4|300"
)
DEFAULT_CLIENTS=("${CLIENTS[@]}")

usage() {
    cat <<EOF
Usage: $SCRIPT_NAME [options] {start|stop|attach|status|list|add|kill|restart|logs|tcpdump|netem|session|shell}

No arguments launch the interactive shell.

Options:
  -s, --session <name>          Override the tmux session name for this run
  -c, --config <path>           Load client definitions from JSON file
  -h, --help                    Show this help message and exit

Environment overrides:
    SESSION_NAME                  tmux session name (default: client_session)
    PYTHON_CMD                    Python executable      (default: python3)
    CLIENT_SCRIPT                 Client entry point     (default: ./main.py)
    DEFAULT_INTERVAL              Interval seconds       (default: 1.0)
    CONFIG_FILE                   Path to JSON config describing clients
    LOG_ROOT                      Base directory for logs and captures (default: ./logs)
    NETEM_INTERFACE               Default network interface for netem (optional)
    NETEM_TEST1_LOSS              Default loss for test1 profile (default: 5%)
    NETEM_TEST2_DELAY             Base delay for test2 profile (default: 120ms)
    NETEM_TEST2_JITTER            Jitter for test2 profile (default: 30ms)
    NETEM_TEST2_DIST              Distribution for test2 profile (default: normal)
EOF
}

require_tmux() {
    if command -v tmux >/dev/null 2>&1; then
        return 0
    fi
    echo "tmux is required but was not found in PATH." >&2
    return 1
}

resolve_client_script() {
    local resolved
    if ! resolved=$(realpath "$CLIENT_SCRIPT" 2>/dev/null); then
        echo "Unable to resolve client script path: $CLIENT_SCRIPT" >&2
        return 1
    fi
    if [ ! -f "$resolved" ]; then
        echo "Client script not found at: $resolved" >&2
        return 1
    fi
    echo "$resolved"
}

reset_tcpdump_state() {
    TCPDUMP_ENABLED=0
    TCPDUMP_PID=""
    TCPDUMP_INTERFACE=""
    TCPDUMP_FILTER=""
    TCPDUMP_FILE=""
    TCPDUMP_STARTED=""
    TCPDUMP_LOG=""
}

clear_tcpdump_state_file() {
    if [ -n "$TCPDUMP_STATE_FILE" ] && [ -f "$TCPDUMP_STATE_FILE" ]; then
        rm -f "$TCPDUMP_STATE_FILE"
    fi
}

write_tcpdump_state() {
    if [ -z "$TCPDUMP_STATE_FILE" ]; then
        return 0
    fi
    mkdir -p "$(dirname "$TCPDUMP_STATE_FILE")"
    {
        printf 'TCPDUMP_ENABLED=%q\n' "$TCPDUMP_ENABLED"
        printf 'TCPDUMP_PID=%q\n' "$TCPDUMP_PID"
        printf 'TCPDUMP_INTERFACE=%q\n' "$TCPDUMP_INTERFACE"
        printf 'TCPDUMP_FILTER=%q\n' "$TCPDUMP_FILTER"
        printf 'TCPDUMP_FILE=%q\n' "$TCPDUMP_FILE"
        printf 'TCPDUMP_STARTED=%q\n' "$TCPDUMP_STARTED"
        printf 'TCPDUMP_LOG=%q\n' "$TCPDUMP_LOG"
        printf 'TCPDUMP_ARMED=%q\n' "$TCPDUMP_ARMED"
        printf 'TCPDUMP_ARMED_INTERFACE=%q\n' "$TCPDUMP_ARMED_INTERFACE"
        printf 'TCPDUMP_ARMED_OUTPUT=%q\n' "$TCPDUMP_ARMED_OUTPUT"
        printf 'TCPDUMP_ARMED_FILTER=%q\n' "$TCPDUMP_ARMED_FILTER"
    } >"$TCPDUMP_STATE_FILE"
    return 0
}

init_tcpdump_state() {
    local base_dir="$LOG_ROOT/tcpdump"
    TCPDUMP_STATE_FILE="$base_dir/${SESSION_NAME}.state"

    TCPDUMP_ARMED=0
    TCPDUMP_ARMED_INTERFACE=""
    TCPDUMP_ARMED_OUTPUT=""
    TCPDUMP_ARMED_FILTER=""
    if [ ! -f "$TCPDUMP_STATE_FILE" ]; then
        reset_tcpdump_state
        return 0
    fi

    reset_tcpdump_state
    # shellcheck disable=SC1090
    . "$TCPDUMP_STATE_FILE"

    TCPDUMP_ARMED=${TCPDUMP_ARMED:-0}
    TCPDUMP_ARMED_INTERFACE=${TCPDUMP_ARMED_INTERFACE:-}
    TCPDUMP_ARMED_OUTPUT=${TCPDUMP_ARMED_OUTPUT:-}
    TCPDUMP_ARMED_FILTER=${TCPDUMP_ARMED_FILTER:-}

    if [ -n "$TCPDUMP_PID" ] && kill -0 "$TCPDUMP_PID" 2>/dev/null; then
        TCPDUMP_ENABLED=1
        return 0
    fi

    reset_tcpdump_state
    write_tcpdump_state
    return 0
}

require_tcpdump() {
    if command -v tcpdump >/dev/null 2>&1; then
        return 0
    fi
    echo "tcpdump is required for this action but was not found." >&2
    return 1
}

prepare_tcpdump_parameters() {
    if ! require_tcpdump; then
        return 1
    fi

    if [ -z "$1" ]; then
        echo "Usage: tcpdump <start|enable> <interface> [--output <file>] [filter ...]" >&2
        return 1
    fi

    local interface=$1
    shift

    local output=""
    local filter_args=()
    while [ $# -gt 0 ]; do
        case "$1" in
            -o|--output)
                if [ -z "${2:-}" ]; then
                    echo "--output requires a file path." >&2
                    return 1
                fi
                output=$2
                shift 2
                ;;
            --)
                shift
                while [ $# -gt 0 ]; do
                    filter_args+=("$1")
                    shift
                done
                ;;
            *)
                filter_args+=("$1")
                shift
                ;;
        esac
    done

    TCPDUMP_ARMED=1
    TCPDUMP_ARMED_INTERFACE=$interface
    TCPDUMP_ARMED_OUTPUT=$output
    TCPDUMP_ARMED_FILTER="${filter_args[*]}"
    write_tcpdump_state
    return 0
}

launch_tcpdump_from_armed() {
    if ! require_tcpdump; then
        return 1
    fi

    if [ "$TCPDUMP_ENABLED" -eq 1 ] && [ -n "$TCPDUMP_PID" ] && kill -0 "$TCPDUMP_PID" 2>/dev/null; then
        echo "tcpdump already running (pid=$TCPDUMP_PID on $TCPDUMP_INTERFACE)." >&2
        return 1
    fi

    if [ "$TCPDUMP_ARMED" -ne 1 ] || [ -z "$TCPDUMP_ARMED_INTERFACE" ]; then
        echo "tcpdump is not armed. Use 'tcpdump enable <interface>' first." >&2
        return 1
    fi

    local interface=$TCPDUMP_ARMED_INTERFACE
    local output=$TCPDUMP_ARMED_OUTPUT
    local filter_string=$TCPDUMP_ARMED_FILTER

    local stamp
    stamp=$(date +%Y%m%d-%H%M%S)
    local base_dir="$LOG_ROOT/tcpdump/$SESSION_NAME"
    mkdir -p "$base_dir"

    local final_output="$output"
    if [ -z "$final_output" ]; then
        final_output="$base_dir/$stamp.pcap"
    else
        mkdir -p "$(dirname "$final_output")"
    fi

    local log_file="$base_dir/$stamp.log"

    local cmd=(tcpdump -i "$interface" -U -w "$final_output")
    if [ -n "$filter_string" ]; then
        local filter_args=()
        # shellcheck disable=SC2206
        filter_args=($filter_string)
        cmd+=("${filter_args[@]}")
    fi

    nohup "${cmd[@]}" >"$log_file" 2>&1 &
    local launch_status=$?
    local pid=$!
    if [ $launch_status -ne 0 ]; then
        echo "Failed to launch tcpdump." >&2
        return 1
    fi

    sleep 1
    if ! kill -0 "$pid" 2>/dev/null; then
        wait "$pid" 2>/dev/null || true
        echo "tcpdump failed to start. Review $log_file for details." >&2
        return 1
    fi

    TCPDUMP_ENABLED=1
    TCPDUMP_PID=$pid
    TCPDUMP_INTERFACE=$interface
    TCPDUMP_FILTER="$filter_string"
    TCPDUMP_FILE="$final_output"
    TCPDUMP_STARTED=$(date +%Y-%m-%dT%H:%M:%S%z)
    TCPDUMP_LOG="$log_file"
    write_tcpdump_state

    echo "tcpdump started (pid=$pid interface=$interface output=$final_output)"
    if [ -n "$filter_string" ]; then
        echo "  filter: $filter_string"
    fi
    echo "  log: $log_file"
    return 0
}

maybe_start_armed_tcpdump() {
    if [ "$TCPDUMP_ARMED" -ne 1 ]; then
        return 0
    fi
    if [ "$TCPDUMP_ENABLED" -eq 1 ]; then
        return 0
    fi

    if ! launch_tcpdump_from_armed; then
        return 1
    fi

    return 0
}

start_tcpdump_capture() {
    if ! prepare_tcpdump_parameters "$@"; then
        return 1
    fi

    if ! launch_tcpdump_from_armed; then
        return 1
    fi

    return 0
}

tcpdump_enable() {
    if ! prepare_tcpdump_parameters "$@"; then
        return 1
    fi

    if [ "$TCPDUMP_ENABLED" -eq 1 ]; then
        echo "tcpdump already running (pid=$TCPDUMP_PID on $TCPDUMP_INTERFACE)." >&2
        return 1
    fi

    echo "tcpdump armed. Capture will start automatically when the session runs."
    if [ -n "$TCPDUMP_ARMED_OUTPUT" ]; then
        echo "  output: $TCPDUMP_ARMED_OUTPUT"
    else
        echo "  output: (auto timestamped under $LOG_ROOT/tcpdump/$SESSION_NAME)"
    fi
    if [ -n "$TCPDUMP_ARMED_FILTER" ]; then
        echo "  filter: $TCPDUMP_ARMED_FILTER"
    fi
    return 0
}

tcpdump_disable() {
    TCPDUMP_ARMED=0
    TCPDUMP_ARMED_INTERFACE=""
    TCPDUMP_ARMED_OUTPUT=""
    TCPDUMP_ARMED_FILTER=""

    if [ "$TCPDUMP_ENABLED" -eq 1 ]; then
        if ! stop_tcpdump_capture; then
            return 1
        fi
    else
        reset_tcpdump_state
        write_tcpdump_state
    fi

    if [ "$TCPDUMP_ENABLED" -eq 0 ]; then
        if [ -n "$TCPDUMP_STATE_FILE" ] && [ -f "$TCPDUMP_STATE_FILE" ]; then
            if [ "$TCPDUMP_ARMED" -eq 0 ]; then
                clear_tcpdump_state_file
            fi
        fi
    fi

    echo "tcpdump disarmed."
    return 0
}

stop_tcpdump_capture() {
    if [ "$TCPDUMP_ENABLED" -eq 1 ] && [ -n "$TCPDUMP_PID" ] && kill -0 "$TCPDUMP_PID" 2>/dev/null; then
        if ! kill "$TCPDUMP_PID" 2>/dev/null; then
            echo "Failed to stop tcpdump (pid=$TCPDUMP_PID)." >&2
            return 1
        fi
        wait "$TCPDUMP_PID" 2>/dev/null || true
        echo "tcpdump stopped (pid=$TCPDUMP_PID)."
    elif [ "$TCPDUMP_ENABLED" -eq 1 ]; then
        echo "tcpdump process not found; cleaning up stale state." >&2
    else
        echo "tcpdump is not running."
    fi

    reset_tcpdump_state
    write_tcpdump_state

    if [ "$TCPDUMP_ARMED" -eq 1 ]; then
        echo "tcpdump remains armed with interface $TCPDUMP_ARMED_INTERFACE."
    fi
    return 0
}

tcpdump_status() {
    if [ "$TCPDUMP_ENABLED" -eq 1 ] && [ -n "$TCPDUMP_PID" ] && kill -0 "$TCPDUMP_PID" 2>/dev/null; then
        echo "tcpdump: running"
        echo "  pid: $TCPDUMP_PID"
        echo "  interface: $TCPDUMP_INTERFACE"
        echo "  output: $TCPDUMP_FILE"
        if [ -n "$TCPDUMP_FILTER" ]; then
            echo "  filter: $TCPDUMP_FILTER"
        fi
        if [ -n "$TCPDUMP_LOG" ]; then
            echo "  log: $TCPDUMP_LOG"
        fi
        if [ -n "$TCPDUMP_STARTED" ]; then
            echo "  started: $TCPDUMP_STARTED"
        fi
        if [ "$TCPDUMP_ARMED" -eq 1 ]; then
            echo "  armed: yes (interface $TCPDUMP_ARMED_INTERFACE)"
        else
            echo "  armed: no"
        fi
        return 0
    fi

    echo "tcpdump: not running"
    if [ -n "$TCPDUMP_PID" ] && ! kill -0 "$TCPDUMP_PID" 2>/dev/null; then
        reset_tcpdump_state
        write_tcpdump_state
    fi
    if [ "$TCPDUMP_ARMED" -eq 1 ]; then
        echo "  armed: yes"
        echo "  interface: ${TCPDUMP_ARMED_INTERFACE:-unset}"
        if [ -n "$TCPDUMP_ARMED_OUTPUT" ]; then
            echo "  next-output: $TCPDUMP_ARMED_OUTPUT"
        else
            echo "  next-output: (auto timestamped under $LOG_ROOT/tcpdump/$SESSION_NAME)"
        fi
        if [ -n "$TCPDUMP_ARMED_FILTER" ]; then
            echo "  filter: $TCPDUMP_ARMED_FILTER"
        fi
    else
        echo "  armed: no"
    fi
    return 0
}

ensure_runtime_dependencies() {
    if ! require_tmux; then
        return 1
    fi
    if [ -z "$PYTHON_BIN" ]; then
        if ! PYTHON_BIN=$(command -v "$PYTHON_CMD" 2>/dev/null); then
            echo "Python executable '$PYTHON_CMD' not found in PATH." >&2
            return 1
        fi
    fi
    if [ -z "$CLIENT_PATH" ]; then
        if ! CLIENT_PATH=$(resolve_client_script); then
            return 1
        fi
    fi
    return 0
}

quote_cmd() {
    local chunk=""
    local arg
    for arg in "$@"; do
        chunk+="$(printf '%q ' "$arg")"
    done
    echo "${chunk% }"
}

ensure_session_exists() {
    if ! require_tmux; then
        return 1
    fi
    if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "Session '$SESSION_NAME' is not running." >&2
        return 1
    fi
    return 0
}

resolve_window_target() {
    local target=$1
    if [ -z "$target" ]; then
        echo "Usage requires a window identifier." >&2
        return 1
    fi
    local match=""
    while IFS='|' read -r idx name; do
        local seed_hint=${name#client_}
        if [ "$target" = "$idx" ] || [ "$target" = "$name" ] || [ "$target" = "$seed_hint" ]; then
            match="$idx|$name"
            break
        fi
    done < <(tmux list-windows -t "$SESSION_NAME" -F "#{window_index}|#{window_name}")

    if [ -z "$match" ]; then
        echo "No matching client/window for '$target'." >&2
        return 1
    fi

    echo "$match"
    return 0
}

sanitize_filename() {
    local value=${1:-window}
    value=${value//[^A-Za-z0-9._-]/_}
    echo "$value"
}

log_file_for_window() {
    local window_name=$1
    local safe
    safe=$(sanitize_filename "$window_name")
    echo "$LOG_SESSION_DIR/${safe}.log"
}

apply_logging_to_window() {
    local idx=$1
    local name=$2

    if [ "$LOGGING_ENABLED" -ne 1 ] || [ -z "$LOG_SESSION_DIR" ]; then
        return 0
    fi

    mkdir -p "$LOG_SESSION_DIR"
    local file
    file=$(log_file_for_window "$name")

    tmux pipe-pane -t "${SESSION_NAME}:$idx" 2>/dev/null
    if tmux pipe-pane -t "${SESSION_NAME}:$idx" -O "exec $PIPE_CAT_CMD >> '$file'"; then
        echo "Logging window $name (#$idx) -> $file"
        return 0
    fi

    echo "Failed to enable logging for $name (#$idx)." >&2
    return 1
}

remove_logging_from_window() {
    local idx=$1
    tmux pipe-pane -t "${SESSION_NAME}:$idx" 2>/dev/null
}

resolve_python_for_config() {
    local interpreter
    if interpreter=$(command -v "$PYTHON_CMD" 2>/dev/null); then
        echo "$interpreter"
        return 0
    fi
    if interpreter=$(command -v python3 2>/dev/null); then
        echo "$interpreter"
        return 0
    fi
    echo "Unable to locate Python interpreter for parsing config." >&2
    return 1
}

load_config_file() {
    local config_path=$1
    if [ -z "$config_path" ]; then
        echo "Usage: config use <path-to-json>" >&2
        return 1
    fi
    if [ ! -f "$config_path" ]; then
        echo "Config file not found: $config_path" >&2
        return 1
    fi

    local interpreter
    if ! interpreter=$(resolve_python_for_config); then
        return 1
    fi

    local parsed
    if ! parsed=$("$interpreter" - "$config_path" <<'PY'
import json, sys

path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as fh:
    data = json.load(fh)

clients = data if isinstance(data, list) else data.get('clients', [])
if not isinstance(clients, list):
    raise ValueError('`clients` must be a list')

lines = []
for idx, entry in enumerate(clients):
    if not isinstance(entry, dict):
        raise ValueError(f'Client #{idx} must be an object')
    try:
        host = entry['host']
        port = entry['port']
        mac = entry['mac']
        seed = entry['seed']
        duration = entry['duration']
    except KeyError as missing:
        raise ValueError(f'Client #{idx} missing field: {missing}')

    interval = entry.get('interval', '')
    lines.append(f"{host}|{port}|{mac}|{seed}|{duration}|{interval}")

print("\n".join(lines))
PY
    ); then
        local status=$?
        echo "Failed to parse client config: $config_path" >&2
        return $status
    fi

    local new_clients=()
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        new_clients+=("$line")
    done <<<"$parsed"

    if [ "${#new_clients[@]}" -eq 0 ]; then
        echo "Config file produced no clients: $config_path" >&2
        return 1
    fi

    CLIENTS=("${new_clients[@]}")
    ACTIVE_CONFIG=$(realpath "$config_path" 2>/dev/null || echo "$config_path")
    CONFIG_FILE="$config_path"
    echo "Loaded ${#CLIENTS[@]} clients from $ACTIVE_CONFIG"
    return 0
}

reset_to_default_clients() {
    CLIENTS=("${DEFAULT_CLIENTS[@]}")
    ACTIVE_CONFIG=""
    CONFIG_FILE=""
    echo "Reverted to embedded client list (${#CLIENTS[@]} entries)."
    return 0
}

show_active_config() {
    if [ -n "$ACTIVE_CONFIG" ]; then
        echo "Active config file: $ACTIVE_CONFIG"
    else
        echo "Active config file: (embedded defaults)"
    fi
    echo "Client definitions (${#CLIENTS[@]}):"
    local idx=0
    for entry in "${CLIENTS[@]}"; do
        IFS='|' read -r host port mac seed duration interval <<<"$entry"
        printf "  #%d host=%s port=%s mac=%s seed=%s duration=%s interval=%s\n" \
            "$idx" "$host" "$port" "$mac" "$seed" "$duration" "${interval:-$DEFAULT_INTERVAL}"
        idx=$((idx + 1))
    done
    return 0
}

set_session_name() {
    local new_name=$1
    if [ -z "$new_name" ]; then
        echo "Usage: session use <name>" >&2
        return 1
    fi
    if [ "$TCPDUMP_ENABLED" -eq 1 ] && [ -n "$TCPDUMP_PID" ] && kill -0 "$TCPDUMP_PID" 2>/dev/null; then
        echo "Stop the active tcpdump capture before switching sessions." >&2
        return 1
    fi
    if [ "$NETEM_ENABLED" -eq 1 ]; then
        echo "Clear the active netem profile before switching sessions." >&2
        return 1
    fi
    SESSION_NAME="$new_name"
    echo "Using session '$SESSION_NAME'."
    init_tcpdump_state
    init_netem_state
    return 0
}

launch_client_window() {
    local host=$1
    local port=$2
    local mac=$3
    local seed=$4
    local duration=$5
    local interval=${6:-$DEFAULT_INTERVAL}
    local append=${7:-0}

    if [ -z "$host" ] || [ -z "$port" ] || [ -z "$mac" ] || [ -z "$seed" ] || [ -z "$duration" ]; then
        echo "Incomplete client definition (host/port/mac/seed/duration required)." >&2
        return 1
    fi

    if ! ensure_runtime_dependencies; then
        return 1
    fi

    local window="client_${seed}"
    local cmd=("$PYTHON_BIN" "$CLIENT_PATH" "$host" --port "$port" --mac "$mac" --seed "$seed" --duration "$duration" --interval "$interval")

    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        if ! tmux new-window -t "${SESSION_NAME}:" -n "$window" "$(quote_cmd "${cmd[@]}")"; then
            echo "Failed to start tmux window for $window." >&2
            return 1
        fi
    else
        echo "Session '$SESSION_NAME' is not running. Creating it now..."
        if ! tmux new-session -d -s "$SESSION_NAME" -n "$window" "$(quote_cmd "${cmd[@]}")"; then
            echo "Failed to create tmux session '$SESSION_NAME'." >&2
            return 1
        fi
    fi

    echo "Started $window -> $host:$port (mac=$mac seed=$seed duration=${duration}s interval=${interval}s)"

    if [ "$append" -eq 1 ]; then
        CLIENTS+=("$host|$port|$mac|$seed|$duration|$interval")
    fi

    if [ "$LOGGING_ENABLED" -eq 1 ] && [ -n "$LOG_SESSION_DIR" ]; then
        local idx
        idx=$(tmux display-message -pt "${SESSION_NAME}:$window" '#I' 2>/dev/null)
        if [ -n "$idx" ]; then
            apply_logging_to_window "$idx" "$window"
        fi
    fi

    return 0
}

create_client_window() {
    local host=$1
    local port=$2
    local mac=$3
    local seed=$4
    local duration=$5
    local interval=${6:-$DEFAULT_INTERVAL}

    if [ -z "$host" ] || [ -z "$port" ] || [ -z "$mac" ] || [ -z "$seed" ] || [ -z "$duration" ]; then
        echo "Usage: add <host> <port> <mac> <seed> <duration> [interval]" >&2
        return 1
    fi

    launch_client_window "$host" "$port" "$mac" "$seed" "$duration" "$interval" 1
}

start_clients() {
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "Session '$SESSION_NAME' already exists." >&2
        return 1
    fi
    if ! ensure_runtime_dependencies; then
        return 1
    fi

    if ! maybe_start_armed_tcpdump; then
        echo "Failed to start armed tcpdump capture. Aborting client launch." >&2
        return 1
    fi

    echo "Launching clients into tmux session '$SESSION_NAME'..."
    local count=0
    local entry
    for entry in "${CLIENTS[@]}"; do
        IFS='|' read -r host port mac seed duration interval <<<"$entry"
        if [ -z "$host" ] || [ -z "$port" ] || [ -z "$mac" ] || [ -z "$seed" ] || [ -z "$duration" ]; then
            echo "Skipping malformed client entry: $entry" >&2
            continue
        fi
        local interval_to_use=${interval:-$DEFAULT_INTERVAL}
        if launch_client_window "$host" "$port" "$mac" "$seed" "$duration" "$interval_to_use" 0; then
            count=$((count + 1))
        fi
    done

    if [ "$count" -eq 0 ]; then
        echo "No clients launched. Check CLIENTS array." >&2
        tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
        return 1
    fi

    echo "All clients are running in tmux session '$SESSION_NAME'."
    echo "Use '$SCRIPT_NAME attach' or 'attach' inside the shell to watch them."
    return 0
}

stop_clients() {
    if ! require_tmux; then
        return 1
    fi
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        if [ "$TCPDUMP_ENABLED" -eq 1 ]; then
            stop_tcpdump_capture || true
        fi
        if [ "$LOGGING_ENABLED" -eq 1 ]; then
            disable_logging >/dev/null 2>&1 || true
        fi
        tmux kill-session -t "$SESSION_NAME"
        echo "Session '$SESSION_NAME' stopped."
    else
        echo "Session '$SESSION_NAME' is not running."
    fi
    return 0
}

attach_clients() {
    local target=${1:-}
    if ! ensure_session_exists; then
        return 1
    fi

    if [ -n "$target" ]; then
        local resolved
        if ! resolved=$(resolve_window_target "$target"); then
            return 1
        fi
        IFS='|' read -r idx name <<<"$resolved"
        if ! tmux select-window -t "${SESSION_NAME}:$idx"; then
            echo "Unable to focus window $name (#$idx)." >&2
            return 1
        fi
        echo "Attaching to $name (#$idx) in session '$SESSION_NAME'..."
    else
        echo "Attaching to session '$SESSION_NAME'..."
    fi

    tmux attach -t "$SESSION_NAME"
    return $?
}

stop_client_window() {
    local target=$1
    if [ -z "$target" ]; then
        echo "Usage: stop <window-index|name|seed>" >&2
        return 1
    fi
    if ! ensure_session_exists; then
        return 1
    fi

    local resolved
    if ! resolved=$(resolve_window_target "$target"); then
        return 1
    fi

    IFS='|' read -r idx name <<<"$resolved"

    if tmux kill-window -t "${SESSION_NAME}:$idx" 2>/dev/null; then
        echo "Stopped window $name (#$idx)."
        return 0
    fi

    echo "Failed to stop window $name (#$idx)." >&2
    return 1
}

list_clients() {
    if ! require_tmux; then
        return 1
    fi
    if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "Session '$SESSION_NAME' is not running."
        return 1
    fi

    local window_count
    window_count=$(tmux list-windows -t "$SESSION_NAME" 2>/dev/null | wc -l | tr -d ' ')
    local attached_count
    attached_count=$(tmux list-clients -t "$SESSION_NAME" 2>/dev/null | wc -l | tr -d ' ')

    echo "Session '$SESSION_NAME' -> windows=$window_count attached=$attached_count"
    if [ "$attached_count" -eq 0 ]; then
        echo "  (no tmux clients currently attached; use 'attach' to watch live output)"
    fi

    tmux list-windows -t "$SESSION_NAME" -F "#{window_index}|#{window_name}|#{window_active}|#{window_panes}" | while IFS='|' read -r idx name active panes; do
        local pane_info
        pane_info=$(tmux list-panes -t "${SESSION_NAME}:$idx" -F "#{pane_index}|#{pane_current_command}|#{pane_pid}|#{pane_dead}" | head -n1)
        IFS='|' read -r pane_idx pane_cmd pane_pid pane_dead <<<"$pane_info"
        if [ -z "$pane_cmd" ]; then
            pane_cmd="(idle)"
        fi
        local state="running"
        if [ "$pane_dead" = "1" ]; then
            state="dead"
        elif [ "$active" = "1" ]; then
            state="active"
        fi
        printf "  [%s] %s -> %s (pid=%s panes=%s state=%s)\n" \
            "$idx" "$name" "$pane_cmd" "${pane_pid:-n/a}" "$panes" "$state"
    done
    return 0
}

status_clients() {
    if ! list_clients; then
        return 1
    fi
    return 0
}

enable_logging() {
    local custom_dir=$1
    if ! require_tmux; then
        return 1
    fi

    local session_exists=0
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        session_exists=1
    fi

    if [ "$LOGGING_ENABLED" -eq 1 ] && [ -n "$LOG_SESSION_DIR" ]; then
        if [ -n "$custom_dir" ] && [ "$custom_dir" != "$LOG_SESSION_DIR" ]; then
            LOG_SESSION_DIR="$custom_dir"
            mkdir -p "$LOG_SESSION_DIR"
            if [ "$session_exists" -eq 1 ]; then
                while IFS='|' read -r idx name; do
                    apply_logging_to_window "$idx" "$name"
                done < <(tmux list-windows -t "$SESSION_NAME" -F "#{window_index}|#{window_name}")
            fi
            echo "Logging directory updated -> $LOG_SESSION_DIR"
        else
            echo "Logging already enabled -> $LOG_SESSION_DIR"
            if [ "$session_exists" -eq 0 ]; then
                echo "Logging will attach when session '$SESSION_NAME' starts."
            fi
        fi
        return 0
    fi

    if [ -n "$custom_dir" ]; then
        LOG_SESSION_DIR="$custom_dir"
    else
        local stamp
        stamp=$(date +%Y%m%d-%H%M%S)
        LOG_SESSION_DIR="$LOG_ROOT/$SESSION_NAME/$stamp"
    fi

    mkdir -p "$LOG_SESSION_DIR"
    LOGGING_ENABLED=1

    if [ "$session_exists" -eq 1 ]; then
        while IFS='|' read -r idx name; do
            apply_logging_to_window "$idx" "$name"
        done < <(tmux list-windows -t "$SESSION_NAME" -F "#{window_index}|#{window_name}")
        echo "Logging enabled. Files stored in $LOG_SESSION_DIR"
    else
        echo "Logging armed. Output will be stored in $LOG_SESSION_DIR once the session starts."
    fi
    return 0
}

disable_logging() {
    if [ "$LOGGING_ENABLED" -eq 0 ]; then
        echo "Logging is already disabled."
        return 0
    fi

    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        while IFS='|' read -r idx _; do
            remove_logging_from_window "$idx"
        done < <(tmux list-windows -t "$SESSION_NAME" -F "#{window_index}|#{window_name}")
    fi

    LOGGING_ENABLED=0
    LOG_SESSION_DIR=""
    echo "Logging disabled."
    return 0
}

show_logging_status() {
    if [ "$LOGGING_ENABLED" -eq 1 ]; then
        echo "Logging: enabled"
        echo "Directory: $LOG_SESSION_DIR"
        if [ -n "$LOG_SESSION_DIR" ] && tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
            while IFS='|' read -r idx name; do
                local path
                path=$(log_file_for_window "$name")
                printf "  [%s] %s -> %s\n" "$idx" "$name" "$path"
            done < <(tmux list-windows -t "$SESSION_NAME" -F "#{window_index}|#{window_name}")
        else
            echo "  (armed; awaiting session '$SESSION_NAME')"
        fi
    else
        echo "Logging: disabled"
    fi
    return 0
}

print_log_path_for_window() {
    local target=$1
    if [ -z "$target" ]; then
        echo "Usage: logs path <window-index|name|seed>" >&2
        return 1
    fi

    if [ "$LOGGING_ENABLED" -ne 1 ] || [ -z "$LOG_SESSION_DIR" ]; then
        echo "Logging is not enabled." >&2
        return 1
    fi

    if ! ensure_session_exists; then
        return 1
    fi

    local resolved
    if ! resolved=$(resolve_window_target "$target"); then
        return 1
    fi

    IFS='|' read -r _ name <<<"$resolved"
    local path
    path=$(log_file_for_window "$name")
    echo "$path"
    return 0
}

reset_netem_state() {
    NETEM_ENABLED=0
    NETEM_PROFILE=""
    NETEM_ARGS=""
    NETEM_DESCRIPTION=""
    NETEM_APPLIED=""
}

write_netem_state() {
    if [ -z "$NETEM_STATE_FILE" ]; then
        return 0
    fi
    mkdir -p "$(dirname "$NETEM_STATE_FILE")"
    {
        printf 'NETEM_ENABLED=%q\n' "$NETEM_ENABLED"
        printf 'NETEM_PROFILE=%q\n' "$NETEM_PROFILE"
        printf 'NETEM_ARGS=%q\n' "$NETEM_ARGS"
        printf 'NETEM_DESCRIPTION=%q\n' "$NETEM_DESCRIPTION"
        printf 'NETEM_APPLIED=%q\n' "$NETEM_APPLIED"
        printf 'NETEM_INTERFACE=%q\n' "$NETEM_INTERFACE"
    } >"$NETEM_STATE_FILE"
    return 0
}

init_netem_state() {
    local base_dir="$LOG_ROOT/netem"
    NETEM_STATE_FILE="$base_dir/${SESSION_NAME}.state"

    if [ ! -f "$NETEM_STATE_FILE" ]; then
        NETEM_INTERFACE="$NETEM_INTERFACE_DEFAULT"
        reset_netem_state
        return 0
    fi

    NETEM_INTERFACE="$NETEM_INTERFACE_DEFAULT"
    reset_netem_state
    # shellcheck disable=SC1090
    . "$NETEM_STATE_FILE"

    if [ -n "$NETEM_APPLIED" ]; then
        NETEM_ENABLED=1
    fi
    return 0
}

require_netem_interface() {
    local interface=$1
    if [ -z "$interface" ]; then
        echo "A network interface is required. Use 'netem use <iface>' or set NETEM_INTERFACE." >&2
        return 1
    fi
    if ! command -v ip >/dev/null 2>&1; then
        echo "The 'ip' command is required for netem operations." >&2
        return 1
    fi
    if ! ip link show "$interface" >/dev/null 2>&1; then
        echo "Interface '$interface' not found." >&2
        return 1
    fi
    return 0
}

apply_tc_command() {
    local interface=$1
    shift
    if [ -z "$interface" ]; then
        echo "Internal error: missing interface for tc command." >&2
        return 1
    fi
    if ! command -v tc >/dev/null 2>&1; then
        echo "The 'tc' command is required for netem operations." >&2
        return 1
    fi

    local cmd=(tc)
    if [ "${1:-}" = "qdisc" ]; then
        shift
        local op=${1:-}
        if [ -z "$op" ]; then
            echo "Internal error: missing qdisc operation." >&2
            return 1
        fi
        shift
        cmd+=(qdisc "$op" dev "$interface")
        if [ $# -gt 0 ]; then
            cmd+=("$@")
        fi
    else
        if [ $# -gt 0 ]; then
            cmd+=("$@")
        fi
        cmd+=(dev "$interface")
    fi
    if [ "$EUID" -ne 0 ]; then
        if ! command -v sudo >/dev/null 2>&1; then
            echo "sudo is required to run tc netem operations." >&2
            return 1
        fi
        sudo "${cmd[@]}"
    else
        "${cmd[@]}"
    fi
}

netem_apply_profile() {
    local profile=$1
    shift
    local description=$1
    shift
    local interface=${1:-$NETEM_INTERFACE}
    shift
    local args=("$@")

    if ! require_netem_interface "$interface"; then
        return 1
    fi

    if ! apply_tc_command "$interface" qdisc replace root netem "${args[@]}"; then
        echo "Failed to apply netem profile to $interface." >&2
        return 1
    fi

    NETEM_ENABLED=1
    NETEM_PROFILE="$profile"
    NETEM_DESCRIPTION="$description"
    NETEM_ARGS="${args[*]}"
    NETEM_INTERFACE="$interface"
    NETEM_APPLIED=$(date +%Y-%m-%dT%H:%M:%S%z)
    write_netem_state

    echo "Applied netem profile '$profile' on $interface"
    echo "  description: $description"
    echo "  tc args: ${args[*]}"
    return 0
}

netem_clear() {
    local interface=${1:-$NETEM_INTERFACE}

    if ! require_netem_interface "$interface"; then
        return 1
    fi

    if apply_tc_command "$interface" qdisc del root >/dev/null 2>&1; then
        echo "Cleared netem settings from $interface."
    else
        echo "No existing netem qdisc to clear on $interface."
    fi

    NETEM_INTERFACE="$interface"
    reset_netem_state
    write_netem_state
    return 0
}

netem_status() {
    local interface=${1:-$NETEM_INTERFACE}

    if [ -z "$interface" ]; then
        echo "Netem interface not set. Use 'netem use <iface>'."
        return 0
    fi

    echo "Netem interface: $interface"
    if [ "$NETEM_ENABLED" -eq 1 ]; then
        echo "Netem: enabled"
        echo "  profile: ${NETEM_PROFILE:-custom}"
        if [ -n "$NETEM_DESCRIPTION" ]; then
            echo "  description: $NETEM_DESCRIPTION"
        fi
        if [ -n "$NETEM_ARGS" ]; then
            echo "  tc args: $NETEM_ARGS"
        fi
        if [ -n "$NETEM_APPLIED" ]; then
            echo "  applied: $NETEM_APPLIED"
        fi
        if command -v tc >/dev/null 2>&1; then
            if tc qdisc show dev "$interface" | grep -q netem; then
                tc qdisc show dev "$interface" | sed 's/^/  tc: /'
            else
                echo "  warning: netem enabled but tc output missing"
            fi
        else
            echo "  note: tc command unavailable for verification"
        fi
    else
        echo "Netem: disabled"
        if command -v tc >/dev/null 2>&1; then
            if tc qdisc show dev "$interface" | grep -q netem; then
                echo "  note: tc reports existing netem configuration"
                tc qdisc show dev "$interface" | sed 's/^/  tc: /'
            fi
        else
            echo "  note: tc command unavailable for verification"
        fi
    fi
    return 0
}

netem_profile_test1() {
    local interface=${1:-$NETEM_INTERFACE}
    local loss=${2:-$NETEM_TEST1_LOSS}
    netem_apply_profile "test1" "Packet loss $loss" "$interface" loss "$loss"
}

netem_profile_test2() {
    local interface=${1:-$NETEM_INTERFACE}
    local delay=${2:-$NETEM_TEST2_DELAY}
    local jitter=${3:-$NETEM_TEST2_JITTER}
    local dist=${4:-$NETEM_TEST2_DIST}
    netem_apply_profile "test2" "Delay $delay ± $jitter distribution $dist" "$interface" delay "$delay" "$jitter" distribution "$dist"
}

netem_apply_custom() {
    local interface=${NETEM_INTERFACE}
    if [ -z "$interface" ]; then
        echo "Set a netem interface first with 'netem use <iface>'." >&2
        return 1
    fi
    if [ $# -eq 0 ]; then
        echo "Usage: netem apply custom <tc args>" >&2
        return 1
    fi
    netem_apply_profile "custom" "Custom netem: $*" "$interface" "$@"
}

netem_set_interface() {
    local interface=$1
    if [ -z "$interface" ]; then
        echo "Usage: netem use <interface>" >&2
        return 1
    fi
    if ! require_netem_interface "$interface"; then
        return 1
    fi
    if [ "$NETEM_ENABLED" -eq 1 ] && [ "$NETEM_INTERFACE" != "$interface" ]; then
        echo "Clear the active netem profile before switching interfaces." >&2
        return 1
    fi
    NETEM_INTERFACE="$interface"
    NETEM_INTERFACE_DEFAULT="$interface"
    write_netem_state
    echo "Netem interface set to $interface"
    return 0
}
restart_client_window() {
    local target=$1
    if [ -z "$target" ]; then
        echo "Usage: restart <window-index|name|seed>" >&2
        return 1
    fi

    if ! ensure_session_exists; then
        return 1
    fi

    local resolved
    if ! resolved=$(resolve_window_target "$target"); then
        return 1
    fi

    IFS='|' read -r idx name <<<"$resolved"
    local seed_hint=${name#client_}

    local found_entry=""
    for entry in "${CLIENTS[@]}"; do
        IFS='|' read -r host port mac seed duration interval <<<"$entry"
        if [ "$seed" = "$seed_hint" ]; then
            found_entry="$entry"
            break
        fi
    done

    if [ -z "$found_entry" ]; then
        echo "No client definition found for window '$name' (seed $seed_hint)." >&2
        return 1
    fi

    if ! tmux kill-window -t "${SESSION_NAME}:$idx" 2>/dev/null; then
        echo "Failed to stop window $name (#$idx) for restart." >&2
        return 1
    fi

    IFS='|' read -r host port mac seed duration interval <<<"$found_entry"
    interval=${interval:-$DEFAULT_INTERVAL}

    if ! launch_client_window "$host" "$port" "$mac" "$seed" "$duration" "$interval" 0; then
        echo "Failed to restart client $name." >&2
        return 1
    fi

    return 0
}

print_sessions() {
    if ! require_tmux; then
        return 1
    fi
    tmux ls 2>/dev/null || echo "No tmux sessions found."
    return 0
}

interactive_shell() {
    cat <<'EOF'
  ____  _   _ _____     ___ ___ _____ 
 |  _ \| \ | |_   _|   |_ _/ _ \_   _|
 | | | |  \| | | |  ___ | | | | || |  
 | |_| | |\  | | | |___|| | |_| || |  
 |____/|_| \_| |_|      |_|\___/ |_| 

             DNT IOT

         Developed by Bima

             Playground

Type 'help' to list available commands.


EOF

    while true; do
        printf "client-shell> "
        IFS= read -r line || { echo; break; }
        line="${line#${line%%[![:space:]]*}}"
        line="${line%${line##*[![:space:]]}}"
        if [ -z "$line" ]; then
            continue
        fi

        set -- $line
        local cmd=$1
        shift

        case "$cmd" in
            help)
                cat <<'EOC'
Commands:
    start [session]               Start configured clients (optionally with a session name)
    stop [target]                 Stop the session or a specific client window
    attach [window]               Attach to the session (optionally focusing a window)
    status | list                 Show detailed session status
    add <host> <port> <mac> <seed> <duration> [interval]
                                                                 Launch a new client window
    kill <window-index|name|seed> Stop a specific client window
    restart <window-index|name|seed>
                                                                 Restart a client window from its definition
    logs enable [dir]             Start piping pane output into log files
    logs disable                  Stop piping logs for all windows
    logs show                     Show logging status and log file paths
    logs path <window>            Print the log file path for a window
    tcpdump enable <iface> [--output <file>] [filter]
                                                                 Arm tcpdump to start when the session launches
    tcpdump start <iface> [--output <file>] [filter]
                                                                 Start a tcpdump capture immediately
    tcpdump stop                  Stop the active tcpdump capture
    tcpdump disable               Clear tcpdump configuration and stop capture
    tcpdump status                Show tcpdump status and file paths
    netem use <iface>             Select interface for netem operations
    netem apply test1 [loss]      Apply packet-loss profile (default from NETEM_TEST1_LOSS)
    netem apply test2 [delay [jitter [dist]]]
                                                                 Apply delay/jitter profile (defaults from NETEM_TEST2_* envs)
    netem apply custom <tc args>  Apply custom tc netem arguments
    netem clear [iface]           Remove netem configuration from interface
    netem status [iface]          Show current netem status and tc output
    config use <path>             Load clients from a JSON file
    config show                   Display current configuration
    config clear                  Restore embedded defaults
    session use <name>            Switch to a different session name
    session list                  List tmux sessions (if any)
    clear                         Clear the screen
    exit | quit                   Leave the shell


EOC
                ;;
            logs)
                case "$1" in
                    enable)
                        shift
                        if ! enable_logging "${1:-}"; then
                            echo "logs enable failed" >&2
                        fi
                        ;;
                    disable)
                        disable_logging
                        ;;
                    show|status|"")
                        show_logging_status
                        ;;
                    path)
                        shift
                        if ! print_log_path_for_window "$1"; then
                            echo "logs path failed" >&2
                        fi
                        ;;
                    *)
                        echo "Usage: logs {enable [dir]|disable|show|path <window>}" >&2
                        ;;
                esac
                ;;
            tcpdump)
                local sub=${1:-status}
                case "$sub" in
                    start)
                        shift
                        if ! start_tcpdump_capture "$@"; then
                            echo "tcpdump start failed" >&2
                        fi
                        ;;
                    enable)
                        shift
                        if ! tcpdump_enable "$@"; then
                            echo "tcpdump enable failed" >&2
                        fi
                        ;;
                    disable)
                        if ! tcpdump_disable; then
                            echo "tcpdump disable failed" >&2
                        fi
                        ;;
                    stop)
                        if ! stop_tcpdump_capture; then
                            echo "tcpdump stop failed" >&2
                        fi
                        ;;
                    status|show|"")
                        if [ "$sub" != "" ]; then
                            shift
                        fi
                        tcpdump_status
                        ;;
                    *)
                        echo "Usage: tcpdump {enable <iface> [--output <file>] [filter ...]|start <iface> [--output <file>] [filter ...]|stop|disable|status}" >&2
                        ;;
                esac
                ;;
            netem)
                local sub=${1:-status}
                case "$sub" in
                    use)
                        shift
                        if ! netem_set_interface "$1"; then
                            echo "netem use failed" >&2
                        fi
                        ;;
                    apply)
                        shift
                        case "${1:-}" in
                            test1)
                                shift
                                if ! netem_profile_test1 "$NETEM_INTERFACE" "${1:-$NETEM_TEST1_LOSS}"; then
                                    echo "netem apply test1 failed" >&2
                                fi
                                ;;
                            test2)
                                shift
                                if ! netem_profile_test2 "$NETEM_INTERFACE" "${1:-$NETEM_TEST2_DELAY}" "${2:-$NETEM_TEST2_JITTER}" "${3:-$NETEM_TEST2_DIST}"; then
                                    echo "netem apply test2 failed" >&2
                                fi
                                ;;
                            custom)
                                shift
                                if ! netem_apply_custom "$@"; then
                                    echo "netem apply custom failed" >&2
                                fi
                                ;;
                            *)
                                echo "Usage: netem apply {test1 [loss]|test2 [delay [jitter [dist]]]|custom <tc args>}" >&2
                                ;;
                        esac
                        ;;
                    clear)
                        shift
                        if ! netem_clear "${1:-$NETEM_INTERFACE}"; then
                            echo "netem clear failed" >&2
                        fi
                        ;;
                    status|show)
                        shift
                        if ! netem_status "${1:-$NETEM_INTERFACE}"; then
                            echo "netem status failed" >&2
                        fi
                        ;;
                    *)
                        if [ -z "$sub" ]; then
                            netem_status "$NETEM_INTERFACE"
                        else
                            echo "Usage: netem {use <iface>|apply ...|clear [iface]|status}" >&2
                        fi
                        ;;
                esac
                ;;
            start)
                if [ $# -gt 0 ]; then
                    if ! set_session_name "$1"; then
                        echo "start failed" >&2
                        continue
                    fi
                    shift
                fi
                if ! start_clients; then
                    echo "start failed" >&2
                fi
                ;;
            stop)
                if [ $# -eq 0 ]; then
                    if ! stop_clients; then
                        echo "stop failed" >&2
                    fi
                else
                    if ! stop_client_window "$1"; then
                        echo "stop failed" >&2
                    fi
                fi
                ;;
            attach)
                attach_clients "${1:-}"
                ;;
            status|list)
                status_clients
                ;;
            add)
                if ! create_client_window "$@"; then
                    echo "add failed" >&2
                fi
                ;;
            kill)
                if ! stop_client_window "$1"; then
                    echo "kill failed" >&2
                fi
                ;;
            restart)
                if ! restart_client_window "$1"; then
                    echo "restart failed" >&2
                fi
                ;;
            config)
                case "$1" in
                    use)
                        shift
                        if ! load_config_file "$1"; then
                            echo "config use failed" >&2
                        fi
                        ;;
                    show|"")
                        show_active_config
                        ;;
                    clear)
                        reset_to_default_clients
                        ;;
                    *)
                        echo "Usage: config {use <path>|show|clear}" >&2
                        ;;
                esac
                ;;
            session)
                case "$1" in
                    use)
                        shift
                        if ! set_session_name "$1"; then
                            echo "session use failed" >&2
                        fi
                        ;;
                    list)
                        if ! print_sessions; then
                            echo "Unable to list sessions" >&2
                        fi
                        ;;
                    show|name|current|"")
                        echo "Current session: $SESSION_NAME"
                        ;;
                    *)
                        echo "Usage: session use <name> | session list" >&2
                        ;;
                esac
                ;;
            clear)
                command -v clear >/dev/null 2>&1 && clear
                ;;
            exit|quit)
                break
                ;;
            *)
                echo "Unknown command: $cmd" >&2
                ;;
        esac
    done

    echo "Bye!"
    return 0
}

main() {
    local session_override=""
    while [ $# -gt 0 ]; do
        case "$1" in
            -s|--session)
                if [ -z "${2:-}" ]; then
                    echo "Error: --session requires a name." >&2
                    usage >&2
                    return 1
                fi
                session_override=$2
                shift 2
                ;;
            -c|--config)
                if [ -z "${2:-}" ]; then
                    echo "Error: --config requires a file path." >&2
                    usage >&2
                    return 1
                fi
                CONFIG_FILE=$2
                shift 2
                ;;
            -h|--help)
                usage
                return 0
                ;;
            --)
                shift
                break
                ;;
            -*)
                echo "Unknown option: $1" >&2
                usage >&2
                return 1
                ;;
            *)
                break
                ;;
        esac
    done

    if [ -n "$session_override" ]; then
        SESSION_NAME="$session_override"
    fi

    init_tcpdump_state
    init_netem_state

    if [ -n "$CONFIG_FILE" ]; then
        if ! load_config_file "$CONFIG_FILE"; then
            return 1
        fi
    fi

    local command
    if [ $# -eq 0 ]; then
        command="shell"
    else
        command=$1
        shift
    fi

    local rc=0
    case "$command" in
        shell)
            interactive_shell || rc=$?
            ;;
        start)
            if [ $# -gt 0 ]; then
                if ! set_session_name "$1"; then
                    rc=1
                else
                    shift
                    start_clients || rc=$?
                fi
            else
                start_clients || rc=$?
            fi
            ;;
        stop)
            if [ $# -eq 0 ]; then
                stop_clients || rc=$?
            else
                stop_client_window "$1" || rc=$?
            fi
            ;;
        attach)
            attach_clients "${1:-}" || rc=$?
            ;;
        status|list)
            status_clients || rc=$?
            ;;
        add)
            create_client_window "$@" || rc=$?
            ;;
        kill)
            stop_client_window "$1" || rc=$?
            ;;
        restart)
            restart_client_window "$1" || rc=$?
            ;;
        logs)
            case "${1:-}" in
                enable)
                    shift
                    enable_logging "${1:-}" || rc=$?
                    ;;
                disable)
                    disable_logging || rc=$?
                    ;;
                show|status|"")
                    show_logging_status || rc=$?
                    ;;
                path)
                    shift
                    print_log_path_for_window "$1" || rc=$?
                    ;;
                *)
                    echo "Usage: $SCRIPT_NAME logs {enable [dir]|disable|show|path <window>}" >&2
                    rc=1
                    ;;
            esac
            ;;
        tcpdump)
            case "${1:-}" in
                start)
                    shift
                    start_tcpdump_capture "$@" || rc=$?
                    ;;
                enable)
                    shift
                    tcpdump_enable "$@" || rc=$?
                    ;;
                disable)
                    tcpdump_disable || rc=$?
                    ;;
                stop)
                    stop_tcpdump_capture || rc=$?
                    ;;
                status|show|"")
                    if [ $# -gt 0 ]; then
                        shift
                    fi
                    tcpdump_status || rc=$?
                    ;;
                *)
                    echo "Usage: $SCRIPT_NAME tcpdump {enable <iface> [--output <file>] [filter ...]|start <iface> [--output <file>] [filter ...]|stop|disable|status}" >&2
                    rc=1
                    ;;
            esac
            ;;
        netem)
            local subcommand=${1:-status}
            case "$subcommand" in
                use)
                    shift
                    netem_set_interface "$1" || rc=$?
                    ;;
                apply)
                    shift
                    case "${1:-}" in
                        test1)
                            shift
                            netem_profile_test1 "$NETEM_INTERFACE" "${1:-$NETEM_TEST1_LOSS}" || rc=$?
                            ;;
                        test2)
                            shift
                            netem_profile_test2 "$NETEM_INTERFACE" "${1:-$NETEM_TEST2_DELAY}" "${2:-$NETEM_TEST2_JITTER}" "${3:-$NETEM_TEST2_DIST}" || rc=$?
                            ;;
                        custom)
                            shift
                            netem_apply_custom "$@" || rc=$?
                            ;;
                        *)
                            echo "Usage: $SCRIPT_NAME netem apply {test1 [loss]|test2 [delay [jitter [dist]]]|custom <tc args>}" >&2
                            rc=1
                            ;;
                    esac
                    ;;
                clear)
                    shift
                    netem_clear "${1:-$NETEM_INTERFACE}" || rc=$?
                    ;;
                status|show)
                    shift
                    netem_status "${1:-$NETEM_INTERFACE}" || rc=$?
                    ;;
                *)
                    if [ -z "$subcommand" ]; then
                        netem_status "$NETEM_INTERFACE" || rc=$?
                    else
                        echo "Usage: $SCRIPT_NAME netem {use <iface>|apply ...|clear [iface]|status}" >&2
                        rc=1
                    fi
                    ;;
            esac
            ;;
        config)
            case "${1:-}" in
                use)
                    shift
                    load_config_file "$1" || rc=$?
                    ;;
                show|"")
                    show_active_config || rc=$?
                    ;;
                clear)
                    reset_to_default_clients || rc=$?
                    ;;
                *)
                    echo "Usage: $SCRIPT_NAME config {use <path>|show|clear}" >&2
                    rc=1
                    ;;
            esac
            ;;
        session)
            case "${1:-}" in
                use)
                    shift
                    if ! set_session_name "$1"; then
                        rc=1
                    fi
                    ;;
                list)
                    print_sessions || rc=$?
                    ;;
                show|name|current|"")
                    echo "Current session: $SESSION_NAME"
                    ;;
                *)
                    echo "Usage: $SCRIPT_NAME session {use <name>|list|show}" >&2
                    rc=1
                    ;;
            esac
            ;;
        *)
            echo "Unknown command: $command" >&2
            usage >&2
            rc=1
            ;;
    esac

    return $rc
}

main "$@"
exit $?

