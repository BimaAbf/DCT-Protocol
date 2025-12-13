from PySide6.QtCore import QObject, Signal, QProcess, QProcessEnvironment
import os, sys

class ServerController(QObject):
    statusChanged = Signal(bool, str)
    outputReceived = Signal(str)
    logOutput = Signal(str)

    def __init__(self, ip="127.0.0.1", port=5000):
        super().__init__()
        self.ip, self.port, self.running, self.devices, self.process = ip, port, False, 0, None
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.script_path = os.path.join(self.base_dir, "Server", "main.py")
        self._load_env()

    def _load_env(self):
        env_path = os.path.join(self.base_dir, ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        if key.strip() == 'HOST': self.ip = value.strip()
                        elif key.strip() == 'PORT':
                            try: self.port = int(value.strip())
                            except ValueError: pass

    def start(self):
        if self.running: return
        self.process = QProcess()
        self.process.setProgram(sys.executable)
        self.process.setArguments([self.script_path])
        self.process.setWorkingDirectory(self.base_dir)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONPATH", f"{self.base_dir};{env.value('PYTHONPATH', '')}" if env.value("PYTHONPATH") else self.base_dir)
        self.process.setProcessEnvironment(env)

        self.process.started.connect(lambda: self._update_status(True, "Server running"))
        self.process.finished.connect(lambda code, _: self._update_status(False, f"Stopped (Code: {code})"))
        self.process.readyReadStandardOutput.connect(lambda: self._read_output(self.process.readAllStandardOutput))
        self.process.readyReadStandardError.connect(lambda: self._read_output(self.process.readAllStandardError))
        
        self.process.start()

    def stop(self):
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(2000):
                self.process.kill()
                self.process.waitForFinished(1000)
            self._update_status(False, "Stopped")

    def _update_status(self, running, message):
        self.running = running
        if not running: self.process = None
        self.statusChanged.emit(running, message)

    def _read_output(self, read_func):
        text = read_func().data().decode('utf-8', errors='replace').strip()
        if text:
            self.outputReceived.emit(text)
            self.logOutput.emit(text)
