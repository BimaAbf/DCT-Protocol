from PySide6.QtCore import QObject, Signal, QProcess, QProcessEnvironment
import datetime, os, sys

class ClientsController(QObject):
    clientsUpdated = Signal(list)
    clientSelected = Signal(dict)
    clientLogOutput = Signal(str)

    def __init__(self, logs_controller=None):
        super().__init__()
        self.clients, self.processes, self.client_configs = [], [], []
        self.logs_controller = logs_controller
        self.session_start_time = datetime.datetime.now()
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.script_path = os.path.join(self.base_dir, "Client", "main.py")
        if self.logs_controller:
            self.logs_controller.logsUpdated.connect(self.refresh)
        self.refresh()

    def _get_config_for_device(self, device_id):
        try:
            idx = int(device_id) - 1
            if 0 <= idx < len(self.client_configs): return self.client_configs[idx]
        except (ValueError, TypeError): pass
        return {}

    def reset_session(self):
        self.session_start_time = datetime.datetime.now()
        self.client_configs = []
        self.refresh()

    def refresh(self):
        now = datetime.datetime.now()
        device_ids = self.logs_controller.get_device_ids() if self.logs_controller else []
        self.clients = []
        for device_id in device_ids:
            metrics = self.logs_controller.get_device_metrics(device_id)
            last_seen = metrics.get("last_seen")
            if not last_seen or not isinstance(last_seen, datetime.datetime):
                continue
            if last_seen < self.session_start_time:
                continue
            config = self._get_config_for_device(device_id)
            self.clients.append({
                "device_id": device_id, "packets_sent": metrics.get("packets", 0),
                "duplicates": metrics.get("duplicates", 0), "gaps": metrics.get("gaps", 0),
                "avg_latency": metrics.get("avg_latency"), "avg_cpu": metrics.get("avg_cpu"),
                "avg_packet_size": metrics.get("avg_packet_size"),
                "last_seen": last_seen.strftime("%H:%M:%S"),
                "is_online": (now - last_seen).total_seconds() < 30,
                "mac": config.get("mac"), "server_ip": config.get("ip"), "port": config.get("port"),
                "interval": config.get("interval"), "duration": config.get("duration"),
                "batch_size": config.get("batch_size"), "delta_thresh": config.get("delta"),
            })
        self.clientsUpdated.emit(self.clients)

    def get_clients(self): return list(self.clients)

    def add_client(self, data):
        batch_size, seed = str(data.get("batch_size", "1")), str(data.get("seed", 100))
        client_num = len(self.client_configs) + 1
        self.client_configs.append({
            "ip": data.get("ip", "127.0.0.1"), "port": data.get("port", "5000"),
            "interval": data.get("interval", "1.0"), "duration": data.get("duration", "60"),
            "mac": data.get("mac", "00:00:00:00:00:00"), "seed": seed,
            "delta": data.get("delta", "5"), "batch_size": batch_size,
        })
        args = [self.script_path, data.get("ip", "127.0.0.1"),
                "--port", str(data.get("port", 5000)), "--interval", str(data.get("interval", 1.0)),
                "--duration", str(data.get("duration", 60)), "--mac", str(data.get("mac", "00:00:00:00:00:00")),
                "--seed", seed, "--delta-thresh", str(data.get("delta", 5)), "--batching", batch_size]
        process = QProcess()
        process.setProgram(sys.executable)
        process.setArguments(args)
        process.setWorkingDirectory(self.base_dir)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONPATH", f"{self.base_dir};{env.value('PYTHONPATH', '')}" if env.value("PYTHONPATH") else self.base_dir)
        process.setProcessEnvironment(env)
        process.readyReadStandardOutput.connect(lambda p=process, n=client_num: self._read_client_output(p, n))
        process.readyReadStandardError.connect(lambda p=process, n=client_num: self._read_client_output(p, n, True))
        process.finished.connect(lambda code, _, p=process, n=client_num: self._on_client_finished(p, n, code))
        process.start()
        self.processes.append(process)
        self.clientLogOutput.emit(f"[Client {client_num}] Started\n")

    def _read_client_output(self, process, client_num, is_error=False):
        data = process.readAllStandardError() if is_error else process.readAllStandardOutput()
        text = data.data().decode('utf-8', errors='replace').strip()
        if text:
            for line in text.split('\n'):
                self.clientLogOutput.emit(f"[Client {client_num}] {line}\n")

    def _on_client_finished(self, process, client_num, code):
        self.clientLogOutput.emit(f"[Client {client_num}] Finished (code: {code})\n")
        self._cleanup_process(process)

    def _cleanup_process(self, process):
        if process in self.processes: self.processes.remove(process)
        try: process.deleteLater()
        except: pass

    def select_client(self, device_id):
        client = next((c for c in self.clients if c.get("device_id") == device_id), None)
        if client: self.clientSelected.emit(client)
        return client
