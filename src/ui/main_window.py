from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QStatusBar, QFileDialog, QMessageBox
)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import Qt, QSize

from core.pdf_handler import PDFHandler
from .pdf_view import PDFView
from .stamp_gallery import StampGallery
from .dialogs.signature_pad import SignaturePadDialog
from config.constants import (
    WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT, TOOLBAR_ICON_SIZE,
    STAMPS_DIR, SIGNATURES_DIR, SUPPORTED_PDF_FORMATS
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.pdf_handler = PDFHandler()
        
        # Ensure storage directories exist
        STAMPS_DIR.mkdir(parents=True, exist_ok=True)
        SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)
        
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("PySign - PDF Signing Application")
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)

        # Create stamp gallery
        self.stamp_gallery = StampGallery(str(STAMPS_DIR))
        layout.addWidget(self.stamp_gallery)

        # Create PDF view
        self.pdf_view = PDFView(self.pdf_handler)
        layout.addWidget(self.pdf_view)

        # Create toolbar
        self.create_toolbar()

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Connect PDF handler signals
        self.pdf_handler.document_loaded.connect(self.on_document_loaded)
        self.pdf_handler.page_changed.connect(self.on_page_changed)
        self.pdf_handler.zoom_changed.connect(self.on_zoom_changed)

    def create_toolbar(self):
        """Create the main toolbar"""
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))
        self.addToolBar(toolbar)

        # File actions
        open_action = QAction("Open", self)
        open_action.setStatusTip("Open PDF document")
        open_action.triggered.connect(self.open_document)
        toolbar.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.setStatusTip("Save PDF document")
        save_action.triggered.connect(self.save_document)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        # Navigation actions
        prev_page = QAction("Previous", self)
        prev_page.setStatusTip("Go to previous page")
        prev_page.triggered.connect(self.previous_page)
        toolbar.addAction(prev_page)

        next_page = QAction("Next", self)
        next_page.setStatusTip("Go to next page")
        next_page.triggered.connect(self.next_page)
        toolbar.addAction(next_page)

        toolbar.addSeparator()

        # Zoom actions
        zoom_in = QAction("Zoom In", self)
        zoom_in.setStatusTip("Zoom in")
        zoom_in.triggered.connect(self.zoom_in)
        toolbar.addAction(zoom_in)

        zoom_out = QAction("Zoom Out", self)
        zoom_out.setStatusTip("Zoom out")
        zoom_out.triggered.connect(self.zoom_out)
        toolbar.addAction(zoom_out)

        fit_width = QAction("Fit Width", self)
        fit_width.setStatusTip("Fit to width")
        fit_width.triggered.connect(self.fit_width)
        toolbar.addAction(fit_width)

        toolbar.addSeparator()

        # Signature actions
        signature_action = QAction("Signature", self)
        signature_action.setStatusTip("Open signature pad")
        signature_action.triggered.connect(self.show_signature_pad)
        toolbar.addAction(signature_action)

    def show_signature_pad(self):
        """Show the signature pad dialog"""
        dialog = SignaturePadDialog(self)
        dialog.exec()

    def open_document(self):
        """Open a PDF document"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PDF Document",
            "",
            f"PDF Files ({SUPPORTED_PDF_FORMATS})"
        )
        if file_path:
            if not self.pdf_handler.open_document(file_path):
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to open the PDF document."
                )

    def save_document(self):
        """Save the PDF document"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF Document",
            "",
            f"PDF Files ({SUPPORTED_PDF_FORMATS})"
        )
        if file_path:
            if not self.pdf_handler.save_document(file_path):
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to save the PDF document."
                )

    def previous_page(self):
        """Go to the previous page"""
        if self.pdf_handler.document:
            self.pdf_handler.navigate_to_page(self.pdf_handler.current_page - 1)

    def next_page(self):
        """Go to the next page"""
        if self.pdf_handler.document:
            self.pdf_handler.navigate_to_page(self.pdf_handler.current_page + 1)

    def zoom_in(self):
        """Zoom in the document view"""
        if self.pdf_handler.document:
            self.pdf_handler.set_zoom(self.pdf_handler.zoom_level * 1.2)

    def zoom_out(self):
        """Zoom out the document view"""
        if self.pdf_handler.document:
            self.pdf_handler.set_zoom(self.pdf_handler.zoom_level / 1.2)

    def fit_width(self):
        """Fit document to window width"""
        if self.pdf_handler.document:
            # Calculate zoom level based on window and page width
            page_info = self.pdf_handler.get_page_info(self.pdf_handler.current_page)
            if page_info:
                view_width = self.pdf_view.width() - self.stamp_gallery.width()
                zoom = view_width / page_info.size[0]
                self.pdf_handler.set_zoom(zoom)

    # Signal handlers
    def on_document_loaded(self, success: bool):
        """Handle document loaded signal"""
        if success:
            self.status_bar.showMessage("Document loaded successfully")
        else:
            self.status_bar.showMessage("Failed to load document")

    def on_page_changed(self, current: int, total: int):
        """Handle page changed signal"""
        self.status_bar.showMessage(f"Page {current + 1} of {total}")

    def on_zoom_changed(self, zoom: float):
        """Handle zoom changed signal"""
        zoom_percent = int(zoom * 100)
        self.status_bar.showMessage(f"Zoom: {zoom_percent}%")