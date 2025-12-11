from PySide6.QtCore import QObject, Signal, QTimer
import os
import csv
from datetime import datetime
from collections import defaultdict

class LogsController(QObject):
    logsUpdated = Signal(list)
    errorOccurred = Signal(str)

    def __init__(self, logs_dir=None):
        super().__init__()
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Read CSV_LOG_DIR from .env file
        if logs_dir is None:
            env_path = os.path.join(base_dir, ".env")
            csv_log_dir = "./logs"  # default
            if os.path.exists(env_path):
                try:
                    with open(env_path) as f:
                        for line in f:
                            if '=' in line and not line.strip().startswith('#'):
                                key, value = line.strip().split('=', 1)
                                if key.strip() == 'CSV_LOG_DIR':
                                    csv_log_dir = value.strip().strip('"').strip("'")
                                    break
                except Exception:
                    pass
            # Resolve relative path from project root
            if csv_log_dir.startswith("./"):
                csv_log_dir = csv_log_dir[2:]
            self.logs_dir = os.path.join(base_dir, csv_log_dir)
        else:
            self.logs_dir = logs_dir
        
        self.latest_log = None
        self.stats = {"pps": 0.0, "last": None}
        self.metrics = {}
        
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_logs)
        self.auto_refresh_timer.start(2000) 
        
        self.refresh_logs()

    def refresh_logs(self):
        files = []
        if os.path.exists(self.logs_dir):
            files = sorted([f for f in os.listdir(self.logs_dir) if f.endswith(('.csv', '.log', '.txt'))])
        
        if files:
            self.latest_log = os.path.join(self.logs_dir, files[-1])
            self._analyze_log(self.latest_log)
        
        self.logsUpdated.emit(files)
        return files

    def read_log(self, filename):
        path = os.path.join(self.logs_dir, filename)
        if not os.path.exists(path):
            return []
        
        with open(path, newline="", encoding="utf-8") as f:
            if filename.endswith(".csv"):
                return list(csv.reader(f))
            else:
                return [[line.strip()] for line in f]

    def _parse_datetime(self, value):
        if not value or value == '-':
            return None
        value = value.replace('Z', '+00:00')
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
        
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _analyze_log(self, path):
        data = defaultdict(lambda: {
            "pkts": 0, "dups": 0, "gaps": 0, "last": None, 
            "lats": [], "sizes": [], "cpus": []
        })
        arrivals = []
        
        try:
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    device_id = row.get("device_id", "unknown")
                    arrival_time = self._parse_datetime(row.get("arrival_time"))
                    timestamp = self._parse_datetime(row.get("timestamp"))
                    
                    if arrival_time:
                        arrivals.append(arrival_time)
                    
                    device_data = data[device_id]
                    device_data["pkts"] += 1
                    
                    if row.get("duplicate_flag") == "1":
                        device_data["dups"] += 1
                    if row.get("gap_flag") == "1":
                        device_data["gaps"] += 1
                    
                    if arrival_time:
                        device_data["last"] = arrival_time
                    
                    if arrival_time and timestamp:
                        latency = (arrival_time - timestamp).total_seconds() * 1000
                        if 0 <= latency < 60000: 
                            device_data["lats"].append(latency)
                    
                    if row.get("packet_size"):
                        device_data["sizes"].append(float(row["packet_size"]))
                    if row.get("cpu_time_ms"):
                        device_data["cpus"].append(float(row["cpu_time_ms"]))
                        
        except Exception as e:
            self.errorOccurred.emit(str(e))
            return

        span = (max(arrivals) - min(arrivals)).total_seconds() if len(arrivals) > 1 else 0
        self.stats["pps"] = len(arrivals) / span if span > 0 else len(arrivals)
        self.stats["last"] = max(arrivals) if arrivals else None
        
        self.metrics = {}
        for device_id, stats in data.items():
            self.metrics[device_id] = {
                "packets": stats["pkts"],
                "duplicates": stats["dups"],
                "gaps": stats["gaps"],
                "last_seen": stats["last"],
                "avg_latency": sum(stats["lats"]) / len(stats["lats"]) if stats["lats"] else None,
                "avg_packet_size": sum(stats["sizes"]) / len(stats["sizes"]) if stats["sizes"] else None,
                "avg_cpu": sum(stats["cpus"]) / len(stats["cpus"]) if stats["cpus"] else None
            }

    def get_device_ids(self):
        return sorted(self.metrics.keys())

    def get_device_metrics(self, device_id):
        return self.metrics.get(device_id, {})

    def get_packets_per_second(self):
        return self.stats.get("pps", 0.0)

    def get_last_received(self):
        return self.stats.get("last")

    def get_device_logs(self, device_id):
        logs = []
        if self.latest_log and os.path.exists(self.latest_log):
            try:
                with open(self.latest_log, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        if row.get("device_id") == str(device_id):
                            timestamp = self._parse_datetime(row.get("timestamp"))
                            arrival_time = self._parse_datetime(row.get("arrival_time"))
                            
                            latency = 0.0
                            if timestamp and arrival_time:
                                lat = (arrival_time - timestamp).total_seconds() * 1000
                                latency = lat if 0 <= lat < 60000 else 0.0
                            
                            logs.append({
                                "seq": row.get("seq"),
                                "timestamp": row.get("timestamp"),
                                "timestamp_dt": timestamp,
                                "arrival_dt": arrival_time,
                                "value": row.get("value"),
                                "arrival_time": row.get("arrival_time"),
                                "duplicate": row.get("duplicate_flag") == "1",
                                "gap": row.get("gap_flag") == "1",
                                "latency": latency
                            })
            except Exception:
                pass
        return logs