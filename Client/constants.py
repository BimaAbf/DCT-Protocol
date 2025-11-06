"""
protocol_constants.py

Defines the constants for the custom telemetry protocol.
Loads values from a .env file. Assumes .env file and all
variables are present.
"""
import struct
import os
import sys
from dotenv import load_dotenv

# Load environment variables from a .env file
if not load_dotenv():
    print("[FATAL] .env file not found.")
    sys.exit(1)

# Helper function to get int from env
def _get_int_env(key: str) -> int:
    """Gets a required env var, casting to int. Supports hex."""
    value = os.getenv(key)
    if value is None:
        print(f"[FATAL] Required env var '{key}' not found in .env file.")
        sys.exit(1)
    try:
        return int(value, 0) # base 0 allows auto-detecting hex (0x...)
    except ValueError:
        print(f"[FATAL] Invalid int value for {key}: '{value}'.")
        sys.exit(1)

# Helper function to get string from env
def _get_str_env(key: str) -> str:
    """Gets a required string env var."""
    value = os.getenv(key)
    if value is None:
        print(f"[FATAL] Required env var '{key}' not found in .env file.")
        sys.exit(1)
    return value

# --- Protocol Constants ---

# Protocol Version
PROTOCOL_VERSION = _get_int_env('PROTOCOL_VERSION')

# Message Types
MSG_STARTUP = _get_int_env('MSG_STARTUP')
MSG_STARTUP_ACK = _get_int_env('MSG_STARTUP_ACK')
MSG_TIME_SYNC = _get_int_env('MSG_TIME_SYNC')
MSG_KEYFRAME = _get_int_env('MSG_KEYFRAME')
MSG_DATA_DELTA = _get_int_env('MSG_DATA_DELTA')
MSG_HEARTBEAT = _get_int_env('MSG_HEARTBEAT')
MSG_BATCHED_DATA = _get_int_env('MSG_BATCHED_DATA')
MSG_DATA_DELTA_QUANTIZED = _get_int_env('MSG_DATA_DELTA_QUANTIZED')
MSG_KEYFRAME_QUANTIZED = _get_int_env('MSG_KEYFRAME_QUANTIZED')
MSG_BATCHED_DATA_QUANTIZED = _get_int_env('MSG_BATCHED_DATA_QUANTIZED')
MSG_SHUTDOWN = _get_int_env('MSG_SHUTDOWN')
HEADER_FORMAT = _get_str_env('HEADER_FORMAT')
try:
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
except struct.error:
    print(f"[Config FATAL] Invalid HEADER_FORMAT value: '{HEADER_FORMAT}'.")
    sys.exit(1)

# Network constants
MAX_PACKET_SIZE = _get_int_env('MAX_PACKET_SIZE')

