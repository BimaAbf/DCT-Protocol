from __future__ import annotations
import os, sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QFileSystemWatcher
from main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    style_path = os.path.join(base_dir, "style", "style.qss")
    
    def update_style(path):
        with open(path) as f:
            app.setStyleSheet(f.read())

    update_style(style_path)
    watcher = QFileSystemWatcher([style_path])
    watcher.fileChanged.connect(lambda _: update_style(style_path))
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())