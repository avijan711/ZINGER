from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QInputDialog, QMessageBox,
    QScrollArea, QWidget, QGridLayout
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QPixmap, QImage,
    QPainterPath, QMouseEvent
)
from PyQt6.QtCore import (
    Qt, QPoint, QRect, QSize, QByteArray,
    QBuffer, QIODevice
)
from datetime import datetime
from PIL import Image
from io import BytesIO
import os

from core.signature_manager import SignatureManager
from config.constants import SUPPORTED_IMAGE_FORMATS, SIGNATURES_DIR

class SignatureCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.path = QPainterPath()
        self.points = []
        self.last_point = None
        self.is_drawing = False
        
        # Set fixed size for canvas
        self.setFixedSize(400, 200)
        
        # Set white background
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), Qt.GlobalColor.white)
        self.setPalette(palette)

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_drawing = True
            self.last_point = event.position().toPoint()
            self.points = [self.last_point]
            self.path = QPainterPath()
            self.path.moveTo(event.position())

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move events"""
        if self.is_drawing:
            new_point = event.position().toPoint()
            self.path.lineTo(event.position())
            self.points.append(new_point)
            self.last_point = new_point
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release events"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_drawing = False

    def paintEvent(self, event):
        """Paint the signature"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background
        painter.fillRect(event.rect(), Qt.GlobalColor.white)
        
        # Draw signature
        pen = QPen(Qt.GlobalColor.black, 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawPath(self.path)

    def clear(self):
        """Clear the signature"""
        self.path = QPainterPath()
        self.points = []
        self.last_point = None
        self.update()

    def get_signature_image(self) -> bytes:
        """Get the signature as a PNG image"""
        # Create pixmap and fill with white
        pixmap = QPixmap(self.size())
        pixmap.fill(Qt.GlobalColor.white)
        
        # Draw signature on pixmap
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(Qt.GlobalColor.black, 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawPath(self.path)
        painter.end()
        
        # Convert to bytes
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, 'PNG')
        buffer.close()
        
        return byte_array.data()

class SignatureThumbnail(QLabel):
    def __init__(self, signature_id: str, signature_data: bytes, name: str, parent=None):
        super().__init__(parent)
        self.signature_id = signature_id
        self.signature_data = signature_data
        self.signature_name = name
        
        # Create pixmap from signature data
        image = QImage.fromData(signature_data)
        pixmap = QPixmap.fromImage(image)
        
        # Scale pixmap to thumbnail size
        scaled_pixmap = pixmap.scaled(
            160, 80,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # Set pixmap and configure label
        self.setPixmap(scaled_pixmap)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip(name)
        self.setFixedSize(QSize(180, 100))
        
        # Add border
        self.setStyleSheet("border: 1px solid gray;")

class SignaturePadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.signature_manager = SignatureManager(str(SIGNATURES_DIR))
        self.selected_signature = None
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Signature Pad")
        self.setMinimumWidth(800)
        
        layout = QHBoxLayout(self)
        
        # Left side - Drawing area
        left_layout = QVBoxLayout()
        
        # Signature canvas
        self.canvas = SignatureCanvas()
        left_layout.addWidget(self.canvas)
        
        # Canvas controls
        canvas_controls = QHBoxLayout()
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.canvas.clear)
        canvas_controls.addWidget(clear_btn)
        
        save_btn = QPushButton("Save Signature")
        save_btn.clicked.connect(self.save_signature)
        canvas_controls.addWidget(save_btn)
        
        import_btn = QPushButton("Import Image")
        import_btn.clicked.connect(self.import_signature)
        canvas_controls.addWidget(import_btn)
        
        left_layout.addLayout(canvas_controls)
        
        # Date stamp controls
        date_controls = QHBoxLayout()
        
        add_date_btn = QPushButton("Add Date Stamp")
        add_date_btn.clicked.connect(self.add_date_stamp)
        date_controls.addWidget(add_date_btn)
        
        left_layout.addLayout(date_controls)
        
        layout.addLayout(left_layout)
        
        # Right side - Saved signatures
        right_layout = QVBoxLayout()
        
        # Title
        title = QLabel("Saved Signatures")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(title)
        
        # Scroll area for signatures
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Content widget for scroll area
        self.content = QWidget()
        self.grid_layout = QGridLayout(self.content)
        self.grid_layout.setSpacing(10)
        
        scroll.setWidget(self.content)
        right_layout.addWidget(scroll)
        
        # Signature controls
        sig_controls = QHBoxLayout()
        
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self.delete_signature)
        sig_controls.addWidget(delete_btn)
        
        rename_btn = QPushButton("Rename")
        rename_btn.clicked.connect(self.rename_signature)
        sig_controls.addWidget(rename_btn)
        
        right_layout.addLayout(sig_controls)
        
        layout.addLayout(right_layout)
        
        # Load saved signatures
        self.load_signatures()

    def load_signatures(self):
        """Load saved signatures"""
        # Clear existing signatures
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Load signatures
        signatures = self.signature_manager.get_all_signatures()
        for i, sig in enumerate(signatures):
            sig_data = self.signature_manager.get_signature_data(sig['id'])
            if sig_data:
                row = i // 2  # 2 signatures per row
                col = i % 2
                thumbnail = SignatureThumbnail(sig['id'], sig_data[0], sig['name'])
                thumbnail.mousePressEvent = lambda e, s=sig['id']: self.select_signature(s)
                self.grid_layout.addWidget(thumbnail, row, col)

    def save_signature(self):
        """Save the current signature"""
        name, ok = QInputDialog.getText(
            self,
            "Save Signature",
            "Enter name for signature:"
        )
        
        if ok and name:
            # Get signature image
            signature_data = self.canvas.get_signature_image()
            
            # Save signature
            if self.signature_manager.save_signature(signature_data, name):
                self.load_signatures()
                self.canvas.clear()
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to save signature."
                )

    def import_signature(self):
        """Import a signature from an image file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Signature",
            "",
            f"Image Files ({SUPPORTED_IMAGE_FORMATS})"
        )
        
        if file_path:
            name, ok = QInputDialog.getText(
                self,
                "Signature Name",
                "Enter name for signature:"
            )
            
            if ok and name:
                if self.signature_manager.import_signature(file_path, name):
                    self.load_signatures()
                else:
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to import signature."
                    )

    def delete_signature(self):
        """Delete the selected signature"""
        if self.selected_signature:
            reply = QMessageBox.question(
                self,
                "Delete Signature",
                "Are you sure you want to delete this signature?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                if self.signature_manager.delete_signature(self.selected_signature):
                    self.selected_signature = None
                    self.load_signatures()
                else:
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to delete signature."
                    )

    def rename_signature(self):
        """Rename the selected signature"""
        if self.selected_signature:
            new_name, ok = QInputDialog.getText(
                self,
                "Rename Signature",
                "Enter new name:"
            )
            
            if ok and new_name:
                if self.signature_manager.rename_signature(self.selected_signature, new_name):
                    self.load_signatures()
                else:
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to rename signature."
                    )

    def select_signature(self, signature_id: str):
        """Select a signature"""
        self.selected_signature = signature_id
        
        # Highlight selected signature
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, SignatureThumbnail):
                if widget.signature_id == signature_id:
                    widget.setStyleSheet("border: 2px solid blue;")
                else:
                    widget.setStyleSheet("border: 1px solid gray;")

    def add_date_stamp(self):
        """Add a date stamp"""
        date_stamp = self.signature_manager.create_date_stamp()
        if date_stamp:
            name = f"Date Stamp {datetime.now().strftime('%Y-%m-%d')}"
            if self.signature_manager.save_signature(date_stamp, name):
                self.load_signatures()
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to create date stamp."
                )