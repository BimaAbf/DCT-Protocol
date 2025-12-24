from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QPushButton
from style.utils import apply_shadow

class ClientCard(QWidget):
    clicked = Signal(dict)
    stopRequested = Signal(str)  # MAC address

    def __init__(self, client: Dict[str, Any] | None = None, position: int | None = None):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.client_data = {}
        
        wrapper_layout = QVBoxLayout(self)
        wrapper_layout.setContentsMargins(5, 5, 5, 5)
        wrapper_layout.setSpacing(0)

        self.container = QFrame()
        self.container.setObjectName("ClientCard")
        self.container.setProperty("class", "client-card")
        self.container.setFrameShape(QFrame.NoFrame)

        self.container.setStyleSheet("#ClientCard { background-color: #FFFFFF; border-radius: 12px; border: none; }")
        apply_shadow(self.container, blur_radius=15, y_offset=4, opacity=80)
        wrapper_layout.addWidget(self.container)

        main_layout = QHBoxLayout(self.container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        status_wrapper = QVBoxLayout()
        status_wrapper.setContentsMargins(6, 12, 0, 12)
        self.status_bar = QFrame()
        self.status_bar.setObjectName("ClientStatusBar")
        self.status_bar.setFrameShape(QFrame.NoFrame)
        self.status_bar.setFixedWidth(6)
        self.status_bar.setStyleSheet("background-color: #10B981; border-radius: 40px;")
        status_wrapper.addWidget(self.status_bar)
        main_layout.addLayout(status_wrapper)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(12)
        
        header_layout = QHBoxLayout()
        self.device_label = QLabel("Client")
        self.device_label.setObjectName("ClientName")
        header_layout.addWidget(self.device_label)
        
        # Online/Offline/Status Indicator
        self.online_indicator = QWidget()
        layout_indicator = QHBoxLayout(self.online_indicator)
        layout_indicator.setContentsMargins(10, 0, 0, 0)
        layout_indicator.setSpacing(6)
        
        self.online_dot = QLabel()
        self.online_dot.setFixedSize(8, 8)
        self.online_dot.setStyleSheet("background-color: #94A3B8; border-radius: 4px;")
        
        self.online_text = QLabel("Offline")
        self.online_text.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        
        layout_indicator.addWidget(self.online_dot)
        layout_indicator.addWidget(self.online_text)
        header_layout.addWidget(self.online_indicator)

        header_layout.addStretch()
        
        # Stop button for active processes
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedSize(60, 28)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF4444;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #DC2626;
            }
        """)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        self.stop_btn.hide()
        header_layout.addWidget(self.stop_btn)
        
        self.packet_summary = QLabel("0 packets")
        self.packet_summary.setObjectName("ClientPackets")
        header_layout.addWidget(self.packet_summary)
        content_layout.addLayout(header_layout)

        grid = QGridLayout()
        grid.setHorizontalSpacing(30)
        grid.setVerticalSpacing(8)
        grid.setContentsMargins(0, 8, 0, 0)
        
        self.labels = {}
        stats = [
            ("server_ip", "Server IP:", 0, 0), ("port", "Port:", 0, 1),
            ("interval", "Interval:", 0, 2), ("runtime", "Runtime:", 0, 3),
            ("mac", "MAC Address:", 1, 0), ("last_seen", "Last Activity:", 1, 1),
            ("duplicates", "Duplicates:", 1, 2), ("device_id", "Device ID:", 1, 3)
        ]

        for key, text, r, c in stats:
            container = QHBoxLayout()
            container.setSpacing(8)
            lbl = QLabel(text)
            lbl.setObjectName("ClientStatLabel")
            container.addWidget(lbl)
            val = QLabel("-")
            val.setObjectName("ClientStatValue")
            container.addWidget(val)
            container.addStretch()
            grid.addLayout(container, r, c)
            self.labels[key] = val
        
        content_layout.addLayout(grid)
        main_layout.addWidget(content_widget, 1)

        if client:
            self.update_data(client, position)

    def _on_stop_clicked(self):
        mac = self.client_data.get("mac")
        if mac:
            self.stopRequested.emit(mac)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.client_data)
        super().mousePressEvent(event)

    def update_data(self, client: Dict[str, Any], position: int | None = None):
        self.client_data = client
        
        # Determine title
        device_id = client.get("device_id")
        if position is not None:
            self.device_label.setText(f"Client {position + 1}")
        elif device_id:
            self.device_label.setText(f"Device {device_id}")
        else:
            self.device_label.setText(client.get("name", "Unknown Client"))
        
        # Handle status based on whether this is a managed process or log-based client
        is_process = client.get("is_process", False)
        status = client.get("status", "")
        is_online = client.get("is_online", False)
        
        # Show/hide stop button for active processes
        if is_process and status in ("pending", "connecting", "running"):
            self.stop_btn.show()
        else:
            self.stop_btn.hide()
        
        # Set status indicator
        if is_process:
            status_config = {
                "pending": ("#94A3B8", "Pending"),
                "connecting": ("#F59E0B", "Connecting"),
                "running": ("#10B981", "Running"),
                "completed": ("#3B82F6", "Completed"),
                "failed": ("#EF4444", "Failed"),
            }
            color, text = status_config.get(status, ("#94A3B8", "Unknown"))
            self.online_dot.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
            self.online_text.setText(text)
            self.online_text.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
        else:
            if is_online:
                self.online_dot.setStyleSheet("background-color: #10B981; border-radius: 4px;")
                self.online_text.setText("Online")
                self.online_text.setStyleSheet("color: #10B981; font-size: 12px; font-weight: 600;")
            else:
                self.online_dot.setStyleSheet("background-color: #94A3B8; border-radius: 4px;")
                self.online_text.setText("Offline")
                self.online_text.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")

        pkts = client.get("packets_sent") if client.get("packets_sent") is not None else client.get("packets", 0)
        self.packet_summary.setText(f"{pkts} packet{'s' if pkts != 1 else ''}")

        self.labels["server_ip"].setText(self._val(client, "ip", "ip_address", "server_ip", default="127.0.0.1"))
        self.labels["port"].setText(str(client.get("port") or client.get("server_port") or 5000))
        
        # Format runtime
        runtime_secs = client.get("runtime_seconds", 0)
        if runtime_secs and runtime_secs > 0:
            hours = int(runtime_secs // 3600)
            mins = int((runtime_secs % 3600) // 60)
            secs = int(runtime_secs % 60)
            if hours > 0:
                self.labels["runtime"].setText(f"{hours:02d}:{mins:02d}:{secs:02d}")
            else:
                self.labels["runtime"].setText(f"{mins:02d}:{secs:02d}")
        else:
            self.labels["runtime"].setText("-")

        self.labels["mac"].setText(self._val(client, "mac", "mac_address", default="00:00:00:00:00:00"))
        self.labels["last_seen"].setText(client.get("last_seen") or client.get("last_activity") or "-")
        
        interval = client.get("interval") or client.get("send_interval")
        self.labels["interval"].setText(f"{interval}s" if interval else "-")

        dup = client.get("duplicates", 0)
        self.labels["duplicates"].setText(str(dup))
        
        # Device ID
        self.labels["device_id"].setText(str(device_id) if device_id else "-")

        # Status bar color based on health
        gaps = client.get("gaps", 0)
        if is_process and status in ("pending", "connecting"):
            color = "#F59E0B"  # Yellow for pending
        elif is_process and status == "failed":
            color = "#EF4444"  # Red for failed
        elif dup == 0 and gaps == 0:
            color = "#10B981"  # Green
        elif dup > 0:
            color = "#F59E0B"  # Yellow for duplicates
        else:
            color = "#EF4444"  # Red for gaps/loss
        self.status_bar.setStyleSheet(f"background-color: {color}; border-radius: 40px;")

    def _val(self, data: Dict, *keys: str, default: str = "-") :
        for k in keys:
            if v := data.get(k): return str(v)
        return default
