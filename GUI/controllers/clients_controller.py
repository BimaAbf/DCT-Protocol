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
        
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.script_path = os.path.join(self.base_dir, "Client", "main.py")
        self.working_dir = self.base_dir
        
        if self.logs_controller:
            self.logs_controller.logsUpdated.connect(self.refresh)
        
        self.refresh()

    def refresh(self):
        now = datetime.datetime.now()
        device_ids = self.logs_controller.get_device_ids() if self.logs_controller else []
        self.clients = []
        
        for device_id in device_ids:
            metrics = self.logs_controller.get_device_metrics(device_id)
            last_seen = metrics.get("last_seen") or now
            
            is_online = False
            if isinstance(last_seen, datetime.datetime):
                is_online = (now - last_seen).total_seconds() < 30
            
            self.clients.append({
                "device_id": device_id,
                "packets_sent": metrics.get("packets", 0),
                "duplicates": metrics.get("duplicates", 0),
                "gaps": metrics.get("gaps", 0),
                "avg_latency": metrics.get("avg_latency"),
                "avg_cpu": metrics.get("avg_cpu"),
                "avg_packet_size": metrics.get("avg_packet_size"),
                "last_seen": last_seen.strftime("%H:%M:%S") if isinstance(last_seen, datetime.datetime) else str(last_seen),
                "is_online": is_online
            })
            
        self.clientsUpdated.emit(self.clients)

    def get_clients(self):
        return list(self.clients)

    def add_client(self, data):
        args = [
            self.script_path,
            data.get("ip", "127.0.0.1"),
            "--port", str(data.get("port", 5000)),
            "--interval", str(data.get("interval", 1.0)),
            "--duration", str(data.get("duration", 60)),
            "--mac", str(data.get("mac", "00:00:00:00:00:00")),
            "--seed", str(data.get("seed", 100)),
            "--delta-thresh", str(data.get("delta", 5)),
            "--batching", "5" if data.get("batching") == "Enabled" else "1"
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