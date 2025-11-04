import csv
import os
import time
from ConsoleColor import console


class Logger:
    def __init__(self, log_directory: str, filename_prefix: str = "server_log"):

        self.csv_writer = None
        self.csv_file = None
        self.log_directory = log_directory
        self.filename_prefix = filename_prefix

    def start(self, start_time: float) -> bool:
        try:
            os.makedirs(self.log_directory, exist_ok=True)

            time_str = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime(start_time))
            filename = f"{self.filename_prefix}_{time_str}.csv"
            filepath = os.path.join(self.log_directory, filename)

            self.csv_file = open(filepath, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)

            self.csv_writer.writerow(['device_id', 'seq', 'timestamp', 'arrival_time', 'duplicate_flag', 'gap_flag'])

            console.log.green(f"[Logger] CSV logging active. Writing to {filepath}")
            return True
        except IOError as e:
            console.log.red(f"[Logger] FATAL: Could not open CSV file. {e}")
            return False

    def log_packet(self, device_id: int, seq_num: int, timestamp_s: float, arrival_time: float, is_duplicate: bool,
                   is_gap: bool):
        if self.csv_writer and self.csv_file:
            try:
                human_readable_timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp_s))
                human_readable_arrival = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(arrival_time))

                self.csv_writer.writerow([
                    device_id,
                    seq_num,
                    human_readable_timestamp,
                    human_readable_arrival,
                    1 if is_duplicate else 0,
                    1 if is_gap else 0
                ])
                self.csv_file.flush()
            except IOError as e:
                console.log.red(f"[CSV Error] Failed to write to CSV file. {e}")

    def close(self):
        if self.csv_file:
            self.csv_file.close()
            console.log.yellow("[Logger] CSV file closed.")