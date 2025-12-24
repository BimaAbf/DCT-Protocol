from __future__ import annotations
import os
import pandas as pd
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView, QGridLayout, QMessageBox
from style.utils import apply_shadow

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
        
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh_logs)
        header_layout.addWidget(refresh_button)
        
        analyze_button = QPushButton("Analyze Log")
        analyze_button.clicked.connect(self._analyze_log)
        header_layout.addWidget(analyze_button)
        layout.addLayout(header_layout)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #64748B; font-size: 12px; padding: 5px;")
        layout.addWidget(self.status_label)
        
        scroll_area = QScrollArea()
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
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

    def showEvent(self, event):
        """Refresh logs when page becomes visible"""
        super().showEvent(event)
        self._refresh_logs()
    
    def _refresh_logs(self):
        """Manually refresh logs list"""
        files = self.logs_controller.refresh_logs()
        self._update_log_files(files)
        self.status_label.setText(f"Found {len(files)} log files")

    def _update_log_files(self, files):
        current_text = self.log_selector.currentText()
        self.log_selector.clear()
        # Only show CSV files that look like server logs
        csv_files = [f for f in files if f.endswith('.csv') and 'server_log' in f]
        self.log_selector.addItems(csv_files)
        if current_text in csv_files:
            self.log_selector.setCurrentText(current_text)
        elif csv_files:
            # Select the latest log by default
            self.log_selector.setCurrentIndex(len(csv_files) - 1)

    def _analyze_log(self):
        self._refresh_logs()
        
        filename = self.log_selector.currentText()
        if not filename:
            self.status_label.setText("No log file selected")
            return
        
        filepath = os.path.join(self.logs_controller.logs_dir, filename)
        if not os.path.exists(filepath):
            self.status_label.setText(f"Log file not found: {filename}")
            return
        
        # Check if file is empty
        if os.path.getsize(filepath) == 0:
            self.status_label.setText(f"Log file is empty: {filename}")
            return
            
        try:
            self.status_label.setText(f"Analyzing {filename}...")
            self.data = pd.read_csv(filepath)
            
            if self.data.empty:
                self.status_label.setText(f"No data in log file: {filename}")
                return
            
            # Parse timestamps
            for col in ['timestamp', 'arrival_time']:
                if col in self.data.columns:
                    self.data[col] = pd.to_datetime(self.data[col], errors='coerce')
            
            # Calculate latency
            if 'arrival_time' in self.data.columns and 'timestamp' in self.data.columns:
                latency = (self.data['arrival_time'] - self.data['timestamp']).dt.total_seconds() * 1000
                self.data['latency_ms'] = latency.where((latency >= 0) & (latency < 5000))
            else:
                self.data['latency_ms'] = np.nan
            
            # Convert numeric columns
            for col in ['cpu_time_ms', 'packet_size', 'device_id', 'seq', 'msg_type']:
                if col in self.data.columns:
                    self.data[col] = pd.to_numeric(self.data[col], errors='coerce')
            
            # Convert flag columns
            for col in ['duplicate_flag', 'gap_flag', 'delayed_flag']:
                if col in self.data.columns:
                    self.data[col] = pd.to_numeric(self.data[col], errors='coerce').fillna(0).astype(int)
                else:
                    self.data[col] = 0
                
            self._render_analysis()
            self.status_label.setText(f"Analyzed {len(self.data)} packets from {filename}")
        except Exception as e:
            self.status_label.setText(f"Error analyzing log: {str(e)}")
            import traceback
            traceback.print_exc()

    def _render_analysis(self):
        # Clear existing content
        for layout in [self.stats_grid, self.graphs_grid, self.tables_layout]:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                    
        if self.data is None or self.data.empty:
            return
            
        total_packets = len(self.data)
        loss = int(self.data['gap_flag'].sum()) if 'gap_flag' in self.data.columns else 0
        duplicates = int(self.data['duplicate_flag'].sum()) if 'duplicate_flag' in self.data.columns else 0
        
        # Calculate average latency
        valid_latency = self.data['latency_ms'].dropna()
        avg_latency = valid_latency.mean() if len(valid_latency) > 0 else 0
        
        # Create stat cards
        self._create_stat_card(self.stats_grid, 0, 0, "Total Packets", f"{total_packets:,}", "#3B82F6")
        loss_pct = (loss / total_packets * 100) if total_packets > 0 else 0
        self._create_stat_card(self.stats_grid, 0, 1, "Packet Loss", f"{loss} ({loss_pct:.1f}%)", "#EF4444")
        dup_pct = (duplicates / total_packets * 100) if total_packets > 0 else 0
        self._create_stat_card(self.stats_grid, 0, 2, "Duplicates", f"{duplicates} ({dup_pct:.1f}%)", "#F59E0B")
        self._create_stat_card(self.stats_grid, 0, 3, "Avg Latency", f"{avg_latency:.2f} ms", "#10B981")
        
        # Configure pyqtgraph
        pg.setConfigOptions(antialias=True)
        
        # Latency histogram
        if len(valid_latency) > 0:
            latency_plot = pg.PlotWidget(title="Latency Distribution (ms)")
            latency_plot.setBackground('w')
            latency_plot.setMouseEnabled(x=False, y=False)
            latency_plot.hideButtons()
            latency_plot.showGrid(x=True, y=True, alpha=0.3)
            latency_plot.setMinimumHeight(250)
            
            y, x = np.histogram(valid_latency.values, bins=50)
            latency_plot.plot(x, y, stepMode="center", fillLevel=0, brush=(59, 130, 246, 100), pen=pg.mkPen('#3B82F6', width=2))
            self._create_graph_card(latency_plot, 0, 0)
        
        # Throughput over time
        if 'arrival_time' in self.data.columns:
            valid_arrivals = self.data.dropna(subset=['arrival_time'])
            if len(valid_arrivals) > 0:
                throughput_plot = pg.PlotWidget(title="Throughput Over Time (packets/sec)")
                throughput_plot.setBackground('w')
                throughput_plot.setMouseEnabled(x=False, y=False)
                throughput_plot.hideButtons()
                throughput_plot.showGrid(x=True, y=True, alpha=0.3)
                throughput_plot.setMinimumHeight(250)
                
                # Resample by second
                try:
                    throughput = valid_arrivals.set_index('arrival_time').resample('1s').size()
                    if len(throughput) > 1:
                        # Convert to relative seconds from start
                        start_time = throughput.index.min()
                        x_values = (throughput.index - start_time).total_seconds()
                        throughput_plot.plot(x_values, throughput.values, pen=pg.mkPen('#10B981', width=2), fillLevel=0, brush=(16, 185, 129, 50))
                        throughput_plot.setLabel('bottom', 'Time (seconds)')
                except Exception:
                    pass
                
                self._create_graph_card(throughput_plot, 0, 1)
        
        # Per-device statistics table
        if 'device_id' in self.data.columns:
            try:
                stats_table = self.data.groupby('device_id').agg({
                    'seq': 'count',
                    'gap_flag': 'sum',
                    'duplicate_flag': 'sum',
                    'latency_ms': 'mean',
                    'packet_size': 'sum'
                }).reset_index()
                stats_table.columns = ['Device', 'Packets', 'Loss', 'Dups', 'Avg Latency (ms)', 'Total Bytes']
                self._create_table_card("Per-Device Statistics", stats_table)
            except Exception:
                pass

    def _create_stat_card(self, layout, row, col, title, value, color):
        card = QFrame()
        card.setProperty("class", "page-card")
        card.setMinimumHeight(100)
        apply_shadow(card)
        card_layout = QVBoxLayout(card)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("color:#64748B;font-weight:500;font-size:12px;")
        card_layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setStyleSheet(f"color:{color};font-size:24px;font-weight:bold;")
        card_layout.addWidget(value_label)
        
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
        
        title_label = QLabel(title)
        title_label.setObjectName("SectionHeader")
        card_layout.addWidget(title_label)
        
        table = QTableWidget(len(data), len(data.columns))
        table.setHorizontalHeaderLabels(data.columns.astype(str))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setMinimumHeight(150)
        
        for i in range(len(data)):
            for j in range(len(data.columns)):
                value = data.iloc[i, j]
                if isinstance(value, float):
                    if pd.isna(value):
                        text = "-"
                    else:
                        text = f"{value:.2f}"
                else:
                    text = str(value)
                table.setItem(i, j, QTableWidgetItem(text))
                
        card_layout.addWidget(table)
        self.tables_layout.addWidget(card)
