from __future__ import annotations
import os, sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QFileSystemWatcher
from GUI.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    style_path = "./style/style.qss"
    
    def update_style(path):
        if os.path.exists(path):
            try:
                with open(path) as f:
                    app.setStyleSheet(f.read())
            except:
                pass
                
    update_style(style_path)
    watcher = QFileSystemWatcher([style_path])
    watcher.fileChanged.connect(lambda _: update_style(style_path))
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
