from __future__ import annotations
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QComboBox
from style.utils import apply_shadow

def _read_env_defaults():
    """Read HOST and PORT from .env file"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(base_dir, ".env")
    host, port = "127.0.0.1", "5000"
    if os.path.exists(env_path):
        try:
            with open(env_path) as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        key, value = key.strip(), value.strip()
                        if key == 'HOST':
                            # For client, use localhost if server binds to 0.0.0.0
                            host = "127.0.0.1" if value == "0.0.0.0" else value
                        elif key == 'PORT':
                            port = value
        except Exception:
            pass
    return host, port

class ClientFormDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Client")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(700, 600)
        
        container = QFrame(self, objectName="FormContainer")
        container.setProperty("class", "dialog-card")
        apply_shadow(container, 20, 5, 255)
        layout = QVBoxLayout(self)
        layout.addWidget(container)
        
        form_layout = QVBoxLayout(container)
        form_layout.setContentsMargins(40, 40, 40, 40)
        form_layout.setSpacing(25)
        
        header = QLabel("New Client", objectName="FormHeader")
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        form_layout.addWidget(header)
        
        # Read defaults from .env
        default_host, default_port = _read_env_defaults()
        
        self.inputs = {}
        fields = [
            ("ip", "IP Address :", default_host),
            ("interval", "Interval :", "1.0"),
            ("port", "Port :", default_port),
            ("batching", "Batching :", ["Disabled", "Enabled"]),
            ("mac", "MAC Address :", "00:00:00:00:00:00"),
            ("delta", "Delta Thresh :", "1"),
            ("duration", "Duration :", "100"),
            ("seed", "Seed :", "32")
        ]
        
        for i in range(0, len(fields), 2):
            row = QHBoxLayout()
            for key, label, default_value in fields[i:i+2]:
                self._add_field(row, key, label, default_value)
            form_layout.addLayout(row)
            
        form_layout.addStretch(1)
        button_row = QHBoxLayout()
        button_row.setSpacing(20)
        button_row.addStretch(1)
        
        for text, func in [("Send", self.accept), ("Cancel", self.reject)]:
            button = QPushButton(text, objectName="FormButton")
            button.clicked.connect(func)
            button_row.addWidget(button)
            
        button_row.addStretch(1)
        form_layout.addLayout(button_row)

    def _add_field(self, layout, key, label_text, default_value):
        container = QFrame()
        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(5)
        v_layout.addWidget(QLabel(label_text, objectName="FormLabel"))
        
        if isinstance(default_value, list):
            field = QComboBox(objectName="FormInput")
            field.addItems(default_value)
        else:
            field = QLineEdit(default_value, objectName="FormInput")
            
        v_layout.addWidget(field)
        layout.addWidget(container, 1)
        self.inputs[key] = field

    def get_data(self):
        return {k: v.currentText() if isinstance(v, QComboBox) else v.text() for k, v in self.inputs.items()}