import os
import sys
from dotenv import load_dotenv
from server import Server
from ConsoleColor import console

if not load_dotenv():
    console.log.red("[FATAL] .env file not found. Please create one.")
    sys.exit(1)


def _get_str_env(key: str) -> str:
    value = os.getenv(key)
    if value is None:
        console.log.red(f"[FATAL] Required env var '{key}' not found in .env file.")
        sys.exit(1)
    return value


def _get_int_env(key: str) -> int:
    value = os.getenv(key)
    if value is None:
        console.log.red(f"[FATAL] Required env var '{key}' not found in .env file.")
        sys.exit(1)
    try:
        return int(value)
    except ValueError:
        console.log.red(f"[FATAL] Invalid int value for {key}: '{value}'.")
        sys.exit(1)

HOST = _get_str_env('HOST')
PORT = _get_int_env('PORT')
CSV_LOG_DIR = _get_str_env('CSV_LOG_DIR')


if __name__ == "__main__":
    server = Server(
        host=HOST,
        port=PORT,
        csvLogDir=CSV_LOG_DIR
    )
    server.run()

