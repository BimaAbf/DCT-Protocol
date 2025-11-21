from PySide6.QtCore import QObject, Signal, QProcess
import platform
import shutil

class ConsoleController(QObject):
    outputReceived = Signal(str)
    finished = Signal(int)
    commandFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(lambda code, _: self.finished.emit(code))
        self.process.errorOccurred.connect(lambda error: self.outputReceived.emit(f"\n[Error] {error}\n"))
        self.sentinel = "__DCT_DONE__"
        self._start_shell()

    def _start_shell(self):
        if platform.system() == "Windows":
            self.process.start(shutil.which("powershell") or "powershell.exe", ["-NoLogo"])
            if self.process.waitForStarted(1000):
                self.process.write(b"$OutputEncoding = [System.Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n")
        else:
            self.process.start(shutil.which("bash") or "/bin/sh", ["-i"])
        
        if not self.process.waitForStarted(2000):
            self.outputReceived.emit("\n[Error] Shell failed.\n")

    def run_command(self, command):
        if not command:
            return
        
        if self.process.state() == QProcess.NotRunning:
            self._start_shell()
            
        echo_cmd = f"; Write-Output '{self.sentinel}'\n" if platform.system() == "Windows" else f"; echo '{self.sentinel}'\n"
        self.process.write((command + echo_cmd).encode('utf-8'))

    def _read_output(self):
        text = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace')
        if self.sentinel in text:
            parts = text.split(self.sentinel)
            for i, part in enumerate(parts):
                if part.strip():
                    self.outputReceived.emit(part.strip())
                if i < len(parts) - 1:
                    self.commandFinished.emit()
        else:
            self.outputReceived.emit(text)

    def cleanup(self):
        if self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
