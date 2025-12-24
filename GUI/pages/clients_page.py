from __future__ import annotations
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget
from controllers.clients_controller import ClientsController
from controllers.logs_controller import LogsController
from widgets.client_card import ClientCard
from widgets.client_form import ClientFormDialog
from style.utils import apply_shadow

class ClientsPage(QWidget):
    def __init__(self, controller: ClientsController, logs: LogsController | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller, self.logs = controller, logs
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        
        self.main_scroll = QScrollArea()
        self.main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setFrameShape(QFrame.NoFrame)
        self.main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.main_scroll)

        content = QWidget(objectName="ClientsContent")
        self.main_scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(20)
        layout.addWidget(QLabel("Clients", objectName="ConsoleTitle"))

        card = QFrame(objectName="ClientsScrollCard")
        card.setProperty("class", "page-card")
        apply_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(16)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(" Client Devices", objectName="ClientsSectionTag"))
        controls.addStretch(1)
        
        # Active clients count label
        self.active_label = QLabel("0 active")
        self.active_label.setStyleSheet("color: #64748B; font-size: 12px;")
        controls.addWidget(self.active_label)
        
        # Stop All button
        self.stop_all_btn = QPushButton("Stop All")
        self.stop_all_btn.setFixedSize(90, 38)
        self.stop_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF4444;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #DC2626;
            }
            QPushButton:disabled {
                background-color: #94A3B8;
            }
        """)
        self.stop_all_btn.clicked.connect(self._stop_all_clients)
        self.stop_all_btn.setEnabled(False)
        controls.addWidget(self.stop_all_btn)
        
        self.add_btn = QPushButton("Add Client")
        self.add_btn.setFixedSize(130, 38)
        self.add_btn.clicked.connect(self._add_client)
        controls.addWidget(self.add_btn)
        card_layout.addLayout(controls)

        self.scroll = QScrollArea(objectName="ClientsScrollArea")
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("background-color: transparent; border: none;")
        card_layout.addWidget(self.scroll)

        body = QWidget(objectName="ClientsScrollViewport")
        body.setAttribute(Qt.WA_StyledBackground, True)
        body.setStyleSheet("background-color: transparent;")
        self.cards_layout = QVBoxLayout(body)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(18)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(body)
        layout.addWidget(card, 1)

        self.controller.clientsUpdated.connect(self._render)
        if self.logs: self.logs.logsUpdated.connect(lambda _: self.controller.refresh())
        self._render(self.controller.get_clients())

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.controller.refresh)
        self.timer.start(2000)  # Refresh every 2 seconds for better responsiveness

    def _add_client(self) -> None:
        dialog = ClientFormDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            self.controller.add_client(data)
    
    def _stop_all_clients(self) -> None:
        self.controller.stop_all_clients()
    
    def _stop_client(self, mac: str) -> None:
        self.controller.stop_client(mac)

    def _render(self, clients: list):
        # Update active count
        active_count = sum(1 for c in clients if c.get("is_process") and c.get("status") in ("pending", "connecting", "running"))
        self.active_label.setText(f"{active_count} active")
        self.stop_all_btn.setEnabled(active_count > 0)
        
        if self.cards_layout.count() and self.cards_layout.itemAt(self.cards_layout.count() - 1).spacerItem():
            self.cards_layout.removeItem(self.cards_layout.itemAt(self.cards_layout.count() - 1))

        # Remove "No connected clients" label if present
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, QLabel) and widget.objectName() == "HelperLabel":
                    widget.deleteLater()
                    break

        for i, client in enumerate(clients):
            device_id = client.get("device_id")
            mac = client.get("mac")
            
            if i < self.cards_layout.count():
                widget = self.cards_layout.itemAt(i).widget()
                if isinstance(widget, ClientCard):
                    widget.update_data(client, position=i)
                    widget.setVisible(True)
                    try: widget.clicked.disconnect()
                    except: pass
                    try: widget.stopRequested.disconnect()
                    except: pass
                    widget.clicked.connect(lambda _, did=device_id: self.controller.select_client(did) if did else None)
                    widget.stopRequested.connect(self._stop_client)
                    continue
                if widget: 
                    widget.deleteLater()
                
            new_card = ClientCard(client, position=i)
            new_card.clicked.connect(lambda _, did=device_id: self.controller.select_client(did) if did else None)
            new_card.stopRequested.connect(self._stop_client)
            if i < self.cards_layout.count():
                self.cards_layout.insertWidget(i, new_card)
            else:
                self.cards_layout.addWidget(new_card)

        while self.cards_layout.count() > len(clients):
            if w := self.cards_layout.takeAt(len(clients)).widget(): 
                w.deleteLater()

        self.cards_layout.addStretch(1)

        if not clients and self.cards_layout.count() == 1:
            lbl = QLabel("No connected clients.", objectName="HelperLabel")
            lbl.setAlignment(Qt.AlignCenter)
            self.cards_layout.insertWidget(0, lbl)
