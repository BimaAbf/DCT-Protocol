from __future__ import annotations
import os, re
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QFrame, QLabel, QWidget, QHBoxLayout, QVBoxLayout, QTextEdit)
from GUI.style.utils import apply_shadow

class ConsoleWidget(QTextEdit):
    command_entered = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Console output...")
        self.setMinimumHeight(320)
        self.prompt = "> "
        self.history = []
        self.history_index = 0
        self.insertPlainText(self.prompt)
        self.last_position = self.textCursor().position()

    def keyPressEvent(self, event):
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
            super().keyPressEvent(event)

    def _handle_tab(self):
        text = self.toPlainText()[self.last_position:]
        cursor_pos = self.textCursor().position() - self.last_position
        
        if cursor_pos < 0:
            return
            
        parts = re.split(r'\s+', text[:cursor_pos]) or ['']
        prefix = parts[-1]
        
        if not prefix:
            return
            
        candidates = ["help", "clear", "cls", "python", "Client/client.py", "Server/server.py", "Analysis/Analysis.py", "dir", "ls", "cd", "exit"]
        try:
            directory = os.path.dirname(prefix) or "."
            if os.path.isdir(directory):
                candidates.extend([(os.path.join(directory, f) if directory != "." else f).replace(os.sep, "/") for f in os.listdir(directory)])
        except:
            pass
            
        matches = [x for x in candidates if x.startswith(prefix)]
        if matches:
            completion = matches[0] if len(matches) == 1 else os.path.commonprefix(matches)
            if len(completion) > len(prefix):
                self.insertPlainText(completion[len(prefix):])

    def _handle_enter(self):
        command = self.toPlainText()[self.last_position:].strip()
        self.moveCursor(QTextCursor.End)
        self.insertPlainText("\n")
        
        if command:
            self.history.append(command)
            self.history_index = len(self.history)
            self.command_entered.emit(command)
        else:
            self.show_prompt()

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

    def _run_command(self, command):
        if command.lower() in {"clear", "cls"}:
            self.console_widget.clear()
            self.console_widget.show_prompt()
        elif command.lower() == "help":
            self.console_widget.append_output("Available Commands:\n  python Client/client.py [args]\n  python Server/server.py [args]\n  python Analysis/Analysis.py\n  clear / cls\n  help\n\nStandard shell commands supported.\n")
            self.console_widget.show_prompt()
        else:
            self.console_controller.run_command(command)
