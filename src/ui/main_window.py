from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QStatusBar, QFileDialog, QMessageBox,
    QFrame
)
from PyQt6.QtGui import (
    QAction, QIcon, QDragEnterEvent,
    QDragMoveEvent, QDropEvent
)
from PyQt6.QtCore import Qt, QSize

from core.pdf_handler import PDFHandler
from core.share_manager import ShareManager
from .pdf_view import PDFView
from .stamp_gallery import StampGallery
from .dialogs.signature_pad import SignaturePadDialog
from .pdf_drag_source import PDFDragSource
from config.constants import (
    WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT, TOOLBAR_ICON_SIZE,
    STAMPS_DIR, SIGNATURES_DIR, SUPPORTED_PDF_FORMATS
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.pdf_handler = PDFHandler()
        self.share_manager = ShareManager()
        
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
        central_widget.setAcceptDrops(True)  # Enable drops on central widget
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Create horizontal layout for main content
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)
        
        # Enable drops on main window
        self.setAcceptDrops(True)

        # Create stamp gallery
        self.stamp_gallery = StampGallery(str(STAMPS_DIR))
        content_layout.addWidget(self.stamp_gallery)

        # Create PDF view
        self.pdf_view = PDFView(self.pdf_handler)
        content_layout.addWidget(self.pdf_view)
        
        # Create drag source area
        self.drag_source = PDFDragSource()
        self.drag_source.setFixedHeight(80)  # Set fixed height for the drag area
        
        # Create a container for the drag source with styling
        drag_container = QFrame()
        drag_container.setObjectName("dragContainer")
        drag_container.setStyleSheet("""
            QFrame#dragContainer {
                background-color: #f8f9fa;
                border-top: 1px solid #dee2e6;
                padding: 10px;
            }
        """)
        drag_layout = QHBoxLayout(drag_container)
        drag_layout.addWidget(self.drag_source)
        
        # Add drag source container to main layout
        main_layout.addWidget(drag_container)

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
        
        # Add Sign button with prominent styling
        sign_action = QAction("Sign", self)
        sign_action.setStatusTip("Sign and save the document")
        sign_action.triggered.connect(self.sign_document)
        sign_action.setProperty("class", "primary")
        toolbar.addAction(sign_action)
        
        # Style the Sign button to make it prominent
        toolbar.setStyleSheet("""
            QToolButton[class="primary"] {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 4px;
                margin: 0 5px;
            }
            QToolButton[class="primary"]:hover {
                background-color: #0056b3;
            }
            QToolButton[class="primary"]:pressed {
                background-color: #004085;
            }
        """)
        
        toolbar.addSeparator()
        
        # Share actions
        email_action = QAction("Share via Email", self)
        email_action.setStatusTip("Share via Outlook email")
        email_action.triggered.connect(self.share_via_email)
        toolbar.addAction(email_action)
        
        whatsapp_action = QAction("Share via WhatsApp", self)
        whatsapp_action.setStatusTip("Share via WhatsApp Web")
        whatsapp_action.triggered.connect(self.share_via_whatsapp)
        toolbar.addAction(whatsapp_action)
        
    def share_via_whatsapp(self):
        """Share the current document via WhatsApp"""
        if not self.pdf_handler.document:
            QMessageBox.warning(
                self,
                "Warning",
                "Please open a document first."
            )
            return
            
        # Save current document to temporary file
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Document for Sharing",
            "",
            f"PDF Files ({SUPPORTED_PDF_FORMATS})"
        )
        
        if file_path:
            if self.pdf_handler.save_document(file_path):
                # Share via WhatsApp
                if not self.share_manager.share_via_whatsapp(file_path):
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to open WhatsApp Web. Please try again."
                    )
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to save the document for sharing."
                )
        
    def share_via_email(self):
        """Share the current document via email"""
        if not self.pdf_handler.document:
            QMessageBox.warning(
                self,
                "Warning",
                "Please open a document first."
            )
            return
            
        # Save current document to temporary file
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Document for Sharing",
            "",
            f"PDF Files ({SUPPORTED_PDF_FORMATS})"
        )
        
        if file_path:
            if self.pdf_handler.save_document(file_path):
                # Share via email
                if not self.share_manager.share_via_email(
                    file_path,
                    "",  # No default subject
                    ""   # No default body
                ):
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to create email. Please check if Outlook is installed and running."
                    )
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to save the document for sharing."
                )

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
                
    def sign_document(self):
        """Sign and save the document automatically"""
        print("\n=== Signing Document ===")
        if not self.pdf_handler.document:
            print("No document loaded")
            QMessageBox.warning(
                self,
                "Warning",
                "Please open a document first."
            )
            return
            
        try:
            # Get the path for the signed document
            signed_path = self.pdf_handler.get_signed_path()
            print(f"Generated signed path: {signed_path}")
            
            if not signed_path:
                print("Failed to generate signed path")
                QMessageBox.critical(
                    self,
                    "Error",
                    "Could not determine save location."
                )
                return
                
            # Save the document
            print(f"Attempting to save document to: {signed_path}")
            if self.pdf_handler.save_document():
                print("Document saved successfully")
                self.status_bar.showMessage(f"Document signed and saved to: {signed_path}")
                # Update drag source with the new file
                print("Updating drag source with new file")
                self.drag_source.setPDFPath(signed_path)
            else:
                print("Failed to save document")
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to save the signed document."
                )
        except Exception as e:
            print(f"Error during signing: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while signing the document: {str(e)}"
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
            # Reset drag source when new document is loaded
            self.drag_source.setPDFPath(None)
        else:
            self.status_bar.showMessage("Failed to load document")
            self.drag_source.setPDFPath(None)

    def on_page_changed(self, current: int, total: int):
        """Handle page changed signal"""
        self.status_bar.showMessage(f"Page {current + 1} of {total}")

    def on_zoom_changed(self, zoom: float):
        """Handle zoom changed signal"""
        zoom_percent = int(zoom * 100)
        self.status_bar.showMessage(f"Zoom: {zoom_percent}%")

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events"""
        mime_data = event.mimeData()
        
        # Accept any drag that has URLs
        if mime_data.hasUrls():
            event.acceptProposedAction()
            return
            
        # Accept PDF-related MIME types
        pdf_mime_types = [
            "application/x-stamp",
            "application/pdf",
            "application/x-pdf",
            "application/acrobat",
            "application/vnd.pdf",
            "text/pdf",
            "text/x-pdf"
        ]
        
        for mime_type in pdf_mime_types:
            if mime_data.hasFormat(mime_type):
                event.acceptProposedAction()
                return
                
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        """Handle drag move events"""
        mime_data = event.mimeData()
        
        # Accept any drag that has URLs
        if mime_data.hasUrls():
            event.acceptProposedAction()
            return
            
        # Accept PDF-related MIME types
        pdf_mime_types = [
            "application/x-stamp",
            "application/pdf",
            "application/x-pdf",
            "application/acrobat",
            "application/vnd.pdf",
            "text/pdf",
            "text/x-pdf"
        ]
        
        for mime_type in pdf_mime_types:
            if mime_data.hasFormat(mime_type):
                event.acceptProposedAction()
                return
                
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle drop events"""
        mime_data = event.mimeData()
        
        try:
            # Handle URL drops
            if mime_data.hasUrls():
                for url in mime_data.urls():
                    if url.isLocalFile():
                        file_path = url.toLocalFile()
                        if file_path.lower().endswith('.pdf'):
                            if self.pdf_handler.open_document(file_path):
                                event.acceptProposedAction()
                                return
            
            # Forward other drops to PDF view
            self.pdf_view.dropEvent(event)
        except Exception as e:
            print(f"Error handling drop event: {e}")
            event.ignore()