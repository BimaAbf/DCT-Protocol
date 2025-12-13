from PySide6.QtCore import QObject, Signal, QTimer
import os, csv
from datetime import datetime
from collections import defaultdict

class LogsController(QObject):
    logsUpdated = Signal(list)
    errorOccurred = Signal(str)

    def __init__(self, logs_dir=None):
        super().__init__()
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if logs_dir is None:
            env_path = os.path.join(base_dir, ".env")
            csv_log_dir = "./logs"
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if '=' in line and not line.strip().startswith('#'):
                            key, value = line.strip().split('=', 1)
                            if key.strip() == 'CSV_LOG_DIR':
                                csv_log_dir = value.strip().strip('"').strip("'")
                                break
            self.logs_dir = os.path.join(base_dir, csv_log_dir[2:] if csv_log_dir.startswith("./") else csv_log_dir)
        else:
            self.logs_dir = logs_dir
        self.latest_log, self.stats, self.metrics = None, {"pps": 0.0, "last": None}, {}
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_logs)
        self.auto_refresh_timer.start(2000)
        self.refresh_logs()

    def refresh_logs(self):
        files = sorted([f for f in os.listdir(self.logs_dir) if f.endswith(('.csv', '.log', '.txt'))]) if os.path.exists(self.logs_dir) else []
        if files:
            self.latest_log = os.path.join(self.logs_dir, files[-1])
            self._analyze_log(self.latest_log)
        self.logsUpdated.emit(files)
        return files

    def read_log(self, filename):
        path = os.path.join(self.logs_dir, filename)
        if not os.path.exists(path): return []
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.reader(f)) if filename.endswith(".csv") else [[line.strip()] for line in f]

    def _parse_datetime(self, value):
        if not value or value == '-': return None
        value = value.replace('Z', '+00:00')
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try: return datetime.strptime(value, fmt)
            except ValueError: pass
        try: return datetime.fromisoformat(value)
        except ValueError: return None

    def _analyze_log(self, path):
        data = defaultdict(lambda: {"pkts": 0, "dups": 0, "gaps": 0, "last": None, "lats": [], "sizes": [], "cpus": []})
        arrivals = []
        try:
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    device_id = row.get("device_id", "unknown")
                    arrival_time = self._parse_datetime(row.get("arrival_time"))
                    timestamp = self._parse_datetime(row.get("timestamp"))
                    if arrival_time: arrivals.append(arrival_time)
                    d = data[device_id]
                    d["pkts"] += 1
                    if row.get("duplicate_flag") == "1": d["dups"] += 1
                    if row.get("gap_flag") == "1": d["gaps"] += 1
                    if arrival_time: d["last"] = arrival_time
                    if arrival_time and timestamp:
                        lat = (arrival_time - timestamp).total_seconds() * 1000
                        if 0 <= lat < 10000: d["lats"].append(lat)
                    if row.get("packet_size"): d["sizes"].append(float(row["packet_size"]))
                    if row.get("cpu_time_ms"): d["cpus"].append(float(row["cpu_time_ms"]))
        except Exception as e:
            self.errorOccurred.emit(str(e))
            return
        span = (max(arrivals) - min(arrivals)).total_seconds() if len(arrivals) > 1 else 0
        self.stats = {"pps": len(arrivals) / span if span > 0 else len(arrivals), "last": max(arrivals) if arrivals else None}
        self.metrics = {did: {"packets": s["pkts"], "duplicates": s["dups"], "gaps": s["gaps"], "last_seen": s["last"],
            "avg_latency": sum(s["lats"]) / len(s["lats"]) if s["lats"] else None,
            "avg_packet_size": sum(s["sizes"]) / len(s["sizes"]) if s["sizes"] else None,
            "avg_cpu": sum(s["cpus"]) / len(s["cpus"]) if s["cpus"] else None} for did, s in data.items()}

    def get_device_ids(self): return sorted(self.metrics.keys())
    def get_device_metrics(self, device_id): return self.metrics.get(device_id, {})
    def get_packets_per_second(self): return self.stats.get("pps", 0.0)
    def get_last_received(self): return self.stats.get("last")

    def get_device_logs(self, device_id):
        logs = []
        if self.latest_log and os.path.exists(self.latest_log):
            with open(self.latest_log, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("device_id") == str(device_id):
                        ts, at = self._parse_datetime(row.get("timestamp")), self._parse_datetime(row.get("arrival_time"))
                        lat = (at - ts).total_seconds() * 1000 if ts and at else 0.0
                        logs.append({"seq": row.get("seq"), "timestamp": row.get("timestamp"), "timestamp_dt": ts,
                            "arrival_dt": at, "value": row.get("value"), "arrival_time": row.get("arrival_time"),
                            "duplicate": row.get("duplicate_flag") == "1", "gap": row.get("gap_flag") == "1",
                            "latency": lat if 0 <= lat < 60000 else 0.0})
        return logs
