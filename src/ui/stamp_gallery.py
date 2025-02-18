from PyQt6.QtWidgets import (
    QLabel, QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QPushButton, QComboBox, QFileDialog, QInputDialog,
    QMessageBox, QFrame
)
from PyQt6.QtGui import QPixmap, QDrag, QImage
from PyQt6.QtCore import Qt, QMimeData, QSize, QByteArray, QPoint
from core.stamp_manager import StampManager
from .flow_layout import FlowLayout
import json

class StampThumbnail(QLabel):
    def __init__(self, stamp_id: str, stamp_data: bytes, name: str, metadata: dict, gallery=None, parent=None):
        super().__init__(parent)
        self.stamp_id = stamp_id
        self.stamp_data = stamp_data
        self.stamp_name = name
        self.metadata = metadata
        self.gallery = gallery
        
        # Create pixmap from stamp data
        image = QImage.fromData(stamp_data)
        pixmap = QPixmap.fromImage(image)
        
        # Scale pixmap to thumbnail size
        scaled_pixmap = pixmap.scaled(
            80, 80,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # Set pixmap and configure label
        self.setPixmap(scaled_pixmap)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip(name)
        self.setFixedSize(QSize(100, 100))
        self.setStyleSheet("""
            QLabel {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                margin: 4px;
            }
            QLabel:hover {
                border-color: #0078d4;
                background-color: #f0f9ff;
                border-width: 2px;
                padding: 7px;
            }
        """)
        
        # Add name label
        self.name_label = QLabel(name, self)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.95);
                border-radius: 2px;
                padding: 2px 4px;
                font-size: 10px;
                color: #333;
            }
        """)
        self.name_label.setWordWrap(True)
        self.name_label.setMaximumWidth(90)
        
        # Position name label at bottom
        self.name_label.setGeometry(5, 70, 90, 25)

    def mousePressEvent(self, event):
        """Handle mouse press for drag and drop"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Create mime data with stamp information
            mime_data = QMimeData()
            mime_data.setData("application/x-stamp", QByteArray(self.stamp_data))
            mime_data.setText(self.stamp_name)  # Set stamp name
            
            # Add metadata as JSON
            metadata_bytes = json.dumps(self.metadata).encode('utf-8')
            mime_data.setData("application/x-stamp-metadata", QByteArray(metadata_bytes))
            
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
                # Center the hotspot
                drag.setHotSpot(QPoint(scaled_pixmap.width() // 2, scaled_pixmap.height() // 2))
            
            # Execute drag operation with both Copy and Move actions
            drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)

class StampGallery(QWidget):
    def __init__(self, storage_path: str):
        super().__init__()
        self.stamp_manager = StampManager(storage_path)
        self.init_ui()
        
        # Connect stamp manager signals
        self.stamp_manager.stamp_added.connect(self.on_stamp_added)
        self.stamp_manager.stamp_removed.connect(self.on_stamp_removed)
        self.stamp_manager.stamp_renamed.connect(self.on_stamp_renamed)
        self.stamp_manager.category_added.connect(self.on_category_added)
        self.stamp_manager.category_removed.connect(self.on_category_removed)

    def init_ui(self):
        """Initialize the user interface"""
        # Main layout with margins and spacing
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Create category section with frame
        category_frame = QFrame()
        category_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
            }
        """)
        category_layout = QVBoxLayout(category_frame)
        category_layout.setContentsMargins(8, 8, 8, 8)
        category_layout.setSpacing(8)
        
        # Category selector with styling
        self.category_combo = QComboBox()
        self.category_combo.addItems(self.stamp_manager.get_categories())
        self.category_combo.currentTextChanged.connect(self.load_stamps)
        self.category_combo.setStyleSheet("""
            QComboBox {
                padding: 4px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
                min-height: 24px;
            }
            QComboBox:hover {
                border-color: #0078d4;
            }
        """)
        category_layout.addWidget(self.category_combo)
        
        # Category buttons in horizontal layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)
        
        # Add category button with styling
        add_category_btn = QPushButton("Add Category")
        add_category_btn.clicked.connect(self.add_category)
        add_category_btn.setStyleSheet("""
            QPushButton {
                padding: 4px 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #e9ecef;
            }
        """)
        button_layout.addWidget(add_category_btn)
        
        # Remove category button with styling
        remove_category_btn = QPushButton("Remove Category")
        remove_category_btn.clicked.connect(self.remove_category)
        remove_category_btn.setStyleSheet("""
            QPushButton {
                padding: 4px 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #e9ecef;
            }
        """)
        button_layout.addWidget(remove_category_btn)
        
        category_layout.addLayout(button_layout)
        
        # Import stamp button with prominent styling
        import_btn = QPushButton("Import Stamp")
        import_btn.clicked.connect(self.import_stamp)
        import_btn.setStyleSheet("""
            QPushButton {
                padding: 8px;
                border: 1px solid #0078d4;
                border-radius: 4px;
                background-color: #0078d4;
                color: white;
                min-height: 32px;
            }
            QPushButton:hover {
                background-color: #006cbd;
            }
        """)
        category_layout.addWidget(import_btn)
        
        layout.addWidget(category_frame)
        
        # Create scroll area for stamps with styling
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 4px;
            }
        """)
        
        # Create content widget for scroll area
        self.content = QWidget()
        self.content.setStyleSheet("""
            QWidget {
                background-color: white;
                padding: 8px;
            }
        """)
        
        # Create flow layout for stamps
        self.flow_layout = FlowLayout(self.content, margin=8, spacing=8)
        
        scroll.setWidget(self.content)
        layout.addWidget(scroll, 1)
        
        # Set fixed width for gallery
        self.setFixedWidth(300)
        
        # Load initial stamps
        self.load_stamps(self.category_combo.currentText())

    def load_stamps(self, category: str):
        """Load stamps for the selected category"""
        # Clear existing stamps
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Load stamps from category
        stamps = self.stamp_manager.get_stamps_by_category(category)
        for stamp in stamps:
            stamp_data = self.stamp_manager.get_stamp_data(stamp['id'])
            if stamp_data:
                # Create metadata with defaults
                metadata = {
                    'aspect_ratio': stamp.get('aspect_ratio', 1.0),
                    'original_width': stamp.get('original_width', 100),
                    'original_height': stamp.get('original_height', 100)
                }
                
                thumbnail = StampThumbnail(
                    stamp['id'],
                    stamp_data[0],
                    stamp_data[1],
                    metadata,
                    gallery=self
                )
                
                # Add widget to flow layout
                self.flow_layout.addWidget(thumbnail)

    def import_stamp(self):
        """Import a new stamp"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Stamp",
            "",
            "Image Files (*.png *.jpg *.jpeg)"
        )
        
        if file_path:
            name, ok = QInputDialog.getText(
                self,
                "Stamp Name",
                "Enter name for stamp:"
            )
            
            if ok and name:
                category = self.category_combo.currentText()
                stamp_id = self.stamp_manager.import_stamp(file_path, name, category)
                
                if not stamp_id:
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to import stamp."
                    )

    def add_category(self):
        """Add a new category"""
        name, ok = QInputDialog.getText(
            self,
            "Add Category",
            "Enter category name:"
        )
        
        if ok and name:
            if not self.stamp_manager.add_category(name):
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to add category."
                )

    def remove_category(self):
        """Remove the selected category"""
        category = self.category_combo.currentText()
        if category == "General":
            QMessageBox.warning(
                self,
                "Warning",
                "Cannot remove the General category."
            )
            return
        
        reply = QMessageBox.question(
            self,
            "Remove Category",
            f"Are you sure you want to remove '{category}'?\nStamps will be moved to General category.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if not self.stamp_manager.remove_category(category):
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to remove category."
                )

    # Signal handlers
    def on_stamp_added(self, stamp_id: str, category: str):
        """Handle stamp added signal"""
        if category == self.category_combo.currentText():
            self.load_stamps(category)

    def on_stamp_removed(self, stamp_id: str):
        """Handle stamp removed signal"""
        self.load_stamps(self.category_combo.currentText())

    def on_stamp_renamed(self, stamp_id: str, new_name: str):
        """Handle stamp renamed signal"""
        self.load_stamps(self.category_combo.currentText())

    def on_category_added(self, category: str):
        """Handle category added signal"""
        self.category_combo.addItem(category)

    def on_category_removed(self, category: str):
        """Handle category removed signal"""
        index = self.category_combo.findText(category)
        if index >= 0:
            self.category_combo.removeItem(index)
            self.category_combo.setCurrentText("General")