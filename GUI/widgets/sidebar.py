import os
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QFrame, QLabel, QPushButton)
from GUI.style.utils import apply_shadow

class Sidebar(QFrame):
    pageRequested = Signal(int)

    def __init__(self, parent=None):

        base_path = os.path.dirname(__file__)
        
        super().__init__(parent)
        self.setObjectName("SidebarPanel")
        self.setFixedWidth(280)
        self.setAttribute(Qt.WA_StyledBackground)
        apply_shadow(self)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignTop)
        
        logo_row = QHBoxLayout()
        logo_row.setSpacing(12)
        logo_pixmap = QPixmap(os.path.join(base_path, "../assets/logo.svg"))
        logo_label = QLabel(objectName="SidebarLogo")
        
        logo_label.setPixmap(logo_pixmap.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
        logo_label.setFixedSize(30, 30)
        logo_row.addWidget(logo_label)
        logo_row.addWidget(QLabel("DCT Protocol", objectName="SidebarTitle"))
        layout.addLayout(logo_row)
        
        divider = QFrame(objectName="SidebarDivider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)
        
        self.buttons = []
        items = [
            (" Dashboard", "../assets/icons/dashboard.svg"),
            (" Clients", "../assets/icons/clients.svg"),
            (" Server Analysis", "../assets/icons/analysis.svg"),
            (" Server Logs", "../assets/icons/logs.svg"),
            (" Console", "../assets/icons/console.svg")
        ]
        
        for i, (text, icon_path) in enumerate(items):
            button = QPushButton(text, objectName="SidebarButton")
            button.setCursor(Qt.PointingHandCursor)
            button.setCheckable(True)
            icon_pixmap = QPixmap(os.path.join(base_path, icon_path))
            
            button.setIcon(QIcon(icon_pixmap))
            button.setIconSize(QSize(20, 20))
            
            button.clicked.connect(lambda checked=False, index=i: self.pageRequested.emit(index))
            layout.addWidget(button)
            self.buttons.append(button)
            
        if self.buttons:
            self.buttons[0].setChecked(True)
