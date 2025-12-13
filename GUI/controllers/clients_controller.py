from PySide6.QtCore import QObject, Signal, QProcess, QProcessEnvironment
import datetime
import os
import sys

class ClientsController(QObject):
    clientsUpdated = Signal(list)
    clientSelected = Signal(dict)

    def __init__(self, logs_controller=None):
        super().__init__()
        self.clients = []
        self.logs_controller = logs_controller
        self.processes = []
        self.session_start_time = datetime.datetime.now()  # Track when GUI started
        self.client_configs = []  # Store client configurations in order added
        self.assigned_configs = set()  # Track which configs have been assigned
        
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.script_path = os.path.join(self.base_dir, "Client", "main.py")
        self.working_dir = self.base_dir
        
        if self.logs_controller:
            self.logs_controller.logsUpdated.connect(self.refresh)
        
        self.refresh()

    def _get_config_for_device(self, device_id):
        """Try to find a config for this device_id based on order"""
        # Convert device_id to index (device_id 1 -> index 0)
        try:
            idx = int(device_id) - 1
            if 0 <= idx < len(self.client_configs):
                return self.client_configs[idx]
        except (ValueError, TypeError):
            pass
        return {}

    def refresh(self):
        now = datetime.datetime.now()
        device_ids = self.logs_controller.get_device_ids() if self.logs_controller else []
        self.clients = []
        
        for device_id in device_ids:
            metrics = self.logs_controller.get_device_metrics(device_id)
            last_seen = metrics.get("last_seen")
            
            # Skip clients that haven't been seen since GUI started
            if not last_seen or not isinstance(last_seen, datetime.datetime):
                continue
            if last_seen < self.session_start_time:
                continue
            
            is_online = (now - last_seen).total_seconds() < 30
            
            # Get stored config for this device (based on device_id order)
            config = self._get_config_for_device(device_id)
            
            self.clients.append({
                "device_id": device_id,
                "packets_sent": metrics.get("packets", 0),
                "duplicates": metrics.get("duplicates", 0),
                "gaps": metrics.get("gaps", 0),
                "avg_latency": metrics.get("avg_latency"),
                "avg_cpu": metrics.get("avg_cpu"),
                "avg_packet_size": metrics.get("avg_packet_size"),
                "last_seen": last_seen.strftime("%H:%M:%S"),
                "is_online": is_online,
                # Include stored config data
                "mac": config.get("mac"),
                "server_ip": config.get("ip"),
                "port": config.get("port"),
                "interval": config.get("interval"),
                "duration": config.get("duration"),
                "batch_size": config.get("batch_size"),
                "delta_thresh": config.get("delta"),
            })
            
        self.clientsUpdated.emit(self.clients)

    def get_clients(self):
        return list(self.clients)

    def add_client(self, data):
        # batch_size: 1 = no batching, >1 = batching enabled with that size
        batch_size = str(data.get("batch_size", "1"))
        seed = str(data.get("seed", 100))
        
        # Store client config in order (will be matched to device_id later)
        self.client_configs.append({
            "ip": data.get("ip", "127.0.0.1"),
            "port": data.get("port", "5000"),
            "interval": data.get("interval", "1.0"),
            "duration": data.get("duration", "60"),
            "mac": data.get("mac", "00:00:00:00:00:00"),
            "seed": seed,
            "delta": data.get("delta", "5"),
            "batch_size": batch_size,
        })
        
        args = [
            self.script_path,
            data.get("ip", "127.0.0.1"),
            "--port", str(data.get("port", 5000)),
            "--interval", str(data.get("interval", 1.0)),
            "--duration", str(data.get("duration", 60)),
            "--mac", str(data.get("mac", "00:00:00:00:00:00")),
            "--seed", seed,
            "--delta-thresh", str(data.get("delta", 5)),
            "--batching", batch_size
        ]
        
        process = QProcess()
        process.setProgram(sys.executable)
        process.setArguments(args)
        process.setWorkingDirectory(self.working_dir)
        
        env = QProcessEnvironment.systemEnvironment()
        current_path = env.value("PYTHONPATH", "")
        if current_path:
            env.insert("PYTHONPATH", f"{self.base_dir};{current_path}")
        else:
            env.insert("PYTHONPATH", self.base_dir)
        process.setProcessEnvironment(env)
        
        process.finished.connect(lambda: self._cleanup_process(process))
        process.start()
        self.processes.append(process)

    def _cleanup_process(self, process):
        if process in self.processes:
            self.processes.remove(process)
        process.deleteLater()

    def select_client(self, device_id):
        client = next((c for c in self.clients if c.get("device_id") == device_id), None)
        if client:
            self.clientSelected.emit(client)
        return client