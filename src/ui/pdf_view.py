from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout,
    QMenu, QMessageBox, QToolTip, QSizePolicy
)
from PyQt6.QtGui import (
    QPainter, QImage, QPixmap, QDragEnterEvent,
    QDragMoveEvent, QDropEvent, QPaintEvent, QMouseEvent,
    QContextMenuEvent, QCursor
)
from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize
from core.pdf_handler import PDFHandler, Annotation
from PIL import Image
from io import BytesIO
import fitz
import json

class PDFViewport(QWidget):
    """Widget for rendering PDF pages and handling stamps"""
    
    def __init__(self, pdf_handler: PDFHandler):
        super().__init__()
        self.pdf_handler = pdf_handler
        self.annotations = []
        self.selected_annotation = None
        self.hovered_annotation = None
        self.resize_handle = None
        self.drag_start_pos = None
        self.drag_start_rect = None
        self.image_cache = {}
        self.page_pixmap = None
        
        # Coordinates and dimensions for movement
        self.start_left = None
        self.start_top = None
        self.start_right = None
        self.start_bottom = None
        self.start_width = None
        self.start_height = None
        
        # Set size policy
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        
        # Constants
        self.HANDLE_SIZE = 8
        self.MIN_SIZE = 20

    def update_page_display(self):
        """Update the page display with current zoom"""
        if not self.pdf_handler.document:
            return
            
        try:
            page = self.pdf_handler.get_page(self.pdf_handler.current_page)
            if not page:
                return
            
            # Calculate zoom matrix
            zoom_matrix = fitz.Matrix(self.pdf_handler.zoom_level, self.pdf_handler.zoom_level)
            
            # Render page to pixmap
            pix = page.get_pixmap(matrix=zoom_matrix, alpha=True)
            
            # Convert to QImage
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGBA8888
            )
            
            # Create pixmap
            self.page_pixmap = QPixmap.fromImage(img)
            
            # Update size
            self.setMinimumSize(self.page_pixmap.size())
            
            self.update()
        except Exception as e:
            print(f"Error updating page display: {e}")

    def _scale_image(self, image_data: bytes, size: QSize) -> QImage:
        """Scale image using Pillow for better quality"""
        try:
            # Create cache key
            cache_key = (image_data, size.width(), size.height())
            
            # Check cache first
            if cache_key in self.image_cache:
                return self.image_cache[cache_key]
            
            # Open image with Pillow
            with Image.open(BytesIO(image_data)) as img:
                # Convert to RGBA if needed
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                # Resize with high quality
                img = img.resize(
                    (size.width(), size.height()),
                    Image.Resampling.LANCZOS
                )
                
                # Convert to QImage
                data = img.tobytes("raw", "RGBA")
                qimg = QImage(
                    data,
                    img.width,
                    img.height,
                    QImage.Format.Format_RGBA8888
                )
                
                # Cache the result
                self.image_cache[cache_key] = qimg
                
                return qimg
        except Exception as e:
            print(f"Error scaling image: {e}")
            return QImage()

    def paintEvent(self, event: QPaintEvent):
        """Paint the PDF page and annotations"""
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            
            # Draw white background
            painter.fillRect(event.rect(), Qt.GlobalColor.white)
            
            # Draw PDF page if available
            if self.page_pixmap:
                painter.drawPixmap(0, 0, self.page_pixmap)
            
            # Draw annotations
            for annotation in self.annotations:
                if annotation.page == self.pdf_handler.current_page:
                    # Get document space coordinates
                    doc_coords = [float(x) for x in annotation.rect]
                    
                    # Convert to viewport space
                    viewport_rect = QRectF(
                        doc_coords[0] * self.pdf_handler.zoom_level,
                        doc_coords[1] * self.pdf_handler.zoom_level,
                        (doc_coords[2] - doc_coords[0]) * self.pdf_handler.zoom_level,
                        (doc_coords[3] - doc_coords[1]) * self.pdf_handler.zoom_level
                    )
                    
                    if annotation.type == "stamp":
                        # Draw stamp image at viewport scale
                        img = self._scale_image(
                            annotation.content["image_data"],
                            QSize(
                                int(viewport_rect.width()),
                                int(viewport_rect.height())
                            )
                        )
                        painter.drawImage(viewport_rect, img)
                        
                        # Draw selection handles if selected
                        if annotation == self.selected_annotation:
                            self._draw_selection_handles(painter, viewport_rect)
        except Exception as e:
            print(f"Error in paint event: {e}")

    def _draw_selection_handles(self, painter: QPainter, viewport_rect: QRectF):
        """Draw selection handles on the stamp"""
        # Draw border in viewport space
        painter.setPen(Qt.GlobalColor.blue)
        painter.drawRect(viewport_rect)
        
        # Calculate handle size in viewport space (constant visual size)
        handle_size = self.HANDLE_SIZE
        
        # Draw corner handles
        painter.setBrush(Qt.GlobalColor.white)
        corners = [
            viewport_rect.topLeft(),
            viewport_rect.topRight(),
            viewport_rect.bottomLeft(),
            viewport_rect.bottomRight()
        ]
        
        for pos in corners:
            handle_rect = QRectF(
                pos.x() - handle_size/2,
                pos.y() - handle_size/2,
                handle_size,
                handle_size
            )
            painter.drawRect(handle_rect)

    def _get_resize_handle(self, viewport_pos: QPointF, viewport_rect: QRectF) -> str:
        """Get the resize handle at the given viewport position"""
        # Handle size is constant in viewport space
        handle_size = self.HANDLE_SIZE
        
        # Check corners in viewport space
        corners = [
            (viewport_rect.topLeft(), 'top-left'),
            (viewport_rect.topRight(), 'top-right'),
            (viewport_rect.bottomLeft(), 'bottom-left'),
            (viewport_rect.bottomRight(), 'bottom-right')
        ]
        
        for corner_pos, handle_name in corners:
            handle_rect = QRectF(
                corner_pos.x() - handle_size/2,
                corner_pos.y() - handle_size/2,
                handle_size,
                handle_size
            )
            if handle_rect.contains(viewport_pos):
                return handle_name
        return None

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            
            # Check if clicking on selected annotation's handles
            if self.selected_annotation:
                # Get document coordinates
                doc_coords = [float(x) for x in self.selected_annotation.rect]
                
                # Convert to viewport space for hit detection
                viewport_rect = QRectF(
                    doc_coords[0] * self.pdf_handler.zoom_level,
                    doc_coords[1] * self.pdf_handler.zoom_level,
                    (doc_coords[2] - doc_coords[0]) * self.pdf_handler.zoom_level,
                    (doc_coords[3] - doc_coords[1]) * self.pdf_handler.zoom_level
                )
                
                # Check for handle hit in viewport space
                handle = self._get_resize_handle(pos, viewport_rect)
                if handle:
                    self.resize_handle = handle
                    self.drag_start_pos = pos
                    
                    # Store original document space coordinates
                    self.start_left = doc_coords[0]
                    self.start_top = doc_coords[1]
                    self.start_right = doc_coords[2]
                    self.start_bottom = doc_coords[3]
                    self.start_width = doc_coords[2] - doc_coords[0]
                    self.start_height = doc_coords[3] - doc_coords[1]
                    
                    print(f"[DEBUG] Resize start - Size: {self.start_width} x {self.start_height}")
                    return
            
            # Check if clicking on any annotation
            clicked_annotation = None
            for annotation in reversed(self.annotations):
                if annotation.page == self.pdf_handler.current_page:
                    rect = QRectF(*[float(x) for x in annotation.rect])
                    if rect.contains(pos):
                        clicked_annotation = annotation
                        break
            
            self.selected_annotation = clicked_annotation
            if clicked_annotation:
                self.drag_start_pos = pos
                
                # Get the current rect coordinates in document space
                rect_coords = [float(x) / self.pdf_handler.zoom_level for x in clicked_annotation.rect]
                
                # Store original coordinates in document space
                self.start_left = rect_coords[0]
                self.start_top = rect_coords[1]
                self.start_right = rect_coords[2]
                self.start_bottom = rect_coords[3]
                
                # Calculate and store original dimensions in document space
                self.start_width = self.start_right - self.start_left
                self.start_height = self.start_bottom - self.start_top
                
                # Store original rect for drag operation in document space
                self.drag_start_rect = QRectF(
                    self.start_left,
                    self.start_top,
                    self.start_width,
                    self.start_height
                )
                
                print(f"[DEBUG] Document space coords: left={self.start_left}, top={self.start_top}")
                print(f"[DEBUG] Document space dimensions: {self.start_width} x {self.start_height}")
                
                print(f"[DEBUG] Original coords: left={self.start_left}, top={self.start_top}, right={self.start_right}, bottom={self.start_bottom}")
                print(f"[DEBUG] Original dimensions: {self.start_width} x {self.start_height}")
                print(f"[DEBUG] Click position: ({pos.x()}, {pos.y()})")
            
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move events"""
        pos = event.position()
        
        # Handle hover effects
        self._handle_hover(pos)
        
        # Handle dragging
        if event.buttons() & Qt.MouseButton.LeftButton and self.drag_start_pos and self.selected_annotation:
            if self.resize_handle:
                self._handle_resize(pos)
            else:
                self._handle_move(pos)

    def _handle_hover(self, pos: QPointF):
        """Handle hover effects"""
        hovered = None
        for annotation in reversed(self.annotations):
            if annotation.page == self.pdf_handler.current_page:
                rect = QRectF(*[float(x) for x in annotation.rect])
                if rect.contains(pos):
                    hovered = annotation
                    if "name" in annotation.content:
                        QToolTip.showText(
                            self.mapToGlobal(pos.toPoint()),
                            annotation.content["name"]
                        )
                    break
        
        if hovered != self.hovered_annotation:
            self.hovered_annotation = hovered
            if not hovered:
                QToolTip.hideText()

    def _handle_resize(self, pos: QPointF):
        """Handle resize operations"""
        try:
            # Get viewport delta
            viewport_delta = pos - self.drag_start_pos
            
            # Convert to document space
            doc_delta_x = viewport_delta.x() / self.pdf_handler.zoom_level
            doc_delta_y = viewport_delta.y() / self.pdf_handler.zoom_level
            
            # Get aspect ratio
            aspect_ratio = self.selected_annotation.content.get('aspect_ratio', 1.0)
            
            # Calculate new size in document space
            if self.resize_handle == 'bottom-right':
                new_width = self.start_width + doc_delta_x
                new_height = new_width / aspect_ratio
                new_rect = (
                    self.start_left,
                    self.start_top,
                    self.start_left + new_width,
                    self.start_top + new_height
                )
            elif self.resize_handle == 'top-left':
                new_width = self.start_width - doc_delta_x
                new_height = new_width / aspect_ratio
                new_rect = (
                    self.start_right - new_width,
                    self.start_bottom - new_height,
                    self.start_right,
                    self.start_bottom
                )
            elif self.resize_handle == 'bottom-left':
                new_width = self.start_width - doc_delta_x
                new_height = new_width / aspect_ratio
                new_rect = (
                    self.start_right - new_width,
                    self.start_top,
                    self.start_right,
                    self.start_top + new_height
                )
            elif self.resize_handle == 'top-right':
                new_width = self.start_width + doc_delta_x
                new_height = new_width / aspect_ratio
                new_rect = (
                    self.start_left,
                    self.start_bottom - new_height,
                    self.start_left + new_width,
                    self.start_bottom
                )
            
            # Ensure minimum size in document space
            min_size = self.MIN_SIZE / self.pdf_handler.zoom_level
            if new_rect[2] - new_rect[0] >= min_size and new_rect[3] - new_rect[1] >= min_size:
                print(f"[DEBUG] Resize - New size: {new_rect[2] - new_rect[0]} x {new_rect[3] - new_rect[1]}")
                self.selected_annotation.rect = new_rect
                self.update()
        except Exception as e:
            print(f"Error handling resize: {e}")

    def _handle_move(self, pos: QPointF):
        """Handle move operations"""
        try:
            # Get the movement in viewport coordinates
            viewport_delta = pos - self.drag_start_pos
            
            # Convert to document coordinates using zoom level
            doc_delta_x = viewport_delta.x() / self.pdf_handler.zoom_level
            doc_delta_y = viewport_delta.y() / self.pdf_handler.zoom_level
            
            print(f"[DEBUG] Viewport delta: ({viewport_delta.x()}, {viewport_delta.y()})")
            print(f"[DEBUG] Document delta: ({doc_delta_x}, {doc_delta_y})")
            
            # Apply movement in document coordinates
            new_rect = (
                self.start_left + doc_delta_x,
                self.start_top + doc_delta_y,
                self.start_left + doc_delta_x + self.start_width,  # Maintain exact width
                self.start_top + doc_delta_y + self.start_height   # Maintain exact height
            )
            
            print(f"[DEBUG] Moving from ({self.start_left}, {self.start_top})")
            print(f"[DEBUG] Moving to ({new_rect[0]}, {new_rect[1]})")
            print(f"[DEBUG] Width: {new_rect[2] - new_rect[0]} (original: {self.start_width})")
            print(f"[DEBUG] Height: {new_rect[3] - new_rect[1]} (original: {self.start_height})")
            
            # Update position while maintaining exact dimensions
            self.selected_annotation.rect = new_rect
            self.update()
        except Exception as e:
            print(f"Error handling move: {e}")

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release events"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.selected_annotation:
                # Get the final rect coordinates
                final_coords = [float(x) for x in self.selected_annotation.rect]
                final_width = final_coords[2] - final_coords[0]
                final_height = final_coords[3] - final_coords[1]
                
                # Compare with starting dimensions
                if self.drag_start_rect:
                    print(f"[DEBUG] Release - Final position: ({final_coords[0]}, {final_coords[1]})")
                    print(f"[DEBUG] Release - Final dimensions: {final_width} x {final_height}")
                    print(f"[DEBUG] Release - Start dimensions were: {self.drag_start_rect.width()} x {self.drag_start_rect.height()}")
                    print(f"[DEBUG] Release - Dimension changes: {final_width - self.drag_start_rect.width()} x {final_height - self.drag_start_rect.height()}")
            
            print("[DEBUG] Cleaning up movement state")
            # Clear all movement state
            self.drag_start_pos = None
            self.drag_start_rect = None
            self.resize_handle = None
            
            # Clear coordinate tracking
            self.start_left = None
            self.start_top = None
            self.start_right = None
            self.start_bottom = None
            self.start_width = None
            self.start_height = None

    def contextMenuEvent(self, event: QContextMenuEvent):
        """Handle context menu events"""
        pos = event.pos()
        
        # Find annotation under cursor
        clicked_annotation = None
        for annotation in reversed(self.annotations):
            if annotation.page == self.pdf_handler.current_page:
                rect = QRectF(*[float(x) for x in annotation.rect])
                if rect.contains(QPointF(pos)):
                    clicked_annotation = annotation
                    break
        
        if clicked_annotation:
            menu = QMenu(self)
            remove_action = menu.addAction("Remove")
            remove_action.triggered.connect(
                lambda: self._remove_annotation(clicked_annotation)
            )
            menu.exec(event.globalPos())

    def _remove_annotation(self, annotation):
        """Remove an annotation"""
        try:
            index = self.annotations.index(annotation)
            if self.pdf_handler.remove_annotation(index):
                if annotation == self.selected_annotation:
                    self.selected_annotation = None
                self.update()
        except Exception as e:
            print(f"Error removing annotation: {e}")

class PDFView(QScrollArea):
    """Scrollable container for PDF viewport"""
    
    def __init__(self, pdf_handler: PDFHandler):
        super().__init__()
        self.pdf_handler = pdf_handler
        
        # Create viewport
        self.viewport_widget = PDFViewport(pdf_handler)
        self.setWidget(self.viewport_widget)
        self.setWidgetResizable(True)
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        # Connect signals
        self.pdf_handler.document_loaded.connect(self.on_document_loaded)
        self.pdf_handler.page_changed.connect(self.on_page_changed)
        self.pdf_handler.zoom_changed.connect(self.on_zoom_changed)
        self.pdf_handler.annotation_added.connect(self.on_annotation_added)
        self.pdf_handler.annotation_removed.connect(self.on_annotation_removed)

    def on_document_loaded(self, success: bool):
        """Handle document loaded signal"""
        if success:
            self.viewport_widget.update_page_display()

    def on_page_changed(self, current: int, total: int):
        """Handle page changed signal"""
        self.viewport_widget.update_page_display()

    def on_zoom_changed(self, zoom: float):
        """Handle zoom changed signal"""
        self.viewport_widget.update_page_display()

    def on_annotation_added(self, annotation: Annotation):
        """Handle annotation added signal"""
        try:
            self.viewport_widget.annotations.append(annotation)
            self.viewport_widget.update()
        except Exception as e:
            print(f"Error adding annotation: {e}")

    def on_annotation_removed(self, annotation_id: int):
        """Handle annotation removed signal"""
        try:
            if 0 <= annotation_id < len(self.viewport_widget.annotations):
                self.viewport_widget.annotations.pop(annotation_id)
                self.viewport_widget.update()
        except Exception as e:
            print(f"Error removing annotation: {e}")

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events"""
        if event.mimeData().hasFormat("application/x-stamp"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent):
        """Handle drag move events"""
        if event.mimeData().hasFormat("application/x-stamp"):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Handle drop events"""
        try:
            if event.mimeData().hasFormat("application/x-stamp"):
                # Get stamp data
                stamp_data = event.mimeData().data("application/x-stamp")
                stamp_name = event.mimeData().text()
                
                # Create image to get dimensions
                img = QImage.fromData(bytes(stamp_data.data()))
                aspect_ratio = img.width() / img.height()
                
                # Get viewport position
                viewport_pos = self.viewport_widget.mapFrom(
                    self,
                    event.position().toPoint()
                )
                
                # Convert to document coordinates
                doc_x = viewport_pos.x() / self.viewport_widget.pdf_handler.zoom_level
                doc_y = viewport_pos.y() / self.viewport_widget.pdf_handler.zoom_level
                
                # Calculate initial size in document space
                doc_width = 100 / self.viewport_widget.pdf_handler.zoom_level
                doc_height = doc_width / aspect_ratio
                
                print(f"[DEBUG] Drop - Viewport pos: ({viewport_pos.x()}, {viewport_pos.y()})")
                print(f"[DEBUG] Drop - Document pos: ({doc_x}, {doc_y})")
                print(f"[DEBUG] Drop - Document size: {doc_width} x {doc_height}")
                
                # Create annotation with document space coordinates
                annotation = Annotation(
                    type="stamp",
                    rect=(
                        doc_x,
                        doc_y,
                        doc_x + doc_width,
                        doc_y + doc_height
                    ),
                    content={
                        "image_data": bytes(stamp_data.data()),
                        "name": stamp_name,
                        "aspect_ratio": aspect_ratio,
                        "original_width": doc_width,
                        "original_height": doc_height
                    },
                    page=self.pdf_handler.current_page
                )
                
                # Add annotation
                self.pdf_handler.add_annotation(annotation)
                event.acceptProposedAction()
        except Exception as e:
            print(f"Error handling drop event: {e}")
