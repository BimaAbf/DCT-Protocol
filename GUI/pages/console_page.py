from __future__ import annotations
import os, subprocess, re
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor, QColor
from PySide6.QtWidgets import QFrame, QLabel, QWidget, QHBoxLayout, QVBoxLayout, QTextEdit, QPushButton, QTabBar, QStackedWidget
from style.utils import apply_shadow

def get_client_color(client_id):
    hue = (client_id * 137) % 360
    return QColor.fromHsl(hue, 180, 160)

class ConsoleWidget(QTextEdit):
    command_entered = Signal(str)

    def __init__(self, parent=None, interactive=True):
        super().__init__(parent)
        self.interactive = interactive
        self.setPlaceholderText("PowerShell Console..." if interactive else "")
        self.setMinimumHeight(320)
        self.prompt, self.history, self.history_index = "", [], 0
        self.last_position = self.textCursor().position()
        self.tab_matches, self.tab_index, self.tab_prefix, self.tab_start_pos = [], 0, "", 0
        if not interactive:
            self.setReadOnly(True)

    def keyPressEvent(self, event):
        if not self.interactive:
            if event.modifiers() == Qt.ControlModifier and event.key() in (Qt.Key_C, Qt.Key_A):
                super().keyPressEvent(event)
            return
        if event.modifiers() == Qt.ControlModifier and event.key() in (Qt.Key_C, Qt.Key_V, Qt.Key_A, Qt.Key_X):
            super().keyPressEvent(event)
            return
        cursor = self.textCursor()
        if cursor.position() < self.last_position and event.key() not in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Control, Qt.Key_Shift, Qt.Key_Tab):
            cursor.movePosition(QTextCursor.End)
            self.setTextCursor(cursor)
        handlers = {Qt.Key_Tab: self._handle_tab, Qt.Key_Return: self._handle_enter, Qt.Key_Enter: self._handle_enter,
                    Qt.Key_Up: lambda: self._navigate_history(-1), Qt.Key_Down: lambda: self._navigate_history(1)}
        if h := handlers.get(event.key()): h()
        elif event.key() == Qt.Key_Backspace and cursor.position() <= self.last_position: return
        else: self.tab_matches, self.tab_index = [], 0; super().keyPressEvent(event)

    def _handle_tab(self):
        full, pos = self.toPlainText(), self.textCursor().position()
        if pos < self.last_position: return
        before = full[self.last_position:pos]
        if self.tab_matches and full[self.tab_start_pos:pos] in self.tab_matches:
            self.tab_index = (self.tab_index + 1) % len(self.tab_matches)
            self._apply_completion()
            return
        if '"' in before:
            if before.count('"') % 2 == 1:
                lq = before.rfind('"')
                prefix, pstart = before[lq+1:], lq+1
            else:
                after = before[before.rfind('"')+1:]
                parts = after.split()
                prefix = parts[-1] if parts else ""
                pstart = len(before) - len(prefix)
        else:
            parts = before.split()
            prefix = parts[-1] if parts else ""
            pstart = len(before) - len(prefix)
        matches, sdir, sp = [], ".", prefix.strip('"')
        if "/" in sp or "\\" in sp: sdir, sp = os.path.dirname(sp) or ".", os.path.basename(sp)
        try:
            if os.path.isdir(sdir):
                for item in sorted(os.listdir(sdir)):
                    if item.lower().startswith(sp.lower()):
                        p = os.path.join(sdir, item) if sdir != "." else item
                        p = p.replace("\\", "/") + ("/" if os.path.isdir(p) else "")
                        matches.append(f'"{p}"' if " " in p else p)
        except: pass
        if len(before.split()) <= 1 and prefix:
            for c in ["help", "clear", "cls", "cd", "dir", "ls", "python", "pip", "git", "exit"]:
                if c.startswith(prefix.lower()) and c not in matches: matches.append(c)
        if not matches: return
        self.tab_matches, self.tab_index, self.tab_prefix, self.tab_start_pos = matches, 0, prefix, self.last_position + pstart
        self._apply_completion()

    def _apply_completion(self):
        if not self.tab_matches: return
        cursor = self.textCursor()
        cursor.setPosition(self.tab_start_pos)
        cursor.setPosition(cursor.position() + len(self.toPlainText()[self.tab_start_pos:self.textCursor().position()]), QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(self.tab_matches[self.tab_index])
        self.setTextCursor(cursor)

    def _handle_enter(self):
        cmd = self.toPlainText()[self.last_position:].strip()
        self.moveCursor(QTextCursor.End)
        self.insertPlainText("\n")
        self.last_position = self.textCursor().position()
        if cmd:
            self.history.append(cmd)
            self.history_index = len(self.history)
            self.command_entered.emit(cmd)

    def _navigate_history(self, d):
        if not self.history: return
        self.history_index = max(0, min(len(self.history), self.history_index + d))
        cursor = self.textCursor()
        cursor.setPosition(self.last_position)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        if 0 <= self.history_index < len(self.history): self.insertPlainText(self.history[self.history_index])

    def append_output(self, text):
        self.moveCursor(QTextCursor.End)
        if text: self.insertPlainText(text)
        self.last_position = self.textCursor().position()
        self.ensureCursorVisible()

    def show_prompt(self):
        if not self.interactive: return
        self.moveCursor(QTextCursor.End)
        if self.prompt: self.insertPlainText(self.prompt)
        self.last_position = self.textCursor().position()
        self.ensureCursorVisible()

class ConsolePage(QWidget):
    def __init__(self, console_controller, server_controller=None, clients_controller=None, parent=None):
        super().__init__(parent)
        self.console_controller = console_controller
        self.server_controller = server_controller
        self.clients_controller = clients_controller
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        header = QHBoxLayout()
        header.addWidget(QLabel("Console", objectName="ConsoleTitle"))
        header.addStretch(1)
        header.addWidget(QLabel("Type 'help' for commands", objectName="ConsoleHelpHint"))
        for txt, w, fn in [("Open Terminal", 120, self._open_terminal), ("Open tmux", 100, self._open_tmux), ("Restart", 80, self._restart)]:
            btn = QPushButton(txt)
            btn.setFixedSize(w, 32)
            btn.clicked.connect(fn)
            header.addWidget(btn)
        layout.addLayout(header)
        container = QFrame(objectName="ConsoleContainer")
        container.setProperty("class", "page-card")
        container.setStyleSheet("#ConsoleContainer { background-color: #FFFFFF; border-radius: 12px; border: none; }")
        apply_shadow(container, 20, 5, 50)
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(15, 15, 15, 15)
        clayout.setSpacing(10)
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.setSpacing(4)
        for i, txt in enumerate(["Terminal", "Server", "Clients"]):
            btn = QPushButton(txt)
            btn.setCheckable(True)
            btn.setFixedSize(70, 26)
            btn.setStyleSheet("""
                QPushButton { background: #1E293B; color: #94A3B8; border: none; border-radius: 5px; font-size: 11px; font-weight: 500; }
                QPushButton:checked { background: #3B82F6; color: white; }
                QPushButton:hover:!checked { background: #334155; color: #E2E8F0; }
            """)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            tab_row.addWidget(btn)
            if i == 0: btn.setChecked(True)
            setattr(self, f"tab_btn_{i}", btn)
        tab_row.addStretch()
        clayout.addLayout(tab_row)
        self.stacked = QStackedWidget()
        console_style = "background-color: #0F172A; color: #E2E8F0; border: none; border-radius: 12px; font-family: Consolas, monospace; font-size: 11pt; padding: 12px;"
        self.console_widget = ConsoleWidget(interactive=True)
        self.console_widget.setStyleSheet(console_style)
        self.console_widget.command_entered.connect(self._run_command)
        self.stacked.addWidget(self.console_widget)
        self.server_log_widget = ConsoleWidget(interactive=False)
        self.server_log_widget.setStyleSheet(console_style.replace("#E2E8F0", "#10B981"))
        self.server_log_widget.setPlaceholderText("Server logs will appear here when server is running...")
        self.stacked.addWidget(self.server_log_widget)
        self.client_log_widget = ConsoleWidget(interactive=False)
        self.client_log_widget.setStyleSheet(console_style)
        self.client_log_widget.setPlaceholderText("Client logs will appear here when clients are started from GUI...")
        self.stacked.addWidget(self.client_log_widget)
        clayout.addWidget(self.stacked)
        layout.addWidget(container, 1)
        self.console_controller.outputReceived.connect(self.console_widget.append_output)
        self.console_controller.commandFinished.connect(self.console_widget.show_prompt)
        self.console_controller.finished.connect(lambda x: self.console_widget.append_output(f"[Process exited {x}]"))
        if self.server_controller:
            self.server_controller.logOutput.connect(self._append_server_log)
        if self.clients_controller:
            self.clients_controller.clientLogOutput.connect(self._append_client_log)
        self.console_widget.setFocus()

    def _switch_tab(self, index):
        for i in range(3):
            getattr(self, f"tab_btn_{i}").setChecked(i == index)
        self.stacked.setCurrentIndex(index)
        if index == 0:
            self.console_widget.setFocus()

    def _append_server_log(self, text):
        self.server_log_widget.append_output(text + "\n")

    def _append_client_log(self, text):
        match = re.match(r'\[Client (\d+)\]', text)
        cursor = self.client_log_widget.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = cursor.charFormat()
        fmt.setForeground(get_client_color(int(match.group(1))) if match else QColor("#E2E8F0"))
        cursor.setCharFormat(fmt)
        cursor.insertText(text)
        self.client_log_widget.setTextCursor(cursor)
        self.client_log_widget.last_position = cursor.position()
        self.client_log_widget.ensureCursorVisible()

    def _open_terminal(self):
        try: subprocess.Popen(["wt", "-d", self.base_dir])
        except: 
            try: subprocess.Popen(["powershell", "-NoExit", "-Command", f"cd '{self.base_dir}'"])
            except Exception as e: self.console_widget.append_output(f"\n[Error] {e}\n")

    def _open_tmux(self):
        wsl_path = f"/mnt/{self.base_dir[0].lower()}" + self.base_dir[2:].replace("\\", "/")
        try: subprocess.Popen(["wt", "wsl", "--cd", wsl_path, "-e", "bash", "-c", "tmux new -A -s dct"])
        except:
            try: subprocess.Popen(["wsl", "--cd", wsl_path, "-e", "bash", "-c", "tmux new -A -s dct"])
            except Exception as e: self.console_widget.append_output(f"\n[Error] {e}\n")

    def _restart(self):
        idx = self.stacked.currentIndex()
        if idx == 0:
            self.console_widget.clear()
            self.console_widget.last_position = 0
            self.console_controller.restart_shell()
        elif idx == 1:
            self.server_log_widget.clear()
            self.server_log_widget.last_position = 0
        elif idx == 2:
            self.client_log_widget.clear()
            self.client_log_widget.last_position = 0

    def _run_command(self, cmd):
        if cmd.lower() in {"clear", "cls"}:
            self.console_widget.clear()
            self.console_widget.last_position = 0
            self.console_controller.run_command("cls")
        elif cmd.lower() == "help":
            self.console_widget.append_output("""DCT Protocol Console - Quick Reference
======================================
Server:  python Server/main.py
Client:  python Client/main.py <host> --port <port> --mac <mac> --interval <sec> --duration <sec>
Analysis: python Analysis/Analysis.py
Console: clear/cls, help
""")
            self.console_controller.run_command("echo $null")
        else: self.console_controller.run_command(cmd)
