from __future__ import annotations
from typing import List
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from GUI.controllers.clients_controller import ClientsController
from GUI.controllers.logs_controller import LogsController
from GUI.widgets.client_card import ClientCard
from GUI.widgets.client_form import ClientFormDialog
from GUI.style.utils import apply_shadow

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
        self.timer.start(30000)

    def _add_client(self) -> None:
        dialog = ClientFormDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            self.controller.add_client(data)

    def _render(self, clients: List[dict]):
        if self.cards_layout.count() and self.cards_layout.itemAt(self.cards_layout.count() - 1).spacerItem():
            self.cards_layout.removeItem(self.cards_layout.itemAt(self.cards_layout.count() - 1))

        for i, client in enumerate(clients):
            if i < self.cards_layout.count():
                widget = self.cards_layout.itemAt(i).widget()
                if isinstance(widget, ClientCard):
                    widget.update_data(client, position=i)
                    widget.setVisible(True)
                    # Ensure signal is connected (disconnect first to avoid duplicates)
                    try: widget.clicked.disconnect()
                    except: pass
                    widget.clicked.connect(lambda c=client: self.controller.select_client(c.get("device_id")))
                    continue
                if widget: widget.deleteLater()
                
                new_card = ClientCard(client, position=i)
                new_card.clicked.connect(lambda c=client: self.controller.select_client(c.get("device_id")))
                self.cards_layout.insertWidget(i, new_card)
            else:
                new_card = ClientCard(client, position=i)
                new_card.clicked.connect(lambda c=client: self.controller.select_client(c.get("device_id")))
                self.cards_layout.addWidget(new_card)

        while self.cards_layout.count() > len(clients):
            if w := self.cards_layout.takeAt(len(clients)).widget(): w.deleteLater()

        self.cards_layout.addStretch(1)

        if not clients and self.cards_layout.count() == 1:
             lbl = QLabel("No connected clients.", objectName="HelperLabel")
             lbl.setAlignment(Qt.AlignCenter)
             self.cards_layout.insertWidget(0, lbl)
