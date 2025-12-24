from PySide6.QtCore import QObject, Signal, QProcess, QProcessEnvironment, QTimer
import datetime
import os
import sys
import random

class ClientProcess:
    """Represents a client process with its configuration and state"""
    
    PENDING = "pending"
    CONNECTING = "connecting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    
    def __init__(self, config: dict, process: QProcess):
        self.config = config
        self.process = process
        self.status = self.PENDING
        self.device_id = None
        self.start_time = None
        self.end_time = None
        self.output_buffer = ""
    
    def get_runtime_seconds(self) -> float:
        """Get the running time in seconds"""
        if not self.start_time:
            return 0.0
        end = self.end_time if self.end_time else datetime.datetime.now()
        return (end - self.start_time).total_seconds()
        
    def get_display_data(self) -> dict:
        """Get data for display in UI"""
        runtime = self.get_runtime_seconds()
        return {
            "mac": self.config.get("mac", "00:00:00:00:00:00"),
            "ip": self.config.get("ip", "127.0.0.1"),
            "port": self.config.get("port", 5000),
            "interval": self.config.get("interval", 1.0),
            "duration": self.config.get("duration", 60),
            "batching": self.config.get("batching", "Disabled"),
            "delta": self.config.get("delta", 5),
            "seed": self.config.get("seed", 100),
            "status": self.status,
            "device_id": self.device_id,
            "is_process": True,  # Flag to indicate this is a managed process
            "is_online": self.status == self.RUNNING,
            "packets_sent": 0,
            "duplicates": 0,
            "gaps": 0,
            "runtime_seconds": runtime,
            "start_time": self.start_time,
        }

class ClientsController(QObject):
    clientsUpdated = Signal(list)
    clientSelected = Signal(dict)
    clientOutputReceived = Signal(str, str)  # mac, output
    processStateChanged = Signal(str, str)  # mac, state

    def __init__(self, logs_controller=None):
        super().__init__()
        self.clients = []  # List of client data from logs
        self.client_processes = {}  # mac -> ClientProcess
        self.logs_controller = logs_controller
        
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.script_path = os.path.join(self.base_dir, "Client", "main.py")
        self.working_dir = os.path.join(self.base_dir, "Client")  # Run from Client directory
        
        if self.logs_controller:
            self.logs_controller.logsUpdated.connect(self.refresh)
        
        # Timer to periodically update client states
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._check_process_states)
        self.refresh_timer.start(1000)
        
        self.refresh()

    def refresh(self):
        """Refresh client list from logs and merge with active processes"""
        now = datetime.datetime.now()
        device_ids = self.logs_controller.get_device_ids() if self.logs_controller else []
        log_clients = {}
        
        # Build clients from logs
        for device_id in device_ids:
            metrics = self.logs_controller.get_device_metrics(device_id)
            last_seen = metrics.get("last_seen") or now
            
            is_online = False
            if isinstance(last_seen, datetime.datetime):
                is_online = (now - last_seen).total_seconds() < 30
            
            log_clients[device_id] = {
                "device_id": device_id,
                "packets_sent": metrics.get("packets", 0),
                "duplicates": metrics.get("duplicates", 0),
                "gaps": metrics.get("gaps", 0),
                "avg_latency": metrics.get("avg_latency"),
                "avg_cpu": metrics.get("avg_cpu"),
                "avg_packet_size": metrics.get("avg_packet_size"),
                "last_seen": last_seen.strftime("%H:%M:%S") if isinstance(last_seen, datetime.datetime) else str(last_seen),
                "is_online": is_online,
                "is_process": False,
            }
        
        # Build unified client list
        self.clients = []
        
        # First add active processes
        for mac, client_proc in list(self.client_processes.items()):
            proc_data = client_proc.get_display_data()
            
            # If we have a device_id and log data, merge them
            if client_proc.device_id and client_proc.device_id in log_clients:
                log_data = log_clients[client_proc.device_id]
                proc_data.update({
                    "packets_sent": log_data.get("packets_sent", 0),
                    "duplicates": log_data.get("duplicates", 0),
                    "gaps": log_data.get("gaps", 0),
                    "avg_latency": log_data.get("avg_latency"),
                    "last_seen": log_data.get("last_seen"),
                })
                # Remove from log_clients so we don't add it again
                del log_clients[client_proc.device_id]
            
            self.clients.append(proc_data)
        
        # Then add remaining clients from logs (not managed by us)
        for device_id, log_data in log_clients.items():
            self.clients.append(log_data)
            
        self.clientsUpdated.emit(self.clients)

    def get_clients(self):
        return list(self.clients)
    
    def get_active_processes(self):
        """Get list of currently running client processes"""
        return [p for p in self.client_processes.values() 
                if p.status in (ClientProcess.PENDING, ClientProcess.CONNECTING, ClientProcess.RUNNING)]

    def _generate_mac(self) -> str:
        """Generate a random MAC address"""
        return ":".join(f"{random.randint(0, 255):02X}" for _ in range(6))

    def add_client(self, data: dict) -> str:
        """Add and start a new client process. Returns the MAC address."""
        mac = data.get("mac", "").strip()
        if not mac or mac == "00:00:00:00:00:00":
            mac = self._generate_mac()
            data["mac"] = mac
        
        # Build command arguments
        args = [
            "main.py",  # Just the filename since we run from Client directory
            data.get("ip", "127.0.0.1"),
            "--port", str(data.get("port", 5000)),
            "--interval", str(data.get("interval", 1.0)),
            "--duration", str(data.get("duration", 60)),
            "--mac", mac,
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
            env.insert("PYTHONPATH", f"{self.base_dir}:{current_path}")
        else:
            env.insert("PYTHONPATH", self.base_dir)
        process.setProcessEnvironment(env)
        
        # Create ClientProcess wrapper
        client_proc = ClientProcess(data, process)
        self.client_processes[mac] = client_proc
        
        # Connect signals
        process.started.connect(lambda m=mac: self._on_client_started(m))
        process.finished.connect(lambda code, status, m=mac: self._on_client_finished(m, code))
        process.readyReadStandardOutput.connect(lambda m=mac: self._on_client_stdout(m))
        process.readyReadStandardError.connect(lambda m=mac: self._on_client_stderr(m))
        process.errorOccurred.connect(lambda err, m=mac: self._on_client_error(m, err))
        
        # Start the process
        process.start()
        client_proc.status = ClientProcess.CONNECTING
        self.refresh()
        
        return mac
    
    def _on_client_started(self, mac: str):
        """Called when a client process starts"""
        if mac in self.client_processes:
            self.client_processes[mac].status = ClientProcess.CONNECTING
            self.client_processes[mac].start_time = datetime.datetime.now()
            self.processStateChanged.emit(mac, ClientProcess.CONNECTING)
            self.refresh()
    
    def _on_client_finished(self, mac: str, code: int):
        """Called when a client process finishes"""
        if mac in self.client_processes:
            self.client_processes[mac].end_time = datetime.datetime.now()
            if code == 0:
                self.client_processes[mac].status = ClientProcess.COMPLETED
            else:
                self.client_processes[mac].status = ClientProcess.FAILED
            self.processStateChanged.emit(mac, self.client_processes[mac].status)
            self.refresh()
    
    def _on_client_error(self, mac: str, error):
        """Called when a client process has an error"""
        if mac in self.client_processes:
            self.client_processes[mac].status = ClientProcess.FAILED
            self.processStateChanged.emit(mac, ClientProcess.FAILED)
            self.clientOutputReceived.emit(mac, f"[Error] Process error: {error}\n")
            self.refresh()
    
    def _on_client_stdout(self, mac: str):
        """Handle stdout from client process"""
        if mac in self.client_processes:
            client_proc = self.client_processes[mac]
            text = client_proc.process.readAllStandardOutput().data().decode('utf-8', errors='replace')
            if text:
                client_proc.output_buffer += text
                self._parse_client_output(mac, text)
                self.clientOutputReceived.emit(mac, text)
    
    def _on_client_stderr(self, mac: str):
        """Handle stderr from client process"""
        if mac in self.client_processes:
            client_proc = self.client_processes[mac]
            text = client_proc.process.readAllStandardError().data().decode('utf-8', errors='replace')
            if text:
                client_proc.output_buffer += text
                self.clientOutputReceived.emit(mac, text)
    
    def _parse_client_output(self, mac: str, text: str):
        """Parse client output to detect device ID assignment"""
        if mac not in self.client_processes:
            return
        
        client_proc = self.client_processes[mac]
        
        # Look for device ID assignment
        if "DeviceID:" in text or "Server assigned DeviceID:" in text:
            try:
                # Try to parse device ID from output
                if "DeviceID:" in text:
                    parts = text.split("DeviceID:")
                    for part in parts[1:]:
                        device_id_str = part.strip().split()[0].strip()
                        if device_id_str.isdigit():
                            client_proc.device_id = device_id_str
                            client_proc.status = ClientProcess.RUNNING
                            self.processStateChanged.emit(mac, ClientProcess.RUNNING)
                            self.refresh()
                            break
            except:
                pass
        
        # Check if client is running
        if "Client running" in text and client_proc.status == ClientProcess.CONNECTING:
            client_proc.status = ClientProcess.RUNNING
            self.processStateChanged.emit(mac, ClientProcess.RUNNING)
            self.refresh()
    
    def _check_process_states(self):
        """Periodically check process states and update"""
        changed = False
        for mac, client_proc in list(self.client_processes.items()):
            if client_proc.process.state() == QProcess.NotRunning:
                if client_proc.status in (ClientProcess.PENDING, ClientProcess.CONNECTING, ClientProcess.RUNNING):
                    client_proc.status = ClientProcess.COMPLETED
                    changed = True
        
        if changed:
            self.refresh()

    def stop_client(self, mac: str):
        """Stop a specific client process"""
        if mac in self.client_processes:
            client_proc = self.client_processes[mac]
            if client_proc.process.state() != QProcess.NotRunning:
                client_proc.process.terminate()
                if not client_proc.process.waitForFinished(2000):
                    client_proc.process.kill()
    
    def stop_all_clients(self):
        """Stop all running client processes"""
        for mac in list(self.client_processes.keys()):
            self.stop_client(mac)
    
    def remove_client(self, mac: str):
        """Remove a completed/failed client from the list"""
        if mac in self.client_processes:
            client_proc = self.client_processes[mac]
            if client_proc.process.state() == QProcess.NotRunning:
                del self.client_processes[mac]
                self.refresh()

    def select_client(self, device_id):
        """Select a client by device ID"""
        client = next((c for c in self.clients if c.get("device_id") == device_id), None)
        if client:
            self.clientSelected.emit(client)
        return client
    
    def cleanup(self):
        """Clean up all processes on shutdown"""
        self.refresh_timer.stop()
        self.stop_all_clients()