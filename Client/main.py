"""
Usage:
  python client_main.py <HOST> --port <PORT> --interval <SEC> --duration <SEC> --mac <MAC> [--seed <SEED>]
Example:
  python client_main.py 127.0.0.1 --port 12345 --interval 1.0 --duration 60.0 --mac "AA:BB:CC:DD:EE:FF" --seed 42
"""

import argparse
from client import Client

def main():
    parser = argparse.ArgumentParser(
        description="Client for DCT Protocol",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Example:\n  python client_main.py 127.0.0.1 --port 12345 --interval 1.0 --duration 60.0 --mac \"AA:BB:CC:DD:EE:FF\" --seed 42"
    )

    parser.add_argument(
        "host",
        type=str,
        help="The server's IP address or hostname."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="The server's port number (default: 12345)."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="The interval in seconds between sending packets (default: 1.0)."
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="The total time in seconds to run the client (default: 60.0)."
    )
    parser.add_argument(
        "--mac",
        type=str,
        required=True,
        help="The client's MAC address for registration (e.g., \"AA:BB:CC:DD:EE:FF\")."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=100,
        help="Optional random seed for reproducible data simulation."
    )

    args = parser.parse_args()

    # Create the client instance
    client = Client(
        server_host=args.host,
        server_port=args.port,
        mac=args.mac,
        interval=args.interval,
        duration=args.duration,
        seed=args.seed
    )

    # Run the client
    client.run()
    client.close()


if __name__ == "__main__":
    main()

