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
        self.registry = {}
        self._heading = ['msg_type','device_id', 'seq', 'timestamp', 'arrival_time', 'value',
                         'duplicate_flag', 'gap_flag', 'delayed_flag', 'cpu_time_ms','packet_size','batch_index']

    def start(self, start_time: float) -> bool:
        try:
            os.makedirs(self.vault_path, exist_ok=True)

            stamp = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime(start_time))
            tagged_name = f"{self.tag_prefix}_{stamp}.csv"
            storage_path = os.path.join(self.vault_path, tagged_name)

            self.binder = open(storage_path, 'w', newline='')
            self.sheet = csv.writer(self.binder)
            self.registry = {}

            self.sheet.writerow(self._heading)
            self.binder.flush()  # Flush header immediately

            console.log.green(f"[Logger] CSV logging active. Writing to {storage_path}")
            return True
        except IOError as e:
            console.log.red(f"[Logger] FATAL: Could not open CSV file. {e}")
            return False

    def log_packet(self, message_type: int, device_id: int, seq_num: int, timestamp_s: float, arrival_time: float,
                   value: int, is_duplicate: bool, is_gap: bool, is_delayed: bool, cpu_time_s: float, packet_size: int,
                   batch_index: int = 0):
        if self.sheet and self.binder:
            try:
                cpu_ms = cpu_time_s * 1000.0
                record_line = {
                    'msg_type': message_type,
                    'device_id': device_id,
                    'seq': seq_num,
                    'timestamp_s': timestamp_s,
                    'arrival_s': arrival_time,
                    'value': value,
                    'duplicate': 1 if is_duplicate else 0,
                    'gap': 1 if is_gap else 0,
                    'delayed': 1 if is_delayed else 0,
                    'cpu_time_ms': cpu_ms,
                    'packet_size': packet_size,
                    'batch_index': batch_index
                }
                # Use arrival_time in key to allow logging duplicates as separate entries
                if is_duplicate:
                    key = (device_id, seq_num, batch_index, arrival_time)
                else:
                    key = (device_id, seq_num, batch_index, 0)
                self.registry[key] = record_line
                
                # Write immediately to CSV for crash safety
                readable_stamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp_s))
                readable_arrival = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(arrival_time))
                self.sheet.writerow([
                    message_type,
                    device_id,
                    seq_num,
                    readable_stamp,
                    readable_arrival,
                    value,
                    1 if is_duplicate else 0,
                    1 if is_gap else 0,
                    1 if is_delayed else 0,
                    cpu_ms,
                    packet_size,
                    batch_index
                ])
                self.binder.flush()  # Ensure data is written to disk immediately
            except IOError as e:
                console.log.red(f"[CSV Error] Failed to write to CSV file. {e}")

    def update_flags_by_seq(self, seq_num: int, device_id: int, batch_index: int, is_duplicate: bool, is_gap: bool,
                            is_delayed: bool):
        key = (device_id, seq_num, batch_index)
        if key in self.registry:
            entry = self.registry[key]
            entry['duplicate'] = 1 if is_duplicate else 0
            entry['gap'] = 1 if is_gap else 0
            entry['delayed'] = 1 if is_delayed else 0
            self._rewrite_sheet()
            console.log.green(
                f"[Logger] Updated flags for DeviceID {device_id}, Seq {seq_num}, BatchIndex {batch_index}.")
        else:
            console.log.yellow(
                f"[Logger] No matching entry found for DeviceID {device_id}, Seq {seq_num}, BatchIndex {batch_index}.")

    def _rewrite_sheet(self) -> None:
        ordered_rows = sorted(
            self.registry.values(),
            key=lambda entry: (entry['device_id'], entry['seq'])
        )

        self.binder.seek(0)
        self.binder.truncate(0)
        self.sheet.writerow(self._heading)

        for entry in ordered_rows:
            readable_stamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry['timestamp_s']))
            readable_arrival = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry['arrival_s']))
            self.sheet.writerow([
                entry['msg_type'],
                entry['device_id'],
                entry['seq'],
                readable_stamp,
                readable_arrival,
                entry['value'],
                entry['duplicate'],
                entry['gap'],
                entry['delayed'],
                entry['cpu_time_ms'],
                entry['packet_size'],
                entry['batch_index']
            ])

        self.binder.flush()
    def close(self):
        if self.binder:
            self.binder.close()
            console.log.yellow("[Logger] CSV file closed.")