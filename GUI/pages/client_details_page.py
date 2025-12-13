from __future__ import annotations
import datetime
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QGridLayout, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView
from style.utils import apply_shadow

class ClientDetailsPage(QWidget):
    backRequested = Signal()

    def __init__(self, logs_controller=None, parent=None):
        super().__init__(parent)
        self.logs_controller = logs_controller
        self.client_data = {}
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        header_layout = QHBoxLayout()
        back_button = QPushButton("Back")
        back_button.setFixedWidth(100)
        back_button.clicked.connect(self.backRequested.emit)
        header_layout.addWidget(back_button)
        
        self.title_label = QLabel("Client Details", objectName="PageHeader")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        
        self.status_badge = QLabel("Online")
        self.status_badge.setStyleSheet("background-color: #10B981; color: white; padding: 5px 10px; border-radius: 12px; font-weight: bold;")
        header_layout.addWidget(self.status_badge)
        layout.addLayout(header_layout)
        
        scroll_area = QScrollArea()
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet("background: transparent;")
        
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setSpacing(20)
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.info_card = QFrame()
        self.info_card.setProperty("class", "page-card")
        self.info_card.setStyleSheet("background-color: #FFFFFF; border-radius: 16px;")
        apply_shadow(self.info_card)
        
        info_layout = QVBoxLayout(self.info_card)
        info_layout.setContentsMargins(20, 20, 20, 20)
        info_layout.setSpacing(15)
        info_layout.addWidget(QLabel("Device Information", objectName="SectionHeader"))
        
        self.info_grid = QGridLayout()
        self.info_grid.setHorizontalSpacing(40)
        self.info_grid.setVerticalSpacing(15)
        info_layout.addLayout(self.info_grid)
        self.content_layout.addWidget(self.info_card)
        
        self.stats_container = QWidget()
        self.stats_grid = QGridLayout(self.stats_container)
        self.content_layout.addWidget(self.stats_container)
        
        self.graphs_container = QWidget()
        self.graphs_grid = QGridLayout(self.graphs_container)
        self.content_layout.addWidget(self.graphs_container)
        
        self._init_graphs()
        
        self.logs_card = QFrame()
        self.logs_card.setProperty("class", "page-card")
        self.logs_card.setStyleSheet("background-color: #FFFFFF; border-radius: 16px;")
        apply_shadow(self.logs_card)
        
        logs_layout = QVBoxLayout(self.logs_card)
        logs_layout.setContentsMargins(10, 10, 10, 10)
        logs_layout.setSpacing(10)
        logs_layout.addWidget(QLabel("Packet Logs", objectName="SectionHeader"))
        
        self.logs_table = QTableWidget()
        self.logs_table.setColumnCount(4)
        self.logs_table.setHorizontalHeaderLabels(["Timestamp", "Value", "Seq", "Status"])
        self.logs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.logs_table.verticalHeader().setVisible(False)
        self.logs_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.logs_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.logs_table.setFrameShape(QFrame.NoFrame)
        self.logs_table.setStyleSheet("QTableWidget { background-color: transparent; border: none; selection-background-color: #F1F5F9; selection-color: #0F172A; } QTableWidget::item { padding-left: 10px; border-bottom: 1px solid #F1F5F9; color: #334155; } QHeaderView::section { background-color: transparent; border: none; border-bottom: 2px solid #E2E8F0; color: #64748B; font-weight: bold; padding: 8px; text-align: left; }")
        logs_layout.addWidget(self.logs_table)
        self.logs_table.setMinimumHeight(300)
        self.content_layout.addWidget(self.logs_card)
        self.content_layout.addStretch()
        
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(1000)
        self.update_timer.timeout.connect(self._update_graphs)

    def _init_graphs(self):
        self.latency_plot = pg.PlotWidget(title="Latency (ms)")
        self.latency_plot.setBackground('w')
        self.latency_curve = self.latency_plot.plot(pen=pg.mkPen('#3B82F6', width=2))
        self._style_plot(self.latency_plot)
        
        self.throughput_plot = pg.PlotWidget(title="Throughput (pps)")
        self.throughput_plot.setBackground('w')
        self.throughput_curve = self.throughput_plot.plot(pen=pg.mkPen('#10B981', width=2))
        self._style_plot(self.throughput_plot)
        
        self.value_plot = pg.PlotWidget(title="Sensor Value")
        self.value_plot.setBackground('w')
        self.value_curve = self.value_plot.plot(pen=pg.mkPen('#8B5CF6', width=2))
        self._style_plot(self.value_plot)
        
        self._add_graph_card(self.latency_plot, 0, 0)
        self._add_graph_card(self.throughput_plot, 0, 1)
        self._add_graph_card(self.value_plot, 1, 0, 2)

    def set_client(self, client_data):
        self.client_data = client_data
        self.title_label.setText(f"Client: {client_data.get('device_id', 'Unknown')}")
        self._clear_layout(self.info_grid)
        
        # Format batching display
        batch_size = client_data.get("batch_size", "1")
        if batch_size and str(batch_size) != "1":
            batching_text = f"Enabled (size: {batch_size})"
        else:
            batching_text = "Disabled"
        
        self._add_info_item("MAC Address", client_data.get("mac") or "Unknown", 0, 0)
        self._add_info_item("Target Server", f"{client_data.get('server_ip') or '127.0.0.1'}:{client_data.get('port') or '5000'}", 0, 1)
        self._add_info_item("Interval", f"{client_data.get('interval') or '-'}s" if client_data.get('interval') else "-", 0, 2)
        self._add_info_item("Batching", batching_text, 1, 0)
        self._add_info_item("Duration", f"{client_data.get('duration') or '-'}s" if client_data.get('duration') else "-", 1, 1)
        self._add_info_item("Delta Threshold", str(client_data.get("delta_thresh") or "-"), 1, 2)
        
        self._clear_layout(self.stats_grid)
        self._add_stat_card(0, 0, "Packets Sent", str(client_data.get('packets_sent', 0)))
        self._add_stat_card(0, 1, "Duplicates", str(client_data.get('duplicates', 0)))
        self._add_stat_card(0, 2, "Packet Loss", f"{self._calculate_loss(client_data):.1f}%")
        self._add_stat_card(0, 3, "Avg Latency", f"{client_data.get('avg_latency', 0) or 0:.1f} ms")
        
        if not self.update_timer.isActive():
            self.update_timer.start()
            
        self._update_table()
        self._update_graphs()

    def _add_info_item(self, label, value, row, col):
        container = QVBoxLayout()
        container.setSpacing(4)
        container.addWidget(QLabel(label, objectName="StatLabel"))
        container.addWidget(QLabel(str(value), objectName="StatValue"))
        self.info_grid.addLayout(container, row, col)

    def _update_table(self):
        if not self.logs_controller or not self.client_data:
            return
            
        logs = self.logs_controller.get_device_logs(self.client_data.get("device_id"))
        logs.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
        self.logs_table.setRowCount(len(logs))
        
        for row, log in enumerate(logs):
            status = "OK"
            if log.get("duplicate"):
                status = "Duplicate"
            elif log.get("gap"):
                status = "Gap"
                
            self.logs_table.setItem(row, 0, QTableWidgetItem(log.get("timestamp", "-")))
            self.logs_table.setItem(row, 1, QTableWidgetItem(str(log.get("value", "-"))))
            self.logs_table.setItem(row, 2, QTableWidgetItem(str(log.get("seq", "-"))))
            
            status_item = QTableWidgetItem(status)
            status_item.setForeground(Qt.darkYellow if status == "Duplicate" else Qt.red if status == "Gap" else Qt.darkGreen)
            self.logs_table.setItem(row, 3, status_item)

    def _update_graphs(self):
        if not self.logs_controller or not self.client_data:
            return
            
        logs = self.logs_controller.get_device_logs(self.client_data.get("device_id"))
        logs.sort(key=lambda x: x.get("timestamp_dt") or datetime.datetime.min)
        
        is_online = False
        if logs and logs[-1].get("arrival_dt") and (datetime.datetime.now() - logs[-1]["arrival_dt"]).total_seconds() < 30:
            is_online = True
            
        self.status_badge.setText("Online" if is_online else "Offline")
        self.status_badge.setStyleSheet(f"background-color: {'#10B981' if is_online else '#94A3B8'}; color: white; padding: 5px 10px; border-radius: 12px; font-weight: bold;")
        
        filtered_values = []
        for log in logs:
            try:
                value, seq = float(log.get("value", 0)), int(log.get("seq", 0))
                if value != -1 and seq > 2:
                    filtered_values.append(value)
            except:
                pass
                
        values_to_plot = filtered_values[-60:] if len(filtered_values) > 60 else filtered_values
        self.value_curve.setData(values_to_plot)
        
        if values_to_plot:
            min_val, max_val = min(values_to_plot), max(values_to_plot)
            y_min, y_max = (int(min_val) // 5) * 5, (int(max_val) // 5 + 1) * 5
            if y_min == y_max:
                y_min -= 5
                y_max += 5
            self.value_plot.setYRange(y_min, y_max, padding=0)
            
        throughput_values = []
        if logs:
            valid_logs = [l for l in logs if l.get("arrival_dt")]
            if valid_logs:
                valid_logs.sort(key=lambda x: x["arrival_dt"])
                start_time, end_time = valid_logs[0]["arrival_dt"], valid_logs[-1]["arrival_dt"]
                num_buckets = int((end_time - start_time).total_seconds()) + 1
                buckets = [0] * num_buckets
                
                for log in valid_logs:
                    seconds = int((log["arrival_dt"] - start_time).total_seconds())
                    if 0 <= seconds < num_buckets:
                        buckets[seconds] += 1
                throughput_values = buckets
                
        self.throughput_curve.setData(throughput_values)
        
        latency_values = []
        for log in logs:
            try:
                if int(log.get("seq", 0)) > 2:
                    latency_values.append(log.get("latency", 0.0))
            except:
                pass
        self.latency_curve.setData(latency_values)
        
        if self.isVisible():
            self._update_table()

    def _calculate_loss(self, client_data):
        sent, gaps = client_data.get('packets_sent', 0), client_data.get('gaps', 0)
        return (gaps / (sent + gaps)) * 100 if sent + gaps > 0 else 0.0

    def _add_stat_card(self, row, col, title, value):
        card = QFrame()
        card.setProperty("class", "metric-card")
        card.setStyleSheet("background-color: #FFFFFF; border-radius: 16px;")
        apply_shadow(card)
        layout = QVBoxLayout(card)
        layout.addWidget(QLabel(title, objectName="StatLabel"))
        layout.addWidget(QLabel(value, objectName="StatValue"))
        self.stats_grid.addWidget(card, row, col)

    def _add_graph_card(self, widget, row, col, colspan=1):
        card = QFrame()
        card.setProperty("class", "page-card")
        card.setStyleSheet("background-color: #FFFFFF; border-radius: 16px;")
        apply_shadow(card)
        layout = QVBoxLayout(card)
        widget.setMinimumHeight(300)
        layout.addWidget(widget)
        self.graphs_grid.addWidget(card, row, col, 1, colspan)

    def _style_plot(self, plot):
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.getAxis('left').setPen('#E2E8F0')
        plot.getAxis('bottom').setPen('#E2E8F0')
        plot.getAxis('left').setTextPen('#64748B')
        plot.getAxis('bottom').setTextPen('#64748B')
        plot.getPlotItem().getViewBox().setLimits(yMin=0)
        plot.setMouseEnabled(x=False, y=False)
        plot.hideButtons()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()