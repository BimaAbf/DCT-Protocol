from PySide6.QtCore import QObject, Signal, QProcess, QProcessEnvironment
import os
import sys

class ServerController(QObject):
    statusChanged = Signal(bool, str)
    outputReceived = Signal(str)
    serverStarted = Signal()
    serverStopped = Signal()

    def __init__(self, ip="0.0.0.0", port=5000):
        super().__init__()
        self.ip = ip
        self.port = port
        self.running = False
        self.devices = 0
        self.process = None
        
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.script_path = os.path.join(self.base_dir, "Server", "main.py")
        self.working_dir = os.path.join(self.base_dir, "Server")  # Run from Server directory
        
        self._load_env()

    def _load_env(self):
        """Load configuration from .env file"""
        env_path = os.path.join(self.base_dir, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path) as f:
                    for line in f:
                        if '=' in line and not line.strip().startswith('#'):
                            key, value = line.strip().split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            if key == 'HOST':
                                self.ip = value
                            elif key == 'PORT':
                                try:
                                    self.port = int(value)
                                except ValueError:
                                    pass
            except Exception:
                pass

    def is_running(self):
        return self.process is not None and self.process.state() == QProcess.Running

    def start(self):
        if self.is_running():
            self.outputReceived.emit("[Server] Already running\n")
            return
            
        self.process = QProcess()
        self.process.setProgram(sys.executable)
        self.process.setArguments(["main.py"])  # Just the filename since we run from Server directory
        self.process.setWorkingDirectory(self.working_dir)
        
        env = QProcessEnvironment.systemEnvironment()
        current_path = env.value("PYTHONPATH", "")
        if current_path:
            env.insert("PYTHONPATH", f"{self.base_dir}:{current_path}")
        else:
            env.insert("PYTHONPATH", self.base_dir)
        self.process.setProcessEnvironment(env)
        
        self.process.started.connect(self._on_started)
        self.process.finished.connect(self._on_finished)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.errorOccurred.connect(self._on_error)
        
        self.outputReceived.emit(f"[Server] Starting server on {self.ip}:{self.port}...\n")
        self.process.start()

    def _on_started(self):
        self.running = True
        self._update_status(True, "Server running")
        self.serverStarted.emit()
        self.outputReceived.emit("[Server] Process started\n")
        
    def _on_finished(self, code, status):
        self.running = False
        self.process = None
        self._update_status(False, f"Stopped (Code: {code})")
        self.serverStopped.emit()
        self.outputReceived.emit(f"[Server] Process exited with code {code}\n")

    def _on_error(self, error):
        error_msgs = {
            QProcess.FailedToStart: "Failed to start",
            QProcess.Crashed: "Crashed",
            QProcess.Timedout: "Timed out",
            QProcess.WriteError: "Write error",
            QProcess.ReadError: "Read error",
        }
        msg = error_msgs.get(error, f"Unknown error ({error})")
        self.outputReceived.emit(f"[Server Error] {msg}\n")

    def _on_stdout(self):
        text = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace')
        if text:
            self.outputReceived.emit(text)

    def _on_stderr(self):
        text = self.process.readAllStandardError().data().decode('utf-8', errors='replace')
        if text:
            self.outputReceived.emit(text)

    def stop(self):
        if self.process and self.process.state() != QProcess.NotRunning:
            self.outputReceived.emit("[Server] Stopping server...\n")
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.outputReceived.emit("[Server] Force killing...\n")
                self.process.kill()
                self.process.waitForFinished(1000)
            self._update_status(False, "Stopped")

    def _update_status(self, running, message):
        self.running = running
        self.statusChanged.emit(running, message)

    def update_device_count(self, count):
        if count != self.devices:
            self.devices = count
            self.statusChanged.emit(self.running, f"Devices: {self.devices}")
