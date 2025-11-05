import csv
import os
import time
from ConsoleColor import console


class Logger:
    def __init__(self, log_directory: str, filename_prefix: str = "server_log"):

        self.sheet = None
        self.binder = None
        self.vault_path = log_directory
        self.tag_prefix = filename_prefix
        self.registry = []
        self._heading = ['device_id', 'seq', 'timestamp', 'arrival_time', 'duplicate_flag', 'gap_flag', 'delayed_flag']

    def start(self, start_time: float) -> bool:
        try:
            os.makedirs(self.vault_path, exist_ok=True)

            stamp = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime(start_time))
            tagged_name = f"{self.tag_prefix}_{stamp}.csv"
            storage_path = os.path.join(self.vault_path, tagged_name)

            self.binder = open(storage_path, 'w', newline='')
            self.sheet = csv.writer(self.binder)
            self.registry = []

            self.sheet.writerow(self._heading)

            console.log.green(f"[Logger] CSV logging active. Writing to {storage_path}")
            return True
        except IOError as e:
            console.log.red(f"[Logger] FATAL: Could not open CSV file. {e}")
            return False

    def log_packet(self, device_id: int, seq_num: int, timestamp_s: float, arrival_time: float, is_duplicate: bool,
                   is_gap: bool, is_delayed: bool):
        if self.sheet and self.binder:
            try:
                record_line = {
                    'device_id': device_id,
                    'seq': seq_num,
                    'timestamp_s': timestamp_s,
                    'arrival_s': arrival_time,
                    'duplicate': 1 if is_duplicate else 0,
                    'gap': 1 if is_gap else 0,
                    'delayed': 1 if is_delayed else 0
                }
                self.registry.append(record_line)
                self._rewrite_sheet()
            except IOError as e:
                console.log.red(f"[CSV Error] Failed to write to CSV file. {e}")

    def _rewrite_sheet(self) -> None:
        ordered_rows = sorted(
            self.registry,
            key=lambda entry: (entry['timestamp_s'], entry['arrival_s'], entry['seq'])
        )

        self.binder.seek(0)
        self.binder.truncate(0)
        self.sheet.writerow(self._heading)

        for entry in ordered_rows:
            readable_stamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry['timestamp_s']))
            readable_arrival = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry['arrival_s']))
            self.sheet.writerow([
                entry['device_id'],
                entry['seq'],
                readable_stamp,
                readable_arrival,
                entry['duplicate'],
                entry['gap'],
                entry['delayed']
            ])

        self.binder.flush()

    def close(self):
        if self.binder:
            self.binder.close()
            console.log.yellow("[Logger] CSV file closed.")