from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QInputDialog, QMessageBox,
    QScrollArea, QWidget, QGridLayout, QStyle
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QPixmap, QImage,
    QPainterPath, QMouseEvent, QDrag
)
from PyQt6.QtCore import (
    Qt, QPoint, QRect, QSize, QByteArray,
    QBuffer, QIODevice, QMimeData
)
from datetime import datetime
from PIL import Image
from io import BytesIO
import os
import json

from core.signature_manager import SignatureManager
from config.constants import SUPPORTED_IMAGE_FORMATS, SIGNATURES_DIR

class SignatureCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.path = QPainterPath()
        self.points = []
        self.last_point = None
        self.is_drawing = False
        self.show_guide = True  # Show guide text when empty
        
        # Set fixed size for canvas
        self.setFixedSize(500, 200)  # Wider canvas for better usability
        
        # Set white background with border
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), Qt.GlobalColor.white)
        self.setPalette(palette)
        
        # Add border and shadow effect
        self.setStyleSheet("""
            SignatureCanvas {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 4px;
            }
        """)

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
        """Paint the signature with guide text and grid"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background
        painter.fillRect(event.rect(), Qt.GlobalColor.white)
        
        # Draw subtle grid pattern
        grid_pen = QPen(QColor("#f0f0f0"), 1, Qt.PenStyle.SolidLine)
        painter.setPen(grid_pen)
        
        # Vertical lines
        for x in range(0, self.width(), 50):
            painter.drawLine(x, 0, x, self.height())
            
        # Horizontal lines
        for y in range(0, self.height(), 50):
            painter.drawLine(0, y, self.width(), y)
        
        # Draw baseline
        baseline_pen = QPen(QColor("#e0e0e0"), 2, Qt.PenStyle.DashLine)
        painter.setPen(baseline_pen)
        baseline_y = self.height() * 2 // 3
        painter.drawLine(0, baseline_y, self.width(), baseline_y)
        
        # Draw guide text if no signature and show_guide is True
        if not self.points and self.show_guide:
            painter.setPen(QPen(QColor("#999999")))
            font = painter.font()
            font.setPointSize(12)
            painter.setFont(font)
            text_rect = self.rect()
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "Sign Here")
        
        # Draw signature with smooth, variable-width pen
        if self.points:
            pen = QPen(Qt.GlobalColor.black, 2, Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
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
        self.is_selected = False
        
        # Create pixmap from signature data
        image = QImage.fromData(signature_data)
        pixmap = QPixmap.fromImage(image)
        
        # Scale pixmap to thumbnail size
        scaled_pixmap = pixmap.scaled(
            200, 100,  # Larger size for better visibility
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # Set pixmap and configure label
        self.setPixmap(scaled_pixmap)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip(f"Name: {name}\nClick to select")
        self.setFixedSize(QSize(220, 140))  # Larger size to accommodate name label
        
        # Modern styling with hover effect
        self.setStyleSheet("""
            SignatureThumbnail {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                margin: 4px;
            }
            SignatureThumbnail:hover {
                border-color: #2196F3;
                background-color: #f8f9fa;
            }
        """)
        
        # Add name label below thumbnail
        self.name_label = QLabel(name, self)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("""
            QLabel {
                color: #495057;
                font-size: 12px;
                padding-top: 4px;
            }
        """)
        self.name_label.move(0, self.height() - 25)
        self.name_label.setFixedWidth(self.width())

    def setSelected(self, selected: bool):
        """Update the selection state and styling"""
        self.is_selected = selected
        if selected:
            self.setStyleSheet("""
                SignatureThumbnail {
                    background-color: #e3f2fd;
                    border: 2px solid #2196F3;
                    border-radius: 4px;
                    padding: 8px;
                    margin: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                SignatureThumbnail {
                    background-color: white;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                    padding: 8px;
                    margin: 4px;
                }
                SignatureThumbnail:hover {
                    border-color: #2196F3;
                    background-color: #f8f9fa;
                }
            """)

    def mousePressEvent(self, event):
        """Handle mouse press for selection and drag start"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Store the start position for drag detection
            self.drag_start_position = event.pos()
            # Let parent handle selection
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for drag and drop"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        # Check if we've moved enough to start a drag
        if not hasattr(self, 'drag_start_position'):
            return

        if (event.pos() - self.drag_start_position).manhattanLength() < 10:
            return

        # Create mime data with signature information
        mime_data = QMimeData()
        mime_data.setData("application/x-signature", QByteArray(self.signature_data))
        mime_data.setText(self.signature_name)

        # Add metadata as JSON - get dimensions from original image data
        original_img = QImage.fromData(self.signature_data)
        original_width = original_img.width() if not original_img.isNull() else 100
        original_height = original_img.height() if not original_img.isNull() else 100
        aspect_ratio = original_width / original_height if original_height > 0 else 1.0

        metadata = {
            'type': 'signature',
            'aspect_ratio': aspect_ratio,
            'original_width': original_width,
            'original_height': original_height
        }
        metadata_bytes = json.dumps(metadata).encode('utf-8')
        mime_data.setData("application/x-signature-metadata", QByteArray(metadata_bytes))

        # Create drag object
        drag = QDrag(self)
        drag.setMimeData(mime_data)

        # Create drag pixmap (scaled for better visibility)
        pixmap = self.pixmap()
        if pixmap:
            scaled_pixmap = pixmap.scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            drag.setPixmap(scaled_pixmap)
            drag.setHotSpot(QPoint(scaled_pixmap.width() // 2, scaled_pixmap.height() // 2))

        # Execute drag operation
        drag.exec(Qt.DropAction.CopyAction)

class SignaturePadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.signature_manager = SignatureManager(str(SIGNATURES_DIR))
        self.selected_signature = None
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface with modern styling"""
        self.setWindowTitle("Signature Pad")
        self.setMinimumWidth(900)  # Wider dialog for better layout
        
        # Apply modern styling to the dialog
        self.setStyleSheet("""
            QDialog {
                background-color: white;
            }
            QPushButton {
                padding: 8px 16px;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
                color: #212529;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #f8f9fa;
                border-color: #c1c9d0;
            }
            QPushButton:pressed {
                background-color: #e9ecef;
            }
            QPushButton[class="primary"] {
                background-color: #2196F3;
                color: white;
                border: none;
            }
            QPushButton[class="primary"]:hover {
                background-color: #1976D2;
            }
            QPushButton[class="danger"] {
                background-color: #dc3545;
                color: white;
                border: none;
            }
            QPushButton[class="danger"]:hover {
                background-color: #c82333;
            }
            QLabel {
                color: #212529;
                font-size: 14px;
            }
            QLabel[class="title"] {
                font-size: 16px;
                font-weight: bold;
                padding: 8px;
                margin-bottom: 8px;
            }
            QScrollArea {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setSpacing(20)  # Increased spacing between sections
        
        # Left side - Drawing area
        left_layout = QVBoxLayout()
        left_layout.setSpacing(15)  # Increased spacing between elements
        
        # Drawing area title
        drawing_title = QLabel("Draw Signature")
        drawing_title.setProperty("class", "title")
        drawing_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(drawing_title)
        
        # Signature canvas
        self.canvas = SignatureCanvas()
        left_layout.addWidget(self.canvas, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        # Canvas controls
        canvas_controls = QHBoxLayout()
        canvas_controls.setSpacing(10)
        
        clear_btn = QPushButton("Clear")
        clear_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
        clear_btn.clicked.connect(self.canvas.clear)
        canvas_controls.addWidget(clear_btn)
        
        save_btn = QPushButton("Save Signature")
        save_btn.setProperty("class", "primary")
        save_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        save_btn.clicked.connect(self.save_signature)
        canvas_controls.addWidget(save_btn)
        
        import_btn = QPushButton("Import Image")
        import_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        import_btn.clicked.connect(self.import_signature)
        canvas_controls.addWidget(import_btn)
        
        left_layout.addLayout(canvas_controls)
        
        # Date stamp controls
        date_controls = QHBoxLayout()
        
        add_date_btn = QPushButton("Add Date Stamp")
        add_date_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        add_date_btn.clicked.connect(self.add_date_stamp)
        date_controls.addWidget(add_date_btn)
        
        left_layout.addLayout(date_controls)
        
        layout.addLayout(left_layout)
        
        # Right side - Saved signatures
        right_layout = QVBoxLayout()
        right_layout.setSpacing(15)
        
        # Title
        title = QLabel("Saved Signatures")
        title.setProperty("class", "title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(title)
        
        # Scroll area for signatures
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(300)  # Set minimum width for better layout
        
        # Content widget for scroll area
        self.content = QWidget()
        self.grid_layout = QGridLayout(self.content)
        self.grid_layout.setSpacing(15)  # Increased spacing between signatures
        
        scroll.setWidget(self.content)
        right_layout.addWidget(scroll)
        
        # Signature controls
        sig_controls = QHBoxLayout()
        sig_controls.setSpacing(10)
        
        delete_btn = QPushButton("Delete")
        delete_btn.setProperty("class", "danger")
        delete_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        delete_btn.clicked.connect(self.delete_signature)
        sig_controls.addWidget(delete_btn)
        
        rename_btn = QPushButton("Rename")
        rename_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
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
        """Select a signature with visual feedback"""
        self.selected_signature = signature_id
        
        # Update selection state for all thumbnails
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, SignatureThumbnail):
                widget.setSelected(widget.signature_id == signature_id)

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