from __future__ import annotations
import os
import pandas as pd
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView, QGridLayout
from style.utils import apply_shadow

class AnalysisPage(QWidget):
    def __init__(self, logs_controller, parent=None):
        super().__init__(parent)
        self.logs_controller = logs_controller
        self.data = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header = QHBoxLayout()
        header.addWidget(QLabel("Server Analysis", objectName="PageHeader"))
        header.addStretch()
        self.log_selector = QComboBox()
        self.log_selector.setMinimumWidth(300)
        header.addWidget(self.log_selector)
        btn = QPushButton("Analyze Log")
        btn.clicked.connect(self._analyze_log)
        header.addWidget(btn)
        layout.addLayout(header)
        
        scroll = QScrollArea()
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        layout.addWidget(scroll)
        
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        scroll.setWidget(content)
        
        self.stats_grid = QGridLayout()
        self.content_layout.addLayout(self.stats_grid)
        self.graphs_grid = QGridLayout()
        self.content_layout.addLayout(self.graphs_grid)
        self.tables_layout = QVBoxLayout()
        self.content_layout.addLayout(self.tables_layout)
        self.content_layout.addStretch()
        
        self.logs_controller.logsUpdated.connect(self._update_log_files)
        self._update_log_files(self.logs_controller.refresh_logs())

    def showEvent(self, event):
        super().showEvent(event)
        self.logs_controller.refresh_logs()

    def _update_log_files(self, files):
        cur = self.log_selector.currentText()
        self.log_selector.clear()
        self.log_selector.addItems(files)
        if cur in files: self.log_selector.setCurrentText(cur)

    def _analyze_log(self):
        self.logs_controller.refresh_logs()
        fn = self.log_selector.currentText()
        if not fn: return
        try:
            self.data = pd.read_csv(os.path.join(self.logs_controller.logs_dir, fn))
            for col in ['timestamp', 'arrival_time']:
                self.data[col] = pd.to_datetime(self.data[col], errors='coerce')
            lat = (self.data['arrival_time'] - self.data['timestamp']).dt.total_seconds() * 1000
            self.data['latency_ms'] = lat.where((lat >= 0) & (lat < 5000))
            for col in ['cpu_time_ms', 'packet_size']:
                self.data[col] = pd.to_numeric(self.data[col], errors='coerce')
            self._render_analysis()
        except: pass

    def _render_analysis(self):
        for l in [self.stats_grid, self.graphs_grid, self.tables_layout]:
            while l.count():
                if w := l.takeAt(0).widget(): w.deleteLater()
        if self.data is None or self.data.empty: return
        
        total, loss, dups = len(self.data), self.data['gap_flag'].sum(), self.data['duplicate_flag'].sum()
        self._stat_card(0, 0, "Total Packets", f"{total:,}", "#3B82F6")
        self._stat_card(0, 1, "Packet Loss", f"{loss} ({loss/total:.1%})", "#EF4444")
        self._stat_card(0, 2, "Duplicates", f"{dups} ({dups/total:.1%})", "#F59E0B")
        self._stat_card(0, 3, "Avg Latency", f"{self.data['latency_ms'].mean():.2f} ms", "#10B981")
        
        pg.setConfigOptions(antialias=True)
        lat_plot = pg.PlotWidget(title="Latency Distribution (ms)")
        lat_plot.setBackground('w')
        lat_plot.setMouseEnabled(x=False, y=False)
        lat_plot.hideButtons()
        lat_plot.showGrid(x=True, y=True, alpha=0.3)
        y, x = np.histogram(self.data['latency_ms'].dropna(), bins=50)
        lat_plot.plot(x, y, stepMode=True, fillLevel=0, brush=(59, 130, 246, 100), pen=pg.mkPen('#3B82F6', width=2))
        self._graph_card(lat_plot, 0, 0)
        
        if 'arrival_time' in self.data:
            tp = pg.PlotWidget(title="Throughput (pps)")
            tp.setBackground('w')
            tp.setMouseEnabled(x=False, y=False)
            tp.hideButtons()
            tp.showGrid(x=True, y=True, alpha=0.3)
            thr = self.data.set_index('arrival_time').resample('1s').size()
            tp.plot(thr.index.astype(int)//10**9, thr.values, pen=pg.mkPen('#10B981', width=2), fillLevel=0, brush=(16, 185, 129, 50))
            self._graph_card(tp, 0, 1)
        
        stats = self.data.groupby('device_id').agg({'seq': 'count', 'gap_flag': 'sum', 'duplicate_flag': 'sum', 'latency_ms': 'mean', 'packet_size': 'sum'}).reset_index()
        stats.columns = ['Device', 'Packets', 'Loss', 'Dups', 'Avg Latency', 'Total Bytes']
        self._table_card("Per-Device Statistics", stats)

    def _stat_card(self, row, col, title, value, color):
        card = QFrame()
        card.setProperty("class", "page-card")
        apply_shadow(card)
        l = QVBoxLayout(card)
        l.addWidget(QLabel(title, styleSheet="color:#64748B;font-weight:500"))
        l.addWidget(QLabel(value, styleSheet=f"color:{color};font-size:24px;font-weight:bold"))
        self.stats_grid.addWidget(card, row, col)

    def _graph_card(self, widget, row, col):
        card = QFrame()
        card.setProperty("class", "page-card")
        apply_shadow(card)
        QVBoxLayout(card).addWidget(widget)
        self.graphs_grid.addWidget(card, row, col)

    def _table_card(self, title, data):
        card = QFrame()
        card.setProperty("class", "page-card")
        apply_shadow(card)
        l = QVBoxLayout(card)
        l.addWidget(QLabel(title, objectName="SectionHeader"))
        t = QTableWidget(len(data), len(data.columns))
        t.setHorizontalHeaderLabels(data.columns.astype(str))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for i in range(len(data)):
            for j in range(len(data.columns)):
                v = data.iloc[i, j]
                t.setItem(i, j, QTableWidgetItem(f"{v:.2f}" if isinstance(v, float) else str(v)))
        l.addWidget(t)
        self.tables_layout.addWidget(card)
