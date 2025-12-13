from PySide6.QtCore import QObject, Signal, QProcess
import platform, shutil, os

class ConsoleController(QObject):
    outputReceived = Signal(str)
    finished = Signal(int)
    commandFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.process.setWorkingDirectory(self.base_dir)
        self.last_command, self._restarting = None, False
        self._start_shell()

    def _on_finished(self, code, status):
        if not self._restarting: self.finished.emit(code)

    def _on_error(self, error):
        if not self._restarting: self.outputReceived.emit(f"\n[Error] {error}\n")

    def _start_shell(self):
        if platform.system() == "Windows":
            self.process.start(shutil.which("powershell") or "powershell.exe",
                ["-NoLogo", "-NoExit", "-ExecutionPolicy", "Bypass",
                 "-Command", f"cd '{self.base_dir}'; $OutputEncoding = [System.Text.Encoding]::UTF8; Clear-Host"])
        else:
            self.process.start(shutil.which("bash") or "/bin/sh", ["-i"])
            if self.process.waitForStarted(2000):
                self.process.write(f"cd '{self.base_dir}' && clear\n".encode('utf-8'))
        if not self.process.waitForStarted(3000):
            self.outputReceived.emit("\n[Error] Shell failed to start.\n")

    def run_command(self, command):
        if not command: return
        if self.process.state() == QProcess.NotRunning: self._start_shell()
        self.last_command = command
        self.process.write((command + "\n").encode('utf-8'))

    def _read_output(self):
        text = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace')
        if text:
            if self.last_command and text.strip().startswith(self.last_command):
                text = text.replace(self.last_command, '', 1).lstrip('\r\n')
                self.last_command = None
            if text: self.outputReceived.emit(text)

    def restart_shell(self):
        self._restarting = True
        if self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
        self._restarting = False
        self._start_shell()

    def cleanup(self):
        if self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000): self.process.kill()
