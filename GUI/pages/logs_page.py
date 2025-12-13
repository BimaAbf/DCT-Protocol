from __future__ import annotations
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QWidget, QLabel, QTableWidget, QTableWidgetItem, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QScrollArea
from style.utils import apply_shadow

class LogsPage(QWidget):
    def __init__(self, logs_controller, parent=None):
        super().__init__(parent)
        self.logs_controller = logs_controller
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        layout.addWidget(scroll)
        
        content = QWidget()
        clayout = QVBoxLayout(content)
        clayout.setContentsMargins(10, 10, 10, 10)
        clayout.setSpacing(20)
        scroll.setWidget(content)
        clayout.addWidget(QLabel("Server Logs", objectName="ConsoleTitle"))
        
        files_card = QFrame()
        files_card.setProperty("class", "page-card")
        apply_shadow(files_card)
        fl = QVBoxLayout(files_card)
        fl.setContentsMargins(10, 10, 10, 10)
        fl.setSpacing(10)
        
        header = QHBoxLayout()
        header.addWidget(QLabel("Logs Files", objectName="SectionHeader"))
        header.addStretch(1)
        self.logs_count_label = QLabel("Logs found: 0", objectName="HelperLabel")
        header.addWidget(self.logs_count_label)
        fl.addLayout(header)
        
        self.logs_list = QListWidget()
        self.logs_list.setFixedHeight(150)
        fl.addWidget(self.logs_list)
        clayout.addWidget(files_card)
        
        viewer_card = QFrame()
        viewer_card.setProperty("class", "page-card")
        apply_shadow(viewer_card)
        vl = QVBoxLayout(viewer_card)
        vl.setContentsMargins(10, 10, 10, 10)
        vl.setSpacing(10)
        self.current_log_label = QLabel("Viewing: -", objectName="SectionHeader")
        vl.addWidget(self.current_log_label)
        
        self.logs_table = QTableWidget()
        self.logs_table.setFrameShape(QFrame.NoFrame)
        self.logs_table.setAlternatingRowColors(True)
        self.logs_table.verticalHeader().setVisible(False)
        vl.addWidget(self.logs_table)
        clayout.addWidget(viewer_card, 1)
        
        self.logs_list.itemClicked.connect(self._on_log_clicked)
        self.logs_controller.logsUpdated.connect(self._update_logs_list)
        self.logs_controller.errorOccurred.connect(self._on_error)
        self.logs_controller.refresh_logs()
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(30000)
        self.refresh_timer.timeout.connect(self.logs_controller.refresh_logs)
        self.refresh_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.logs_controller.refresh_logs()

    def _update_logs_list(self, files):
        self.logs_list.clear()
        if not files:
            self.logs_list.addItem(QListWidgetItem("No log files found"))
            self.logs_count_label.setText("Logs found: 0")
            return
        self.logs_list.addItems(files)
        self.logs_count_label.setText(f"Logs found: {len(files)}")

    def _on_log_clicked(self, item):
        fn = item.text()
        self.current_log_label.setText(f"Viewing: {fn}")
        self._render_log_table(self.logs_controller.read_log(fn))

    def _render_log_table(self, rows):
        self.logs_table.clear()
        self.logs_table.setRowCount(0)
        self.logs_table.setColumnCount(0)
        if not rows: return
        header = rows[0] if rows and len(rows[0]) > 1 else None
        data = rows[1:] if header else rows
        if header:
            self.logs_table.setColumnCount(len(header))
            self.logs_table.setHorizontalHeaderLabels(header)
        else:
            self.logs_table.setColumnCount(len(rows[0]))
        cpu_idx = next((i for i, c in enumerate(header or []) if "cpu_time" in c.lower()), -1)
        for rd in data:
            r = self.logs_table.rowCount()
            self.logs_table.insertRow(r)
            for c, v in enumerate(rd):
                dv = f"{float(v):.4f}" if c == cpu_idx else v
                try: dv = f"{float(v):.4f}" if c == cpu_idx else v
                except: dv = v
                self.logs_table.setItem(r, c, QTableWidgetItem(dv))
        self.logs_table.resizeColumnsToContents()

    def _on_error(self, msg):
        self.logs_list.clear()
        self.logs_list.addItem(QListWidgetItem(msg))
        self.logs_count_label.setText(msg)
