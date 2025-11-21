from __future__ import annotations
import pandas as pd
import numpy as np
import pyqtgraph as pg
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView, QGridLayout)
from GUI.style.utils import apply_shadow

MESSAGE_TYPES = {1: "Startup", 2: "Startup Ack", 3: "Time Sync", 4: "Keyframe", 5: "Delta", 6: "Heartbeat", 7: "Batch", 11: "Shutdown"}

class AnalysisPage(QWidget):
    def __init__(self, logs_controller, parent=None):
        super().__init__(parent)
        self.logs_controller = logs_controller
        self.data = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Server Analysis", objectName="PageHeader"))
        header_layout.addStretch()
        
        self.log_selector = QComboBox()
        self.log_selector.setMinimumWidth(300)
        header_layout.addWidget(self.log_selector)
        
        analyze_button = QPushButton("Analyze Log")
        analyze_button.clicked.connect(self._analyze_log)
        header_layout.addWidget(analyze_button)
        layout.addLayout(header_layout)
        
        scroll_area = QScrollArea()
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        layout.addWidget(scroll_area)
        
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        scroll_area.setWidget(content_widget)
        
        self.stats_grid = QGridLayout()
        self.content_layout.addLayout(self.stats_grid)
        
        self.graphs_grid = QGridLayout()
        self.content_layout.addLayout(self.graphs_grid)
        
        self.tables_layout = QVBoxLayout()
        self.content_layout.addLayout(self.tables_layout)
        self.content_layout.addStretch()
        
        self.logs_controller.logsUpdated.connect(self._update_log_files)
        self._update_log_files(self.logs_controller.refresh_logs())

    def _update_log_files(self, files):
        current_text = self.log_selector.currentText()
        self.log_selector.clear()
        self.log_selector.addItems(files)
        if current_text in files:
            self.log_selector.setCurrentText(current_text)

    def _analyze_log(self):
        filename = self.log_selector.currentText()
        if not filename:
            return
            
        try:
            self.data = pd.read_csv(os.path.join(self.logs_controller.logs_dir, filename))
            for col in ['timestamp', 'arrival_time']:
                self.data[col] = pd.to_datetime(self.data[col], errors='coerce')
                
            latency = (self.data['arrival_time'] - self.data['timestamp']).dt.total_seconds() * 1000
            self.data['latency_ms'] = latency.where((latency >= 0) & (latency < 5000))
            
            for col in ['cpu_time_ms', 'packet_size']:
                self.data[col] = pd.to_numeric(self.data[col], errors='coerce')
                
            self._render_analysis()
        except Exception:
            pass

    def _render_analysis(self):
        for layout in [self.stats_grid, self.graphs_grid, self.tables_layout]:
            while layout.count():
                if widget := layout.takeAt(0).widget():
                    widget.deleteLater()
                    
        if self.data is None or self.data.empty:
            return
            
        total_packets = len(self.data)
        loss = self.data['gap_flag'].sum()
        duplicates = self.data['duplicate_flag'].sum()
        
        self._create_stat_card(self.stats_grid, 0, 0, "Total Packets", f"{total_packets:,}", "#3B82F6")
        self._create_stat_card(self.stats_grid, 0, 1, "Packet Loss", f"{loss} ({loss/total_packets:.1%})", "#EF4444")
        self._create_stat_card(self.stats_grid, 0, 2, "Duplicates", f"{duplicates} ({duplicates/total_packets:.1%})", "#F59E0B")
        self._create_stat_card(self.stats_grid, 0, 3, "Avg Latency", f"{self.data['latency_ms'].mean():.2f} ms", "#10B981")
        
        pg.setConfigOptions(antialias=True)
        
        latency_plot = pg.PlotWidget(title="Latency Distribution (ms)")
        latency_plot.setBackground('w')
        latency_plot.setMouseEnabled(x=False, y=False)
        latency_plot.hideButtons()
        latency_plot.showGrid(x=True, y=True, alpha=0.3)
        
        y, x = np.histogram(self.data['latency_ms'].dropna(), bins=50)
        latency_plot.plot(x, y, stepMode=True, fillLevel=0, brush=(59, 130, 246, 100), pen=pg.mkPen('#3B82F6', width=2))
        self._create_graph_card(latency_plot, 0, 0)
        
        if 'arrival_time' in self.data:
            throughput_plot = pg.PlotWidget(title="Throughput (pps)")
            throughput_plot.setBackground('w')
            throughput_plot.setMouseEnabled(x=False, y=False)
            throughput_plot.hideButtons()
            throughput_plot.showGrid(x=True, y=True, alpha=0.3)
            
            throughput = self.data.set_index('arrival_time').resample('1s').size()
            throughput_plot.plot(throughput.index.astype(int)//10**9, throughput.values, pen=pg.mkPen('#10B981', width=2), fillLevel=0, brush=(16, 185, 129, 50))
            self._create_graph_card(throughput_plot, 0, 1)
            
        stats_table = self.data.groupby('device_id').agg({
            'seq': 'count',
            'gap_flag': 'sum',
            'duplicate_flag': 'sum',
            'latency_ms': 'mean',
            'packet_size': 'sum'
        }).reset_index()
        stats_table.columns = ['Device', 'Packets', 'Loss', 'Dups', 'Avg Latency', 'Total Bytes']
        self._create_table_card("Per-Device Statistics", stats_table)

    def _create_stat_card(self, layout, row, col, title, value, color):
        card = QFrame()
        card.setProperty("class", "page-card")
        apply_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(QLabel(title, styleSheet="color:#64748B;font-weight:500"))
        card_layout.addWidget(QLabel(value, styleSheet=f"color:{color};font-size:24px;font-weight:bold"))
        layout.addWidget(card, row, col)

    def _create_graph_card(self, widget, row, col):
        card = QFrame()
        card.setProperty("class", "page-card")
        apply_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(widget)
        self.graphs_grid.addWidget(card, row, col)

    def _create_table_card(self, title, data):
        card = QFrame()
        card.setProperty("class", "page-card")
        apply_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(QLabel(title, objectName="SectionHeader"))
        
        table = QTableWidget(len(data), len(data.columns))
        table.setHorizontalHeaderLabels(data.columns.astype(str))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        for i in range(len(data)):
            for j in range(len(data.columns)):
                value = data.iloc[i, j]
                table.setItem(i, j, QTableWidgetItem(f"{value:.2f}" if isinstance(value, float) else str(value)))
                
        card_layout.addWidget(table)
        self.tables_layout.addWidget(card)
