"""PDF viewport widget for displaying and interacting with PDF documents"""

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QPainter, QMouseEvent, QContextMenuEvent, QMenu
from PyQt6.QtCore import Qt, QPointF, QRectF
from typing import Optional
import logging

from core.pdf_handler import PDFHandler, Annotation
from .annotation_manager import AnnotationManager
from .image_cache import ImageCache
from .renderer import PDFRenderer
from .drag_drop_handler import DragDropHandler

logger = logging.getLogger(__name__)

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
            clicked_annotation = self.annotation_manager.get_annotation_at_position(
                pos, self.pdf_handler.current_page
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
            hovered = self.annotation_manager.get_annotation_at_position(
                pos, self.pdf_handler.current_page
            )
            if self.annotation_manager.update_hover(hovered):
                self.update()
            
            # Handle dragging
            if (event.buttons() & Qt.MouseButton.LeftButton and 
                state.drag_start_pos and state.selected_annotation):
                self._handle_drag(pos)
                
        except Exception as e:
            logger.error(f"Error in mouse move event: {e}")
            
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release events"""
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self.annotation_manager.clear_state()
                
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
        """Handle drag enter events"""
        self.drag_drop_handler.handle_drag_enter(event)
        
    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Handle drag move events"""
        # Use handle_drag_enter for move events as well to maintain consistency
        self.drag_drop_handler.handle_drag_enter(event)
        
    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop events"""
        if self.drag_drop_handler.handle_drop(event):
            self.update()
        
    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Handle context menu events"""
        try:
            pos = event.pos()
            clicked_annotation = self.annotation_manager.get_annotation_at_position(
                QPointF(pos), self.pdf_handler.current_page
            )
            
            if clicked_annotation:
                menu = QMenu(self)
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