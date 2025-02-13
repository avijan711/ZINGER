from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QComboBox, QFileDialog,
    QInputDialog, QMessageBox, QFrame, QGridLayout,
    QMenu
)
from PyQt6.QtGui import QPixmap, QDrag, QImage
from PyQt6.QtCore import Qt, QMimeData, QSize, QByteArray
from core.stamp_manager import StampManager
from pathlib import Path
import json
import os
class StampThumbnail(QLabel):
    def __init__(self, stamp_id: str, stamp_data: bytes, name: str, metadata: dict, gallery=None, parent=None):
        super().__init__(parent)
        self.stamp_id = stamp_id
        self.stamp_data = stamp_data
        self.stamp_name = name
        self.metadata = metadata
        self.gallery = gallery
        self.metadata = metadata
        
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
        
        # Add name label
        self.name_label = QLabel(name, self)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("background-color: rgba(255, 255, 255, 0.8);")
        self.name_label.setWordWrap(True)
        
        # Enable mouse tracking
        self.setMouseTracking(True)

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
            
            # Create drag pixmap
            pixmap = self.pixmap()
            if pixmap:
                drag.setPixmap(pixmap)
                drag.setHotSpot(event.position().toPoint() - self.rect().topLeft())
            
            # Execute drag operation
            drag.exec(Qt.DropAction.CopyAction)
    def contextMenuEvent(self, event):
        """Handle right-click context menu"""
        # Create menu
        menu = QMenu(self)
        
        # Add rename action
        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self._rename_stamp())
        
        menu.addSeparator()
        
        # Add delete action
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_stamp())
        
        # Show menu at cursor position
        menu.exec(event.globalPos())
    
    def _rename_stamp(self):
        """Handle rename action"""
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Stamp",
            "Enter new name:",
            text=self.stamp_name
        )
        
        if ok and new_name:
            if not self.gallery.stamp_manager.rename_stamp(self.stamp_id, new_name):
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to rename stamp."
                )
    
    def _delete_stamp(self):
        """Handle delete action"""
        reply = QMessageBox.question(
            self,
            "Delete Stamp",
            f"Are you sure you want to delete '{self.stamp_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if not self.gallery.stamp_manager.delete_stamp(self.stamp_id):
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to delete stamp."
                )

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
        layout = QVBoxLayout(self)
        
        # Create toolbar
        toolbar = QHBoxLayout()
        
        # Category selector
        self.category_combo = QComboBox()
        self.category_combo.addItems(self.stamp_manager.get_categories())
        self.category_combo.currentTextChanged.connect(self.load_stamps)
        toolbar.addWidget(self.category_combo)
        
        # Add category button
        add_category_btn = QPushButton("Add Category")
        add_category_btn.clicked.connect(self.add_category)
        toolbar.addWidget(add_category_btn)
        
        # Remove category button
        remove_category_btn = QPushButton("Remove Category")
        remove_category_btn.clicked.connect(self.remove_category)
        toolbar.addWidget(remove_category_btn)
        
        layout.addLayout(toolbar)
        
        # Create stamp management toolbar
        stamp_toolbar = QHBoxLayout()
        
        # Import stamp button
        import_btn = QPushButton("Import Stamp")
        import_btn.clicked.connect(self.import_stamp)
        stamp_toolbar.addWidget(import_btn)
        
        layout.addLayout(stamp_toolbar)
        
        # Create scroll area for stamps
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Create content widget for scroll area
        self.content = QWidget()
        self.grid_layout = QGridLayout(self.content)
        self.grid_layout.setSpacing(10)
        
        scroll.setWidget(self.content)
        layout.addWidget(scroll)
        
        # Set fixed width for gallery
        self.setFixedWidth(300)
        
        # Load initial stamps
        self.load_stamps(self.category_combo.currentText())

    def load_stamps(self, category: str):
        """Load stamps for the selected category"""
        # Clear existing stamps
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Load stamps from category
        stamps = self.stamp_manager.get_stamps_by_category(category)
        for i, stamp in enumerate(stamps):
            stamp_data = self.stamp_manager.get_stamp_data(stamp['id'])
            if stamp_data:
                row = i // 2  # 2 stamps per row
                col = i % 2
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
                self.grid_layout.addWidget(thumbnail, row, col)

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

    def delete_stamp(self):
        """Delete the selected stamp"""
        # Get selected stamp
        selected = None
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, StampThumbnail) and widget.underMouse():
                selected = widget
                break
        
        if selected:
            reply = QMessageBox.question(
                self,
                "Delete Stamp",
                f"Are you sure you want to delete '{selected.stamp_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                if not self.stamp_manager.delete_stamp(selected.stamp_id):
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to delete stamp."
                    )

    def rename_stamp(self):
        """Rename the selected stamp"""
        # Get selected stamp
        selected = None
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, StampThumbnail) and widget.underMouse():
                selected = widget
                break
        
        if selected:
            new_name, ok = QInputDialog.getText(
                self,
                "Rename Stamp",
                "Enter new name:",
                text=selected.stamp_name
            )
            
            if ok and new_name:
                if not self.stamp_manager.rename_stamp(selected.stamp_id, new_name):
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to rename stamp."
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