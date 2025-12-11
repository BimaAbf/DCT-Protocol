"""

Defines the constants for the custom telemetry protocol.
Loads values from a .env file. Assumes .env file and all
variables are present.
"""
import struct
import os
import sys
from dotenv import load_dotenv


if not load_dotenv():
    print("[FATAL] .env file not found.")
    sys.exit(1)
def _get_int_env(key: str) -> int:
    """gets a required env var, casting to int. Supports hex."""
    value = os.getenv(key)
    if value is None:
        print(f"[FATAL] Required env var '{key}' not found in .env file.")
        sys.exit(1)
    try:
        return int(value, 0)
    except ValueError:
        print(f"[FATAL] Invalid int value for {key}: '{value}'.")
        sys.exit(1)

def _get_str_env(key: str) -> str:
    """gets a required string env var."""
    value = os.getenv(key)
    if value is None:
        print(f"[FATAL] Required env var '{key}' not found in .env file.")
        sys.exit(1)
    return value
MSG_DATA_DELTA = _get_int_env('MSG_DATA_DELTA')
MSG_DATA_DELTA_QUANTIZED = _get_int_env('MSG_DATA_DELTA_QUANTIZED')
PROTOCOL_VERSION = _get_int_env('PROTOCOL_VERSION')
MSG_STARTUP = _get_int_env('MSG_STARTUP')
MSG_STARTUP_ACK = _get_int_env('MSG_STARTUP_ACK')
MSG_TIME_SYNC = _get_int_env('MSG_TIME_SYNC')
MSG_KEYFRAME = _get_int_env('MSG_KEYFRAME')
MSG_HEARTBEAT = _get_int_env('MSG_HEARTBEAT')
MSG_BATCHED_DATA = _get_int_env('MSG_BATCHED_DATA')
MSG_BATCHED_DATA_QUANTIZED = _get_int_env('MSG_BATCHED_DATA_QUANTIZED')
MSG_SHUTDOWN = _get_int_env('MSG_SHUTDOWN')
HEADER_FORMAT = _get_str_env('HEADER_FORMAT')
MSG_KEYFRAME_QUANTIZED = _get_int_env('MSG_KEYFRAME_QUANTIZED')
MAX_PACKET_SIZE = _get_int_env('MAX_PACKET_SIZE')
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)