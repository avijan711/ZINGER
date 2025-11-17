"""PDF viewport widget for displaying and interacting with PDF documents"""

from PyQt6.QtWidgets import QWidget, QSizePolicy, QMenu
from PyQt6.QtGui import (
    QPainter, QMouseEvent, QContextMenuEvent,
    QDragEnterEvent, QDragMoveEvent, QDropEvent, QImage
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QByteArray
from typing import Optional
import logging
import json

from core.pdf_handler import PDFHandler, Annotation
from .annotation_manager import AnnotationManager
from .image_cache import ImageCache
from .renderer import PDFRenderer
from .drag_drop_handler import DragDropHandler

logger = logging.getLogger(__name__)

# Constants
HANDLE_SIZE = 8
MIN_SIZE = 20

class PDFViewport(QWidget):
    """Widget for rendering PDF pages and handling annotations"""
    
    def __init__(self, pdf_handler: PDFHandler):
        super().__init__()
        
        # Initialize components
        self.pdf_handler = pdf_handler
        self.annotation_manager = AnnotationManager()
        self.image_cache = ImageCache()
        self.renderer = PDFRenderer(pdf_handler, self.image_cache)
        self.drag_drop_handler = DragDropHandler(pdf_handler)
        
        # Configure widget
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        
    def paintEvent(self, event) -> None:
        """Handle paint events"""
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            
            # Draw white background
            painter.fillRect(event.rect(), Qt.GlobalColor.white)
            
            if self.renderer.page_pixmap:
                # Draw page and border
                page_rect = QRectF(0, 0, self.renderer.page_pixmap.width(), 
                                 self.renderer.page_pixmap.height())
                painter.setPen(Qt.GlobalColor.gray)
                painter.drawRect(page_rect)
                painter.drawPixmap(0, 0, self.renderer.page_pixmap)
                
                # Draw annotations
                self.renderer.render_annotations(
                    painter,
                    self.annotation_manager.annotations,
                    self.pdf_handler.current_page,
                    self.pdf_handler.zoom_level,
                    self.annotation_manager.state.selected_annotation
                )
            else:
                self.renderer.draw_drop_zone(painter, event.rect())
                
        except Exception as e:
            logger.error(f"Error in paint event: {e}")
            
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press events"""
        try:
            if event.button() != Qt.MouseButton.LeftButton:
                return
                
            pos = event.position()
            state = self.annotation_manager.state
            
            # Check if clicking on selected annotation's handles
            if state.selected_annotation:
                doc_coords = [float(x) for x in state.selected_annotation.rect]
                viewport_rect = self._get_viewport_rect(doc_coords)
                
                # Check for handle hit
                handle = self._get_resize_handle(pos, viewport_rect)
                if handle:
                    self.annotation_manager.start_resize(pos, state.selected_annotation, handle)
                    return
            
            # Check if clicking on any annotation
            # Convert viewport coordinates to document coordinates
            doc_pos = QPointF(
                pos.x() / self.pdf_handler.zoom_level,
                pos.y() / self.pdf_handler.zoom_level
            )
            clicked_annotation = self.annotation_manager.get_annotation_at_position(
                doc_pos, self.pdf_handler.current_page
            )
            
            if clicked_annotation:
                self.annotation_manager.start_drag(pos, clicked_annotation)
            else:
                self.annotation_manager.state.selected_annotation = None
                
            self.update()
            
        except Exception as e:
            logger.error(f"Error in mouse press event: {e}")
            
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move events"""
        try:
            pos = event.position()
            state = self.annotation_manager.state

            # Handle hover effects
            # Convert viewport coordinates to document coordinates
            doc_pos = QPointF(
                pos.x() / self.pdf_handler.zoom_level,
                pos.y() / self.pdf_handler.zoom_level
            )
            hovered = self.annotation_manager.get_annotation_at_position(
                doc_pos, self.pdf_handler.current_page
            )
            if self.annotation_manager.update_hover(hovered):
                self.update()

            # Handle dragging or resizing
            if (event.buttons() & Qt.MouseButton.LeftButton and
                state.drag_start_pos and state.selected_annotation):
                if state.resize_handle:
                    self._handle_resize(pos)
                else:
                    self._handle_drag(pos)

        except Exception as e:
            logger.error(f"Error in mouse move event: {e}")
            
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release events"""
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                # Clear only drag/resize state, preserve selection
                self.annotation_manager.clear_drag_state()
                
        except Exception as e:
            logger.error(f"Error in mouse release event: {e}")
            
    def _handle_drag(self, pos: QPointF) -> None:
        """Handle drag operations"""
        try:
            state = self.annotation_manager.state
            if not state.drag_start_pos or not state.drag_start_rect:
                return
                
            # Get viewport delta
            viewport_delta = pos - state.drag_start_pos
            
            # Convert to document coordinates
            doc_delta_x = viewport_delta.x() / self.pdf_handler.zoom_level
            doc_delta_y = viewport_delta.y() / self.pdf_handler.zoom_level
            
            # Calculate new position
            orig_rect = state.drag_start_rect
            new_rect = QRectF(
                orig_rect.left() + doc_delta_x,
                orig_rect.top() + doc_delta_y,
                orig_rect.width(),
                orig_rect.height()
            )
            
            # Update annotation position
            state.selected_annotation.rect = (
                new_rect.left(),
                new_rect.top(),
                new_rect.right(),
                new_rect.bottom()
            )
            self.update()
            
        except Exception as e:
            logger.error(f"Error handling drag: {e}")
            
    def _get_viewport_rect(self, doc_coords: list) -> QRectF:
        """Convert document coordinates to viewport coordinates"""
        return QRectF(
            doc_coords[0] * self.pdf_handler.zoom_level,
            doc_coords[1] * self.pdf_handler.zoom_level,
            (doc_coords[2] - doc_coords[0]) * self.pdf_handler.zoom_level,
            (doc_coords[3] - doc_coords[1]) * self.pdf_handler.zoom_level
        )

    def _get_resize_handle(self, viewport_pos: QPointF, viewport_rect: QRectF) -> Optional[str]:
        """Get the resize handle at the given viewport position"""
        handle_size = HANDLE_SIZE

        corners = [
            (viewport_rect.topLeft(), 'top-left'),
            (viewport_rect.topRight(), 'top-right'),
            (viewport_rect.bottomLeft(), 'bottom-left'),
            (viewport_rect.bottomRight(), 'bottom-right')
        ]

        for corner_pos, handle_name in corners:
            handle_rect = QRectF(
                corner_pos.x() - handle_size / 2,
                corner_pos.y() - handle_size / 2,
                handle_size,
                handle_size
            )
            if handle_rect.contains(viewport_pos):
                return handle_name
        return None

    def _handle_resize(self, pos: QPointF) -> None:
        """Handle resize operations"""
        try:
            state = self.annotation_manager.state
            if not state.drag_start_pos or not state.drag_start_rect or not state.selected_annotation:
                return

            # Get viewport delta
            viewport_delta = pos - state.drag_start_pos

            # Convert to document space
            doc_delta_x = viewport_delta.x() / self.pdf_handler.zoom_level
            doc_delta_y = viewport_delta.y() / self.pdf_handler.zoom_level

            # Get original dimensions
            orig_rect = state.drag_start_rect
            orig_width = orig_rect.width()
            orig_height = orig_rect.height()

            # Get aspect ratio
            aspect_ratio = state.selected_annotation.content.get('aspect_ratio', 1.0)

            # Calculate new size based on handle
            if state.resize_handle == 'bottom-right':
                new_width = max(MIN_SIZE / self.pdf_handler.zoom_level, orig_width + doc_delta_x)
                new_height = new_width / aspect_ratio
                new_rect = QRectF(
                    orig_rect.left(),
                    orig_rect.top(),
                    new_width,
                    new_height
                )
            elif state.resize_handle == 'top-left':
                new_width = max(MIN_SIZE / self.pdf_handler.zoom_level, orig_width - doc_delta_x)
                new_height = new_width / aspect_ratio
                new_rect = QRectF(
                    orig_rect.right() - new_width,
                    orig_rect.bottom() - new_height,
                    new_width,
                    new_height
                )
            elif state.resize_handle == 'bottom-left':
                new_width = max(MIN_SIZE / self.pdf_handler.zoom_level, orig_width - doc_delta_x)
                new_height = new_width / aspect_ratio
                new_rect = QRectF(
                    orig_rect.right() - new_width,
                    orig_rect.top(),
                    new_width,
                    new_height
                )
            elif state.resize_handle == 'top-right':
                new_width = max(MIN_SIZE / self.pdf_handler.zoom_level, orig_width + doc_delta_x)
                new_height = new_width / aspect_ratio
                new_rect = QRectF(
                    orig_rect.left(),
                    orig_rect.bottom() - new_height,
                    new_width,
                    new_height
                )
            else:
                return

            # Update annotation with new rect
            state.selected_annotation.rect = (
                new_rect.left(),
                new_rect.top(),
                new_rect.right(),
                new_rect.bottom()
            )
            self.update()

        except Exception as e:
            logger.error(f"Error handling resize: {e}")

    def update_page_display(self) -> None:
        """Update the page display with current zoom"""
        if not self.pdf_handler.document:
            return
            
        try:
            pixmap = self.renderer.render_page(
                self.pdf_handler.current_page,
                self.pdf_handler.zoom_level
            )
            if pixmap:
                self.setMinimumSize(pixmap.size())
                self.update()
                
        except Exception as e:
            logger.error(f"Error updating page display: {e}")
            
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter events for stamps, signatures, and PDFs"""
        mime_data = event.mimeData()

        # Handle stamp and signature drops
        if mime_data.hasFormat("application/x-stamp") or mime_data.hasFormat("application/x-signature"):
            if self.pdf_handler.document:
                event.acceptProposedAction()
                return
            else:
                event.ignore()
                return

        # Delegate PDF drops to handler
        self.drag_drop_handler.handle_drag_enter(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Handle drag move events"""
        mime_data = event.mimeData()

        # Handle stamp and signature drops
        if mime_data.hasFormat("application/x-stamp") or mime_data.hasFormat("application/x-signature"):
            if self.pdf_handler.document:
                event.acceptProposedAction()
                return
            else:
                event.ignore()
                return

        # Delegate PDF drops to handler
        self.drag_drop_handler.handle_drag_enter(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop events for stamps, signatures, and PDFs"""
        try:
            mime_data = event.mimeData()

            # Handle stamp drops
            if mime_data.hasFormat("application/x-stamp"):
                self._handle_stamp_drop(event)
                return

            # Handle signature drops
            if mime_data.hasFormat("application/x-signature"):
                self._handle_signature_drop(event)
                return

            # Delegate PDF drops to handler
            if self.drag_drop_handler.handle_drop(event):
                self.update()

        except Exception as e:
            logger.error(f"Error in dropEvent: {e}")
            event.ignore()

    def _handle_stamp_drop(self, event: QDropEvent) -> None:
        """Handle stamp drop events"""
        try:
            if not self.pdf_handler.document:
                event.ignore()
                return

            mime_data = event.mimeData()
            stamp_data = mime_data.data("application/x-stamp")
            metadata_data = mime_data.data("application/x-stamp-metadata")

            if not stamp_data:
                event.ignore()
                return

            stamp_name = mime_data.text()
            stamp_bytes = bytes(stamp_data.data())

            # Parse metadata
            if metadata_data:
                metadata = json.loads(bytes(metadata_data.data()).decode('utf-8'))
                original_width = metadata.get('original_width', 100)
                original_height = metadata.get('original_height', 100)
                aspect_ratio = metadata.get('aspect_ratio', 1.0)
                color = metadata.get('color', '#000000')
            else:
                # Fallback to image dimensions if no metadata
                img = QImage.fromData(stamp_bytes)
                if img.isNull():
                    event.ignore()
                    return
                original_width = img.width()
                original_height = img.height()
                aspect_ratio = original_width / original_height if original_height > 0 else 1.0
                color = '#000000'

            # Get drop position
            pos = event.position()

            # Convert to document coordinates
            doc_x = pos.x() / self.pdf_handler.zoom_level
            doc_y = pos.y() / self.pdf_handler.zoom_level

            # Scale to a reasonable initial size (e.g. 100px width)
            target_width = 100
            scale_factor = target_width / original_width

            # Calculate size in document space
            doc_width = (original_width * scale_factor) / self.pdf_handler.zoom_level
            doc_height = (original_height * scale_factor) / self.pdf_handler.zoom_level

            # Create annotation with document space coordinates
            annotation = Annotation(
                type="stamp",
                rect=(doc_x, doc_y, doc_x + doc_width, doc_y + doc_height),
                content={
                    "image_data": stamp_bytes,
                    "name": stamp_name,
                    "aspect_ratio": float(aspect_ratio),
                    "original_width": float(original_width),
                    "original_height": float(original_height),
                    "scale_factor": float(scale_factor),
                    "color": color
                },
                page=self.pdf_handler.current_page
            )

            if self.pdf_handler.add_annotation(annotation):
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
                self.update()
            else:
                event.ignore()

        except Exception as e:
            logger.error(f"Error handling stamp drop: {e}")
            event.ignore()

    def _handle_signature_drop(self, event: QDropEvent) -> None:
        """Handle signature drop events"""
        try:
            if not self.pdf_handler.document:
                event.ignore()
                return

            mime_data = event.mimeData()
            sig_data = mime_data.data("application/x-signature")
            metadata_data = mime_data.data("application/x-signature-metadata")

            if not sig_data:
                event.ignore()
                return

            sig_name = mime_data.text()
            sig_bytes = bytes(sig_data.data())

            # Parse metadata or get from image
            if metadata_data:
                metadata = json.loads(bytes(metadata_data.data()).decode('utf-8'))
                aspect_ratio = metadata.get('aspect_ratio', 1.0)
                original_width = metadata.get('original_width', 100)
                original_height = metadata.get('original_height', 100)
            else:
                # Fallback: get dimensions from image data
                img = QImage.fromData(sig_bytes)
                if img.isNull():
                    event.ignore()
                    return
                original_width = img.width()
                original_height = img.height()
                aspect_ratio = original_width / original_height if original_height > 0 else 1.0

            # Get drop position
            pos = event.position()

            # Convert to document coordinates
            doc_x = pos.x() / self.pdf_handler.zoom_level
            doc_y = pos.y() / self.pdf_handler.zoom_level

            # Scale to a reasonable initial size (e.g. 100px width)
            target_width = 100
            scale_factor = target_width / original_width

            # Calculate size in document space
            doc_width = (original_width * scale_factor) / self.pdf_handler.zoom_level
            doc_height = (original_height * scale_factor) / self.pdf_handler.zoom_level

            # Create annotation with document space coordinates
            annotation = Annotation(
                type="signature",
                rect=(doc_x, doc_y, doc_x + doc_width, doc_y + doc_height),
                content={
                    "image_data": sig_bytes,
                    "name": sig_name,
                    "aspect_ratio": float(aspect_ratio),
                    "original_width": float(original_width),
                    "original_height": float(original_height),
                    "scale_factor": float(scale_factor)
                },
                page=self.pdf_handler.current_page
            )

            if self.pdf_handler.add_annotation(annotation):
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
                self.update()
            else:
                event.ignore()

        except Exception as e:
            logger.error(f"Error handling signature drop: {e}")
            event.ignore()
        
    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Handle context menu events"""
        try:
            pos = event.pos()
            clicked_annotation = self.annotation_manager.get_annotation_at_position(
                QPointF(pos), self.pdf_handler.current_page
            )
            
            if clicked_annotation:
                logger.debug(f"Context menu for annotation: {clicked_annotation}")
                logger.debug(f"Annotation type: {getattr(clicked_annotation, 'type', 'unknown')}")
                logger.debug(f"Annotation content: {getattr(clicked_annotation, 'content', {})}")
                
                menu = QMenu(self)
                
                # Add reset color action for stamp annotations first
                if (hasattr(clicked_annotation, 'type') and
                    clicked_annotation.type == "stamp" and
                    hasattr(clicked_annotation, 'content') and
                    'color' in clicked_annotation.content and
                    clicked_annotation.content['color'] != '#000000'):  # Only show if not already default
                    logger.debug("Adding Reset Color option to context menu")
                    reset_color_action = menu.addAction("Reset Color")
                    reset_color_action.triggered.connect(
                        lambda: self._reset_stamp_color(clicked_annotation)
                    )
                
                # Add remove action
                remove_action = menu.addAction("Remove")
                remove_action.triggered.connect(
                    lambda: self._remove_annotation(clicked_annotation)
                )
                
                menu.exec(event.globalPos())
                
        except Exception as e:
            logger.error(f"Error in context menu event: {e}")
            
    def _remove_annotation(self, annotation: Annotation) -> None:
        """Remove an annotation"""
        try:
            index = self.annotation_manager.annotations.index(annotation)
            if self.pdf_handler.remove_annotation(index):
                self.annotation_manager.remove_annotation(annotation)
                self.update()
                
        except Exception as e:
            logger.error(f"Error removing annotation: {e}")
            
    def _reset_stamp_color(self, annotation: Annotation) -> None:
        """Reset a stamp annotation's color to default black"""
        try:
            if (hasattr(annotation, 'type') and
                annotation.type == "stamp" and
                hasattr(annotation, 'content') and
                'color' in annotation.content):
                logger.debug(f"Resetting stamp color from {annotation.content['color']} to default")
                # Update to default color
                annotation.content["color"] = "#000000"
                # Clear image cache to force redraw
                self.image_cache.clear()
                # Update display
                self.update()
                logger.debug("Successfully reset stamp color to default")
        except Exception as e:
            logger.error(f"Error resetting stamp color: {e}")
            
    def _reset_stamp_color(self, annotation: Annotation) -> None:
        """Reset a stamp annotation's color to default"""
        try:
            if "color" in annotation.content:
                # Update to default color
                annotation.content["color"] = "#000000"
                # Clear image cache to force redraw
                self.image_cache.clear()
                # Update display
                self.update()
                logger.debug("Reset stamp color to default")
        except Exception as e:
            logger.error(f"Error resetting stamp color: {e}")