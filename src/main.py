import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # Set application metadata
    app.setApplicationName("PySign")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("PySign")
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()