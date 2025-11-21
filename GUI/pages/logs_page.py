from __future__ import annotations
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame, QWidget, QLabel, QTableWidget, QTableWidgetItem, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QScrollArea)
from GUI.style.utils import apply_shadow

class LogsPage(QWidget):
    def __init__(self, logs_controller, parent=None):
        super().__init__(parent)
        self.logs_controller = logs_controller
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        scroll_area = QScrollArea()
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll_area)
        
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setSpacing(20)
        scroll_area.setWidget(content_widget)
        
        self.content_layout.addWidget(QLabel("Server Logs", objectName="ConsoleTitle"))
        
        files_card = QFrame()
        files_card.setProperty("class", "page-card")
        apply_shadow(files_card)
        files_layout = QVBoxLayout(files_card)
        files_layout.setContentsMargins(10, 10, 10, 10)
        files_layout.setSpacing(10)
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Logs Files", objectName="SectionHeader"))
        header_layout.addStretch(1)
        self.logs_count_label = QLabel("Logs found: 0", objectName="HelperLabel")
        header_layout.addWidget(self.logs_count_label)
        files_layout.addLayout(header_layout)
        
        self.logs_list = QListWidget()
        self.logs_list.setFixedHeight(150)
        files_layout.addWidget(self.logs_list)
        self.content_layout.addWidget(files_card)
        
        viewer_card = QFrame()
        viewer_card.setProperty("class", "page-card")
        apply_shadow(viewer_card)
        viewer_layout = QVBoxLayout(viewer_card)
        viewer_layout.setContentsMargins(10, 10, 10, 10)
        viewer_layout.setSpacing(10)
        
        self.current_log_label = QLabel("Viewing: -", objectName="SectionHeader")
        viewer_layout.addWidget(self.current_log_label)
        
        self.logs_table = QTableWidget()
        self.logs_table.setFrameShape(QFrame.NoFrame)
        self.logs_table.setAlternatingRowColors(True)
        self.logs_table.verticalHeader().setVisible(False)
        viewer_layout.addWidget(self.logs_table)
        self.content_layout.addWidget(viewer_card, 1)
        
        self.logs_list.itemClicked.connect(self._on_log_clicked)
        self.logs_controller.logsUpdated.connect(self._update_logs_list)
        self.logs_controller.errorOccurred.connect(self._on_error)
        
        self.logs_controller.refresh_logs()
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(30000)
        self.refresh_timer.timeout.connect(self.logs_controller.refresh_logs)
        self.refresh_timer.start()

    def _update_logs_list(self, files):
        self.logs_list.clear()
        if not files:
            self.logs_list.addItem(QListWidgetItem("No log files found"))
            self.logs_count_label.setText("Logs found: 0")
            return
            
        self.logs_list.addItems(files)
        self.logs_count_label.setText(f"Logs found: {len(files)}")
        for i in range(self.logs_list.count()):
            self.logs_list.item(i).setToolTip(self.logs_list.item(i).text())

    def _on_log_clicked(self, item):
        filename = item.text()
        self.current_log_label.setText(f"Viewing: {filename}")
        self._render_log_table(self.logs_controller.read_log(filename))

    def _render_log_table(self, rows):
        self.logs_table.clear()
        self.logs_table.setRowCount(0)
        self.logs_table.setColumnCount(0)
        
        if not rows:
            return
            
        header = rows[0] if rows and len(rows[0]) > 1 else None
        data = rows[1:] if header else rows
        
        if header:
            self.logs_table.setColumnCount(len(header))
            self.logs_table.setHorizontalHeaderLabels(header)
        else:
            self.logs_table.setColumnCount(len(rows[0]))
            
        cpu_time_index = -1
        if header:
            for i, col_name in enumerate(header):
                if "cpu_time" in col_name.lower():
                    cpu_time_index = i
                    
        for row_data in data:
            row_idx = self.logs_table.rowCount()
            self.logs_table.insertRow(row_idx)
            for col_idx, value in enumerate(row_data):
                display_value = value
                if col_idx == cpu_time_index:
                    try:
                        display_value = f"{float(value):.4f}"
                    except:
                        pass
                self.logs_table.setItem(row_idx, col_idx, QTableWidgetItem(display_value))
                
        self.logs_table.resizeColumnsToContents()

    def _on_error(self, message):
        self.logs_list.clear()
        self.logs_list.addItem(QListWidgetItem(message))
        self.logs_count_label.setText(message)
