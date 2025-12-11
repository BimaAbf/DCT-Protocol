from __future__ import annotations
from datetime import datetime
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QHeaderView
from style.utils import apply_shadow

class DashboardPage(QWidget):
    def __init__(self, server_controller, clients_controller, logs_controller=None, parent=None):
        super().__init__(parent)
        self.server_controller = server_controller
        self.clients_controller = clients_controller
        self.logs_controller = logs_controller
        self.start_time = None
        
        self.x_data = list(range(20))
        self.y_data = [0] * 20
        self.ptr = 19
        self.last_packets = 0
        
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_graph)
        
        self.uptime_timer = QTimer(self)
        self.uptime_timer.setInterval(1000)
        self.uptime_timer.timeout.connect(self._update_uptime)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_area = QScrollArea()
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        layout.addWidget(scroll_area)
        
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setSpacing(20)
        scroll_area.setWidget(content)
        
        self.content_layout.addWidget(QLabel("Dashboard", objectName="PageHeader"))
        
        row_layout = QHBoxLayout()
        self.server_card = self._build_server_card()
        row_layout.addWidget(self.server_card, 1)
        
        self.graph_card = self._build_graph_card()
        row_layout.addWidget(self.graph_card, 2)
        
        self.content_layout.addLayout(row_layout)
        
        self.clients_card = self._build_clients_table()
        self.content_layout.addWidget(self.clients_card)
        
        self.server_controller.statusChanged.connect(self._on_server_status)
        self.clients_controller.clientsUpdated.connect(self._refresh_clients)
        
        if self.logs_controller:
            self.logs_controller.logsUpdated.connect(lambda _: self._refresh_clients(self.clients_controller.get_clients()))
            
        self._refresh_clients(self.clients_controller.get_clients())

    def _build_server_card(self):
        card = QFrame(objectName="ServerCard")
        card.setProperty("class", "page-card")
        apply_shadow(card)
        
        layout = QVBoxLayout(card)
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Server Control", objectName="SectionHeader"))
        header_layout.addStretch()
        
        self.btn_start = QPushButton("Start", objectName="StartButton")
        self.btn_stop = QPushButton("Stop", objectName="StopButton")
        
        self.btn_start.clicked.connect(self.server_controller.start)
        self.btn_stop.clicked.connect(self.server_controller.stop)
        
        header_layout.addWidget(self.btn_start)
        header_layout.addWidget(self.btn_stop)
        layout.addLayout(header_layout)
        
        grid = QGridLayout()
        self.lbl_ip = self._add_stat(grid, 0, 0, "Server IP")
        self.lbl_start_time = self._add_stat(grid, 0, 1, "Start Time")
        self.lbl_port = self._add_stat(grid, 1, 0, "Port")
        self.lbl_uptime = self._add_stat(grid, 1, 1, "Uptime")
        self.lbl_connections = self._add_stat(grid, 2, 0, "Active Connections")
        self.lbl_status = self._add_stat(grid, 2, 1, "Status")
        self.lbl_status.setText("Stopped")
        
        layout.addLayout(grid)
        
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)
        
        layout.addWidget(QLabel("Network Health", objectName="SectionHeader"))
        
        health_grid = QGridLayout()
        self.lbl_total_packets = self._add_stat(health_grid, 0, 0, "Total Packets")
        self.lbl_loss = self._add_stat(health_grid, 0, 1, "Global Loss")
        self.lbl_latency = self._add_stat(health_grid, 1, 0, "Avg Latency")
        self.lbl_throughput = self._add_stat(health_grid, 1, 1, "Throughput")
        
        layout.addLayout(health_grid)
        
        self.lbl_ip.setText(self.server_controller.ip)
        self.lbl_port.setText(str(self.server_controller.port))
        
        return card

    def _add_stat(self, grid, row, col, title):
        grid.addWidget(QLabel(f"{title} :", objectName="StatLabel"), row, col * 2)
        value_label = QLabel("-", objectName="StatValue")
        grid.addWidget(value_label, row, col * 2 + 1)
        return value_label

    def _build_graph_card(self):
        card = QFrame(objectName="GraphCard")
        card.setProperty("class", "page-card")
        apply_shadow(card)
        
        layout = QVBoxLayout(card)
        layout.addWidget(QLabel("Packets per Second", objectName="SectionHeader"))
        
        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=False, y=True, alpha=0.3)
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.hideButtons()
        self.plot_widget.getPlotItem().getViewBox().setLimits(yMin=0)
        
        fill_color = QColor("#3A7FF9")
        fill_color.setAlpha(40)
        
        self.curve = self.plot_widget.plot(
            self.x_data, 
            self.y_data, 
            pen=pg.mkPen('#3A7FF9', width=3),
            fillLevel=0,
            brush=pg.mkBrush(fill_color)
        )
        self.plot_widget.setMinimumHeight(180)
        
        layout.addWidget(self.plot_widget)
        return card

    def _build_clients_table(self):
        card = QFrame(objectName="ClientsCard")
        card.setProperty("class", "page-card")
        apply_shadow(card)
        
        layout = QVBoxLayout(card)
        layout.addWidget(QLabel("Clients Overview", objectName="SectionHeader"))
        
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Client", "Last Seen", "Latency", "Loss", "Packets", "Status"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        table.cellDoubleClicked.connect(lambda r, c: self.clients_controller.select_client(table.item(r, 0).text()) if table.item(r, 0) else None)
        
        table.setFrameShape(QFrame.NoFrame)
        table.setMinimumHeight(300)
        
        layout.addWidget(table)
        return card


    def _on_server_status(self, running, message):
        self.lbl_status.setText("Running" if running else "Stopped")
        if running:
            if not self.start_time:
                self.start_time = datetime.now()
                self.lbl_start_time.setText(self.start_time.strftime("%H:%M:%S"))
            if not self.uptime_timer.isActive():
                self.uptime_timer.start()
            
            self.x_data = list(range(20))
            self.y_data = [0] * 20
            self.ptr = 19
            self.last_packets = 0
            self.curve.setData(self.x_data, self.y_data)
            
            if not self.timer.isActive():
                self.timer.start(1000)
        else:
            self.uptime_timer.stop()
            self.timer.stop()
            self.start_time = None
            self.lbl_start_time.setText("-")
            self.lbl_uptime.setText("-")
            
        self._update_uptime()

    def _update_uptime(self):
        if not self.start_time:
            return
        seconds = int((datetime.now() - self.start_time).total_seconds())
        self.lbl_uptime.setText(f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}")

    def _update_graph(self):
        packets, gaps, latency, count, size, size_count = 0, 0, 0.0, 0, 0, 0
        clients = self.clients_controller.get_clients()
        
        for client in clients:
            packets += client.get("packets_sent", 0)
            gaps += client.get("gaps", 0)
            latency += client.get("avg_latency", 0)
            count += 1 if client.get("avg_latency") else 0
            size += client.get("avg_packet_size", 0)
            size_count += 1 if client.get("avg_packet_size") else 0
            
        pps = max(0, packets - self.last_packets)
        self.last_packets = packets
        
        self.x_data.pop(0)
        self.x_data.append(self.ptr + 1)
        self.ptr += 1
        
        self.y_data.pop(0)
        self.y_data.append(pps)
        
        self.curve.setData(self.x_data, self.y_data)
        
        self.lbl_total_packets.setText(f"{packets:,}")
        self.lbl_loss.setText(f"{(gaps / (packets + gaps) * 100):.2f}%" if packets + gaps > 0 else "0.00%")
        self.lbl_latency.setText(f"{(latency / count):.1f} ms" if count > 0 else "0.0 ms")
        
        bps = pps * (size / size_count if size_count > 0 else 0)
        self.lbl_throughput.setText(f"{bps / 1024:.1f} KB/s" if bps > 1024 else f"{int(bps)} B/s")

    def _refresh_clients(self, clients):
        table = self.clients_card.findChild(QTableWidget)
        if table.rowCount() != len(clients):
            table.setRowCount(len(clients))
            
        for row, client in enumerate(clients):
            device_id = client.get("device_id") or "Unknown"
            last_seen = str(client.get("last_seen") or "-")
            packets = int(client.get("packets_sent", 0))
            duplicates = int(client.get("duplicates", 0))
            gaps = int(client.get("gaps", 0))
            
            latency = f"{client.get('avg_latency'):.1f} ms" if client.get("avg_latency") else "-"
            loss = f"{(gaps / (packets + gaps) * 100):.1f}%" if packets + gaps > 0 else "0.0%"
            
            for col, text in enumerate([device_id, last_seen, latency, loss, str(packets)]):
                item = table.item(row, col)
                if not item:
                    table.setItem(row, col, QTableWidgetItem(text))
                elif item.text() != text:
                    item.setText(text)
            
            widget = table.cellWidget(row, 5)
            if not widget:
                widget = QWidget()
                h_layout = QHBoxLayout(widget)
                h_layout.setContentsMargins(0, 0, 0, 0)
                h_layout.setSpacing(6)
                
                dot = QLabel(objectName="StatusDot")
                dot.setFixedSize(10, 10)
                text_label = QLabel(objectName="StatusText")
                
                h_layout.addWidget(dot)
                h_layout.addWidget(text_label)
                table.setCellWidget(row, 5, widget)
            
            dot = widget.findChild(QLabel, "StatusDot")
            text_label = widget.findChild(QLabel, "StatusText")
            
            if duplicates == 0 and gaps == 0:
                dot.setStyleSheet("background:#10B981;border-radius:5px")
                text_label.setText("Good")
                text_label.setStyleSheet("color:#10B981")
            elif duplicates > 0:
                dot.setStyleSheet("background:#F59E0B;border-radius:5px")
                text_label.setText(f"{duplicates} Dups")
                text_label.setStyleSheet("color:#F59E0B")
            else:
                dot.setStyleSheet("background:#EF4444;border-radius:5px")
                text_label.setText("Loss")
                text_label.setStyleSheet("color:#EF4444")
                
        self.lbl_connections.setText(str(len(clients)))
