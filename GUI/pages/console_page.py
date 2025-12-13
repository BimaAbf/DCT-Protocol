from __future__ import annotations
import os
import subprocess
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QFrame, QLabel, QWidget, QHBoxLayout, QVBoxLayout, QTextEdit, QPushButton
from style.utils import apply_shadow

class ConsoleWidget(QTextEdit):
    command_entered = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("PowerShell Console...")
        self.setMinimumHeight(320)
        self.prompt = ""
        self.history = []
        self.history_index = 0
        self.last_position = self.textCursor().position()

        self.tab_matches = []
        self.tab_index = 0
        self.tab_prefix = ""
        self.tab_start_pos = 0

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            if event.key() in (Qt.Key_C, Qt.Key_V, Qt.Key_A, Qt.Key_X):
                super().keyPressEvent(event)
                return
        
        cursor = self.textCursor()
        if cursor.position() < self.last_position and event.key() not in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Control, Qt.Key_Shift, Qt.Key_Tab):
            cursor.movePosition(QTextCursor.End)
            self.setTextCursor(cursor)
            
        key_map = {
            Qt.Key_Tab: self._handle_tab,
            Qt.Key_Return: self._handle_enter,
            Qt.Key_Enter: self._handle_enter,
            Qt.Key_Up: lambda: self._navigate_history(-1),
            Qt.Key_Down: lambda: self._navigate_history(1)
        }
        
        if handler := key_map.get(event.key()):
            handler()
        elif event.key() == Qt.Key_Backspace and cursor.position() <= self.last_position:
            return
        else:
            self.tab_matches = []
            self.tab_index = 0
            super().keyPressEvent(event)

    def _handle_tab(self):
        full_text = self.toPlainText()
        cursor_pos = self.textCursor().position()
        
        if cursor_pos < self.last_position:
            return
        
        before_cursor = full_text[self.last_position:cursor_pos]
        
        if self.tab_matches:
            current_text = full_text[self.tab_start_pos:cursor_pos]
            if current_text in self.tab_matches:
                self.tab_index = (self.tab_index + 1) % len(self.tab_matches)
                self._apply_completion()
                return
        
        prefix = ""
        prefix_start_in_cmd = 0 
        
        if '"' in before_cursor:
            quote_count = before_cursor.count('"')
            if quote_count % 2 == 1: 
                last_quote = before_cursor.rfind('"')
                prefix = before_cursor[last_quote + 1:]
                prefix_start_in_cmd = last_quote + 1
            else:
                after_quote = before_cursor[before_cursor.rfind('"') + 1:]
                parts = after_quote.split()
                prefix = parts[-1] if parts else ""
                prefix_start_in_cmd = len(before_cursor) - len(prefix)
        else:
            parts = before_cursor.split()
            prefix = parts[-1] if parts else ""
            prefix_start_in_cmd = len(before_cursor) - len(prefix)
        
        matches = []
        search_dir = "."
        search_prefix = prefix.strip('"')
        
        if "/" in search_prefix or "\\" in search_prefix:
            search_dir = os.path.dirname(search_prefix) or "."
            search_prefix = os.path.basename(search_prefix)
        
        try:
            if os.path.isdir(search_dir):
                for item in sorted(os.listdir(search_dir)):
                    if item.lower().startswith(search_prefix.lower()):
                        path = os.path.join(search_dir, item) if search_dir != "." else item
                        path = path.replace("\\", "/")
                        if os.path.isdir(path):
                            path += "/"
                        if " " in path:
                            path = f'"{path}"'
                        matches.append(path)
        except:
            pass
        
        parts = before_cursor.split()
        if len(parts) <= 1 and prefix:
            cmds = ["help", "clear", "cls", "cd", "dir", "ls", "python", "pip", "git", "exit"]
            for c in cmds:
                if c.startswith(prefix.lower()) and c not in matches:
                    matches.append(c)
        
        if not matches:
            return
        
        self.tab_matches = matches
        self.tab_index = 0
        self.tab_prefix = prefix
        self.tab_start_pos = self.last_position + prefix_start_in_cmd
        
        self._apply_completion()
    
    def _apply_completion(self):
        if not self.tab_matches:
            return
        cursor = self.textCursor()
        current_pos = cursor.position()
        cursor.setPosition(self.tab_start_pos)
        cursor.setPosition(current_pos, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(self.tab_matches[self.tab_index])
        self.setTextCursor(cursor)

    def _handle_enter(self):
        command = self.toPlainText()[self.last_position:].strip()
        self.moveCursor(QTextCursor.End)
        self.insertPlainText("\n")
        self.last_position = self.textCursor().position()
        
        if command:
            self.history.append(command)
            self.history_index = len(self.history)
            self.command_entered.emit(command)

    def _navigate_history(self, direction):
        if not self.history:
            return
            
        self.history_index = max(0, min(len(self.history), self.history_index + direction))
        cursor = self.textCursor()
        cursor.setPosition(self.last_position)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        
        if 0 <= self.history_index < len(self.history):
            self.insertPlainText(self.history[self.history_index])

    def append_output(self, text):
        self.moveCursor(QTextCursor.End)
        if text:
            self.insertPlainText(text)
        self.last_position = self.textCursor().position()
        self.ensureCursorVisible()

    def show_prompt(self):
        self.moveCursor(QTextCursor.End)
        if self.prompt:
            self.insertPlainText(self.prompt)
        self.last_position = self.textCursor().position()
        self.ensureCursorVisible()

class ConsolePage(QWidget):
    def __init__(self, console_controller, parent=None):
        super().__init__(parent)
        self.console_controller = console_controller
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(20)
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Console", objectName="ConsoleTitle"))
        header_layout.addStretch(1)
        header_layout.addWidget(QLabel("Type 'help' for commands", objectName="ConsoleHelpHint"))
        
        # Button to open external terminal
        self.terminal_btn = QPushButton("Open Terminal")
        self.terminal_btn.setFixedSize(120, 32)
        self.terminal_btn.clicked.connect(self._open_terminal)
        header_layout.addWidget(self.terminal_btn)
        
        # Button to open WSL with tmux
        self.tmux_btn = QPushButton("Open tmux")
        self.tmux_btn.setFixedSize(100, 32)
        self.tmux_btn.clicked.connect(self._open_tmux)
        header_layout.addWidget(self.tmux_btn)
        
        # Button to restart terminal
        self.kill_btn = QPushButton("Restart")
        self.kill_btn.setFixedSize(80, 32)
        self.kill_btn.clicked.connect(self._restart_terminal)
        header_layout.addWidget(self.kill_btn)
        
        layout.addLayout(header_layout)
        
        container = QFrame(objectName="ConsoleContainer")
        container.setProperty("class", "page-card")
        container.setStyleSheet("#ConsoleContainer { background-color: #FFFFFF; border-radius: 12px; border: none; }")
        apply_shadow(container, 20, 5, 50)
        
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(15, 15, 15, 15)
        
        self.console_widget = ConsoleWidget()
        self.console_widget.setStyleSheet("background-color: #0F172A; color: #E2E8F0; border: none; border-radius: 12px; font-family: Consolas, monospace; font-size: 11pt; padding: 12px;")
        self.console_widget.command_entered.connect(self._run_command)
        container_layout.addWidget(self.console_widget)
        layout.addWidget(container, 1)
        
        self.console_controller.outputReceived.connect(self.console_widget.append_output)
        self.console_controller.commandFinished.connect(self.console_widget.show_prompt)
        self.console_controller.finished.connect(lambda x: self.console_widget.append_output(f"[Process exited {x}]"))
        self.console_widget.setFocus()

    def _open_terminal(self):
        """Open external terminal in project directory"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        try:
            # Try Windows Terminal first
            subprocess.Popen(["wt", "-d", base_dir])
        except FileNotFoundError:
            try:
                # Fallback: open PowerShell directly
                subprocess.Popen(["powershell", "-NoExit", "-Command", f"cd '{base_dir}'"])
            except Exception as e:
                self.console_widget.append_output(f"\n[Error] Could not open terminal: {e}\n")

    def _open_tmux(self):
        """Open WSL with tmux in project directory"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        drive = base_dir[0].lower()
        wsl_path = f"/mnt/{drive}" + base_dir[2:].replace("\\", "/")
        
        try:
            # Open Windows Terminal with WSL, cd to project, start tmux
            subprocess.Popen(["wt", "wsl", "--cd", wsl_path, "-e", "bash", "-c", "tmux new -A -s dct"])
        except FileNotFoundError:
            try:
                subprocess.Popen(["wsl", "--cd", wsl_path, "-e", "bash", "-c", "tmux new -A -s dct"])
            except Exception as e:
                self.console_widget.append_output(f"\n[Error] Could not open tmux: {e}\n")

    def _restart_terminal(self):
        """Restart the terminal"""
        self.console_widget.clear()
        self.console_widget.last_position = 0
        self.console_controller.restart_shell()

    def _run_command(self, command):
        if command.lower() in {"clear", "cls"}:
            self.console_widget.clear()
            self.console_widget.last_position = 0
            self.console_controller.run_command("cls")
        elif command.lower() == "help":
            help_text = """DCT Protocol Console - Quick Reference
======================================
Server:
  python Server/main.py          Start the server

Client:
  python Client/main.py <host> --port <port> --mac <mac> --interval <sec> --duration <sec>
  Example: python Client/main.py 127.0.0.1 --port 5000 --mac AA:BB:CC:DD:EE:FF --interval 1 --duration 60

Analysis:
  python Analysis/Analysis.py    Run analysis on logs

Console:
  clear / cls                    Clear the console
  help                           Show this help

PowerShell commands also work (dir, cd, etc.)
"""
            self.console_widget.append_output(help_text)
            self.console_controller.run_command("echo $null")
        else:
            self.console_controller.run_command(command)
