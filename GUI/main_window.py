from __future__ import annotations
import os
from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QMainWindow, QStackedWidget
from widgets.sidebar import Sidebar
from pages.logs_page import LogsPage
from pages.console_page import ConsolePage
from pages.clients_page import ClientsPage
from pages.dashboard_page import DashboardPage
from pages.analysis_page import AnalysisPage
from pages.client_details_page import ClientDetailsPage
from controllers.logs_controller import LogsController
from controllers.server_controller import ServerController
from controllers.clients_controller import ClientsController
from controllers.console_controller import ConsoleController

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DCT Protocol")
        if os.path.exists("./assets/Logo.svg"):
            self.setWindowIcon(QIcon("./assets/Logo.svg"))
            
        self.resize(1300, 700)
        self.setMinimumSize(QSize(1300, 600))
        
        # ###### remove this section ######################
        # screens = QGuiApplication.screens()
        # geometry = screens[1].availableGeometry()
        # self.move(geometry.x() + (geometry.width() - 1300) // 2, geometry.y() + (geometry.height() - 700) // 2)
        # #################################################
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 0)
        main_layout.setSpacing(10)
        
        self.sidebar = Sidebar()
        sidebar_wrapper = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_wrapper)
        sidebar_layout.setContentsMargins(0, 0, 0, 10)
        sidebar_layout.addWidget(self.sidebar)
        main_layout.addWidget(sidebar_wrapper)
        
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, 1)
        
        self.server_controller = ServerController()
        self.logs_controller = LogsController()
        self.clients_controller = ClientsController(self.logs_controller)
        self.console_controller = ConsoleController(self)
        
        self.pages = [
            DashboardPage(self.server_controller, self.clients_controller, self.logs_controller),
            ClientsPage(self.clients_controller, self.logs_controller),
            AnalysisPage(self.logs_controller),
            LogsPage(self.logs_controller),
            ConsolePage(self.console_controller)
        ]
        
        for page in self.pages:
            self.stacked_widget.addWidget(page)
            
        self.client_details_page = ClientDetailsPage(self.logs_controller)
        self.stacked_widget.addWidget(self.client_details_page)
        
        self.sidebar.pageRequested.connect(self.stacked_widget.setCurrentIndex)
        self.stacked_widget.currentChanged.connect(self._sync_sidebar)
        self.clients_controller.clientSelected.connect(self._show_client_details)
        self.client_details_page.backRequested.connect(lambda: self.stacked_widget.setCurrentIndex(1))

    def _show_client_details(self, client_data):
        self.client_details_page.set_client(client_data)
        self.stacked_widget.setCurrentWidget(self.client_details_page)

    def _sync_sidebar(self, index):
        for i, button in enumerate(self.sidebar.buttons):
            button.setChecked(i == index)

    def closeEvent(self, event):
        self.console_controller.cleanup()
        super().closeEvent(event)