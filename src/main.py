import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)

    # The UI stylesheets assume a light theme (white backgrounds without
    # explicit text colors); pin the palette so OS dark mode can't produce
    # white-on-white text.
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)

    # Set application metadata
    app.setApplicationName("PySign")
    app.setApplicationVersion("2.0.1")
    app.setOrganizationName("PySign")
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()