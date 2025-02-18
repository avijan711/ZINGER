from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame
from PyQt6.QtGui import QPainter, QColor, QPen, QDrag, QPixmap, QPainterPath
from PyQt6.QtCore import Qt, QMimeData, QPoint, QSize, QUrl
import os

class PDFDragSource(QWidget):
    """Widget that provides a draggable area for signed PDFs"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_path = None
        self.drag_enabled = False
        self.setMinimumHeight(100)
        self.setMinimumWidth(200)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        
        # Setup layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Create frame with custom styling
        self.frame = QFrame()
        self.frame.setObjectName("dragFrame")
        self.frame.setStyleSheet("""
            QFrame#dragFrame {
                background-color: #f8f9fa;
                border: 2px dashed #dee2e6;
                border-radius: 8px;
            }
            QFrame#dragFrame:hover {
                background-color: #e9ecef;
                border-color: #adb5bd;
            }
        """)
        
        # Add label
        self.label = QLabel("Drag signed PDF from here")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                color: #495057;
                font-size: 14px;
                padding: 20px;
            }
        """)
        
        # Setup frame layout
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.addWidget(self.label)
        
        layout.addWidget(self.frame)
        
    def setPDFPath(self, path: str):
        """Set the path of the PDF to be dragged"""
        self.pdf_path = path
        self.drag_enabled = bool(path and os.path.exists(path))
        
        # Update label and styling based on state
        if self.drag_enabled:
            self.label.setText("← Drag signed PDF from here")
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.frame.setStyleSheet("""
                QFrame#dragFrame {
                    background-color: #e9ecef;
                    border: 2px dashed #adb5bd;
                    border-radius: 8px;
                }
                QFrame#dragFrame:hover {
                    background-color: #dee2e6;
                    border-color: #6c757d;
                }
            """)
        else:
            self.label.setText("No signed PDF available")
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.frame.setStyleSheet("""
                QFrame#dragFrame {
                    background-color: #f8f9fa;
                    border: 2px dashed #dee2e6;
                    border-radius: 8px;
                }
            """)
            
    def mousePressEvent(self, event):
        """Handle mouse press to start drag operation"""
        if not self.drag_enabled or not self.pdf_path or not os.path.exists(self.pdf_path):
            return
            
        if event.button() == Qt.MouseButton.LeftButton:
            try:
                # Create drag object
                drag = QDrag(self)
                mime_data = QMimeData()
                
                # Add URL to mime data
                file_path = os.path.abspath(self.pdf_path)
                url = QUrl.fromLocalFile(file_path)
                mime_data.setUrls([url])
                
                # Create drag feedback pixmap
                pixmap = self._createDragPixmap()
                drag.setPixmap(pixmap)
                drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
                
                # Set mime data and execute drag
                drag.setMimeData(mime_data)
                
                # Update cursor during drag
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                
                # Execute drag
                drag.exec(Qt.DropAction.CopyAction)
                
                # Reset cursor after drag
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                
            except:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            
    def _createDragPixmap(self) -> QPixmap:
        """Create a pixmap for drag feedback"""
        # Create base pixmap
        size = QSize(200, 60)
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        # Setup painter
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw rounded rectangle background
        path = QPainterPath()
        path.addRoundedRect(0, 0, size.width(), size.height(), 8, 8)
        
        # Fill background
        painter.fillPath(path, QColor("#e9ecef"))
        
        # Draw border
        painter.setPen(QPen(QColor("#adb5bd"), 2, Qt.PenStyle.DashLine))
        painter.drawPath(path)
        
        # Draw text
        painter.setPen(QColor("#495057"))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Signed PDF")
        
        painter.end()
        return pixmap
        
    def enterEvent(self, event):
        """Handle mouse enter event"""
        if self.drag_enabled:
            self.frame.setStyleSheet("""
                QFrame#dragFrame {
                    background-color: #dee2e6;
                    border: 2px dashed #6c757d;
                    border-radius: 8px;
                }
            """)
            
    def leaveEvent(self, event):
        """Handle mouse leave event"""
        if self.drag_enabled:
            self.frame.setStyleSheet("""
                QFrame#dragFrame {
                    background-color: #e9ecef;
                    border: 2px dashed #adb5bd;
                    border-radius: 8px;
                }
                QFrame#dragFrame:hover {
                    background-color: #dee2e6;
                    border-color: #6c757d;
                }
            """)