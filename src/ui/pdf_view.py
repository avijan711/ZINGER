from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout,
    QMenu, QMessageBox, QToolTip, QSizePolicy
)
from PyQt6.QtGui import (
    QPainter, QImage, QPixmap, QDragEnterEvent,
    QDragMoveEvent, QDropEvent, QPaintEvent, QMouseEvent,
    QContextMenuEvent, QCursor, QPen, QColor, QPainterPath
)
from PyQt6.QtCore import QUrl, QTemporaryFile
from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize
from core.pdf_handler import PDFHandler, Annotation
import fitz
import json
import logging
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from .pdf_viewer.image_cache import ImageCache

# Configure logging
logger = logging.getLogger(__name__)

# Constants
HANDLE_SIZE = 8
MIN_SIZE = 20
ZOOM_RANGE = (0.1, 5.0)
DEFAULT_ZOOM = 1.0

@dataclass
class ViewportState:
    """Represents the current state of the viewport"""
    drag_start_pos: Optional[QPointF] = None
    drag_start_rect: Optional[QRectF] = None
    resize_handle: Optional[str] = None
    selected_annotation: Optional[Annotation] = None
    hovered_annotation: Optional[Annotation] = None

class AnnotationManager:
    """Manages annotation operations and state"""
    
    def __init__(self):
        self.annotations: List[Annotation] = []
        self.state = ViewportState()
        
    def add_annotation(self, annotation: Annotation) -> bool:
        """Add an annotation to the manager"""
        try:
            self.annotations.append(annotation)
            return True
        except Exception as e:
            logger.error(f"Error adding annotation: {e}")
            return False
            
    def remove_annotation(self, annotation: Annotation) -> bool:
        """Remove an annotation from the manager"""
        try:
            self.annotations.remove(annotation)
            return True
        except ValueError:
            logger.error(f"Annotation not found")
            return False
        except Exception as e:
            logger.error(f"Error removing annotation: {e}")
            return False
            
    def get_annotation_at_position(self, pos: QPointF, page: int) -> Optional[Annotation]:
        """Get annotation at the given position"""
        for annotation in reversed(self.annotations):
            if annotation.page == page:
                rect = QRectF(*[float(x) for x in annotation.rect])
                if rect.contains(pos):
                    return annotation
        return None

class PDFViewport(QWidget):
    """Widget for rendering PDF pages and handling annotations"""
    
    def __init__(self, pdf_handler: PDFHandler):
        super().__init__()
        self.pdf_handler = pdf_handler
        self.annotation_manager = AnnotationManager()
        self.image_cache = ImageCache()
        self.page_pixmap: Optional[QPixmap] = None
        
        # Configure widget
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

    def _draw_drop_zone_indicator(self, painter: QPainter, rect: QRect):
        """Draw the drop zone indicator when no document is loaded"""
        # Set up painter for drop zone
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f8f9fa"))
        
        # Draw rounded rectangle for drop zone
        drop_rect = rect.adjusted(20, 20, -20, -20)
        painter.drawRoundedRect(drop_rect, 10, 10)
        
        # Draw dashed border
        pen = QPen(QColor("#dee2e6"), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(drop_rect, 10, 10)
        
        # Draw icon
        icon_size = 64
        icon_rect = QRect(
            drop_rect.center().x() - icon_size // 2,
            drop_rect.center().y() - icon_size // 2 - 30,
            icon_size,
            icon_size
        )
        
        # Draw arrow icon
        painter.setPen(QPen(QColor("#6c757d"), 3))
        painter.setBrush(QColor("#6c757d"))
        
        # Draw arrow
        arrow_path = QPainterPath()
        arrow_path.moveTo(icon_rect.center().x(), icon_rect.top())
        arrow_path.lineTo(icon_rect.center().x(), icon_rect.bottom() - 20)
        arrow_path.moveTo(icon_rect.center().x() - 15, icon_rect.bottom() - 35)
        arrow_path.lineTo(icon_rect.center().x(), icon_rect.bottom() - 20)
        arrow_path.lineTo(icon_rect.center().x() + 15, icon_rect.bottom() - 35)
        painter.drawPath(arrow_path)
        
        # Draw text
        painter.setPen(QColor("#495057"))
        font = painter.font()
        font.setPointSize(12)
        painter.setFont(font)
        text_rect = QRect(
            drop_rect.left(),
            icon_rect.bottom() + 10,
            drop_rect.width(),
            30
        )
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "Drop PDF here")
        
        font.setPointSize(10)
        painter.setFont(font)
        subtext_rect = QRect(
            drop_rect.left(),
            text_rect.bottom(),
            drop_rect.width(),
            25
        )
        painter.drawText(subtext_rect, Qt.AlignmentFlag.AlignCenter, "or click Open to select a file")

    def paintEvent(self, event: QPaintEvent) -> None:
        """Handle paint events for the viewport"""
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            
            # Draw background
            painter.fillRect(event.rect(), Qt.GlobalColor.white)
            
            if self.page_pixmap:
                self._render_page(painter)
                self._render_annotations(painter)
            else:
                self._draw_drop_zone_indicator(painter, event.rect())
                
        except Exception as e:
            logger.error(f"Error in paint event: {e}")
            
    def _render_page(self, painter: QPainter) -> None:
        """Render the PDF page"""
        page_rect = QRectF(0, 0, self.page_pixmap.width(), self.page_pixmap.height())
        painter.setPen(Qt.GlobalColor.gray)
        painter.drawRect(page_rect)
        painter.drawPixmap(0, 0, self.page_pixmap)
        
    def _render_annotations(self, painter: QPainter) -> None:
        """Render all annotations"""
        for annotation in self.annotation_manager.annotations:
            if annotation.page == self.pdf_handler.current_page:
                self._render_annotation(painter, annotation)
                
    def _render_annotation(self, painter: QPainter, annotation: Annotation) -> None:
        """Render a single annotation"""
        try:
            # Convert coordinates
            doc_coords = [float(x) for x in annotation.rect]
            viewport_rect = QRectF(
                doc_coords[0] * self.pdf_handler.zoom_level,
                doc_coords[1] * self.pdf_handler.zoom_level,
                (doc_coords[2] - doc_coords[0]) * self.pdf_handler.zoom_level,
                (doc_coords[3] - doc_coords[1]) * self.pdf_handler.zoom_level
            )
            
            if annotation.type == "stamp":
                # Get color from annotation content
                color = annotation.content.get("color")
                logger.debug(f"Rendering stamp with color: {color}")
                
                # Get scaled and colored image
                img = self.image_cache.get_scaled_image(
                    annotation.content["image_data"],
                    max(1, int(viewport_rect.width())),
                    max(1, int(viewport_rect.height())),
                    color
                )
                
                if not img.isNull():
                    painter.drawImage(viewport_rect, img)
                
                if annotation == self.annotation_manager.state.selected_annotation:
                    self._draw_selection_handles(painter, viewport_rect)
                    
        except Exception as e:
            logger.error(f"Error rendering annotation: {e}")

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events for PDF files and stamps"""
        mime_data = event.mimeData()
        
        # Handle stamp drops first
        if mime_data.hasFormat("application/x-stamp"):
            if self.pdf_handler.document:
                event.acceptProposedAction()
                return
            else:
                event.ignore()
                return
        
        # Handle Outlook attachments
        if mime_data.hasFormat("application/x-qt-windows-mime;value=\"FileGroupDescriptorW\""):
            descriptor_data = mime_data.data("application/x-qt-windows-mime;value=\"FileGroupDescriptorW\"")
            try:
                raw_data = bytes(descriptor_data)
                if len(raw_data) >= 76:
                    filename_data = raw_data[76:]
                    null_pos = 0
                    for i in range(0, len(filename_data)-1, 2):
                        if filename_data[i] == 0 and filename_data[i+1] == 0:
                            null_pos = i
                            break
                            
                    if null_pos > 0:
                        filename = filename_data[:null_pos].decode('utf-16-le')
                        if filename.lower().endswith('.pdf'):
                            event.acceptProposedAction()
                            return
            except Exception as e:
                logger.error(f"Error reading descriptor: {e}")

        # Accept any drag that has URLs
        if mime_data.hasUrls():
            event.acceptProposedAction()
            return
            
        # Accept PDF-related MIME types
        accepted_mime_types = [
            "application/pdf",
            "application/x-pdf",
            "application/acrobat",
            "application/vnd.pdf",
            "text/pdf",
            "text/x-pdf"
        ]
        
        for mime_type in accepted_mime_types:
            if mime_data.hasFormat(mime_type):
                event.acceptProposedAction()
                return
                
        event.ignore()
    
    def dragMoveEvent(self, event: QDragMoveEvent):
        """Handle drag move events for PDF files"""
        self.dragEnterEvent(event)

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
            logger.error(f"Error updating page display: {e}")

    def _draw_selection_handles(self, painter: QPainter, viewport_rect: QRectF):
        """Draw selection handles on the stamp"""
        # Draw border in viewport space
        painter.setPen(Qt.GlobalColor.blue)
        painter.drawRect(viewport_rect)
        
        # Calculate handle size in viewport space (constant visual size)
        handle_size = HANDLE_SIZE
        
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
        handle_size = HANDLE_SIZE
        
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
                    state.resize_handle = handle
                    state.drag_start_pos = pos
                    
                    # Store exact coordinates for resize operation
                    state.drag_start_rect = QRectF(
                        doc_coords[0],
                        doc_coords[1],
                        doc_coords[2] - doc_coords[0],
                        doc_coords[3] - doc_coords[1]
                    )
                    return
            
            # Convert viewport position to document coordinates
            doc_pos = QPointF(
                pos.x() / self.pdf_handler.zoom_level,
                pos.y() / self.pdf_handler.zoom_level
            )
            
            # Check if clicking on any annotation
            clicked_annotation = self.annotation_manager.get_annotation_at_position(
                doc_pos, self.pdf_handler.current_page
            )
            
            if clicked_annotation:
                state.selected_annotation = clicked_annotation
                state.drag_start_pos = pos
                
                # Store initial rect with exact dimensions
                rect_coords = [float(x) for x in clicked_annotation.rect]
                state.drag_start_rect = QRectF(
                    rect_coords[0],
                    rect_coords[1],
                    rect_coords[2] - rect_coords[0],
                    rect_coords[3] - rect_coords[1]
                )
            else:
                state.selected_annotation = None
            
            self.update()
            
        except Exception as e:
            logger.error(f"Error in mouse press event: {e}")
            
    def _get_viewport_rect(self, doc_coords: List[float]) -> QRectF:
        """Convert document coordinates to viewport coordinates"""
        return QRectF(
            doc_coords[0] * self.pdf_handler.zoom_level,
            doc_coords[1] * self.pdf_handler.zoom_level,
            (doc_coords[2] - doc_coords[0]) * self.pdf_handler.zoom_level,
            (doc_coords[3] - doc_coords[1]) * self.pdf_handler.zoom_level
        )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move events"""
        try:
            pos = event.position()
            state = self.annotation_manager.state
            
            # Handle hover effects
            self._handle_hover(pos)
            
            # Handle dragging
            if (event.buttons() & Qt.MouseButton.LeftButton and
                state.drag_start_pos and state.selected_annotation):
                
                if state.resize_handle:
                    self._handle_resize(pos)
                else:
                    self._handle_move(pos)
                    
        except Exception as e:
            logger.error(f"Error in mouse move event: {e}")

    def _handle_hover(self, pos: QPointF) -> None:
        """Handle hover effects"""
        # Convert viewport position to document coordinates
        doc_pos = QPointF(
            pos.x() / self.pdf_handler.zoom_level,
            pos.y() / self.pdf_handler.zoom_level
        )
        
        hovered = self.annotation_manager.get_annotation_at_position(
            doc_pos, self.pdf_handler.current_page
        )
        
        state = self.annotation_manager.state
        if hovered != state.hovered_annotation:
            state.hovered_annotation = hovered
            if hovered and "name" in hovered.content:
                QToolTip.showText(
                    self.mapToGlobal(pos.toPoint()),
                    hovered.content["name"]
                )
            else:
                QToolTip.hideText()

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
                new_width = max(MIN_SIZE, orig_width + doc_delta_x)
                new_height = new_width / aspect_ratio
                new_rect = QRectF(
                    orig_rect.left(),
                    orig_rect.top(),
                    new_width,
                    new_height
                )
            elif state.resize_handle == 'top-left':
                new_width = max(MIN_SIZE, orig_width - doc_delta_x)
                new_height = new_width / aspect_ratio
                new_rect = QRectF(
                    orig_rect.right() - new_width,
                    orig_rect.bottom() - new_height,
                    new_width,
                    new_height
                )
            elif state.resize_handle == 'bottom-left':
                new_width = max(MIN_SIZE, orig_width - doc_delta_x)
                new_height = new_width / aspect_ratio
                new_rect = QRectF(
                    orig_rect.right() - new_width,
                    orig_rect.top(),
                    new_width,
                    new_height
                )
            elif state.resize_handle == 'top-right':
                new_width = max(MIN_SIZE, orig_width + doc_delta_x)
                new_height = new_width / aspect_ratio
                new_rect = QRectF(
                    orig_rect.left(),
                    orig_rect.bottom() - new_height,
                    new_width,
                    new_height
                )
            else:
                return
            
            # Check minimum size
            min_size = MIN_SIZE / self.pdf_handler.zoom_level
            if new_rect.width() >= min_size and new_rect.height() >= min_size:
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

    def _handle_move(self, pos: QPointF) -> None:
        """Handle move operations"""
        try:
            state = self.annotation_manager.state
            if not state.drag_start_pos or not state.drag_start_rect or not state.selected_annotation:
                return

            # Get viewport delta
            viewport_delta = pos - state.drag_start_pos
            
            # Convert to document coordinates
            doc_delta_x = viewport_delta.x() / self.pdf_handler.zoom_level
            doc_delta_y = viewport_delta.y() / self.pdf_handler.zoom_level
            
            # Calculate new position while maintaining dimensions
            orig_rect = state.drag_start_rect
            
            # Calculate new position
            new_left = orig_rect.left() + doc_delta_x
            new_top = orig_rect.top() + doc_delta_y
            
            # Maintain exact width and height
            new_rect = QRectF(
                new_left,
                new_top,
                orig_rect.width(),
                orig_rect.height()
            )
            
            # Update annotation position
            state.selected_annotation.rect = (
                new_rect.left(),
                new_rect.top(),
                new_rect.left() + orig_rect.width(),
                new_rect.top() + orig_rect.height()
            )
            self.update()
            
        except Exception as e:
            logger.error(f"Error handling move: {e}")

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release events"""
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                # Reset viewport state
                state = self.annotation_manager.state
                state.drag_start_pos = None
                state.drag_start_rect = None
                state.resize_handle = None
                
        except Exception as e:
            logger.error(f"Error in mouse release event: {e}")
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop events for PDF files and stamps"""
        try:
            mime_data = event.mimeData()
            
            # Handle stamp drops first
            if mime_data.hasFormat("application/x-stamp"):
                if not self.pdf_handler.document:
                    event.ignore()
                    return
                
                # Get stamp data and metadata
                stamp_data = mime_data.data("application/x-stamp")
                metadata_data = mime_data.data("application/x-stamp-metadata")
                if not stamp_data:
                    event.ignore()
                    return
                
                stamp_name = mime_data.text()
                stamp_bytes = bytes(stamp_data.data())
                
                # Parse metadata if available
                try:
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
                        aspect_ratio = original_width / original_height
                    
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
                except Exception as e:
                    logger.error(f"Error processing stamp data: {e}")
                    event.ignore()
                    return
                
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
                        "image_data": stamp_bytes,
                        "name": stamp_name,
                        "aspect_ratio": float(aspect_ratio),
                        "original_width": float(original_width),
                        "original_height": float(original_height),
                        "scale_factor": float(scale_factor),
                        "color": color if metadata_data else "#000000"  # Use metadata color or default
                    },
                    page=self.pdf_handler.current_page
                )
                
                # Add annotation
                if self.pdf_handler.add_annotation(annotation):
                    event.setDropAction(Qt.DropAction.CopyAction)
                    event.accept()
                    self.update()
                    return
                else:
                    event.ignore()
                    return
            
            # Handle Outlook attachments
            if mime_data.hasFormat("application/x-qt-windows-mime;value=\"FileGroupDescriptorW\""):
                descriptor_data = mime_data.data("application/x-qt-windows-mime;value=\"FileGroupDescriptorW\"")
                file_contents = mime_data.data("application/x-qt-windows-mime;value=\"FileContents\"")
                
                if descriptor_data and file_contents:
                    try:
                        raw_descriptor = bytes(descriptor_data)
                        raw_contents = bytes(file_contents)
                        
                        if len(raw_descriptor) >= 76:
                            filename_data = raw_descriptor[76:]
                            null_pos = 0
                            for i in range(0, len(filename_data)-1, 2):
                                if filename_data[i] == 0 and filename_data[i+1] == 0:
                                    null_pos = i
                                    break
                                    
                            if null_pos > 0:
                                filename = filename_data[:null_pos].decode('utf-16-le')
                                if filename.lower().endswith('.pdf'):
                                    temp_file = QTemporaryFile(self)
                                    if temp_file.open():
                                        temp_file.write(raw_contents)
                                        temp_file.close()
                                        if self.pdf_handler.open_document(temp_file.fileName()):
                                            event.acceptProposedAction()
                                            return
                    except Exception as e:
                        logger.error(f"Error handling Outlook attachment: {e}")
            
            # Handle file drops (for PDFs)
            if mime_data.hasUrls():
                for url in mime_data.urls():
                    if url.isLocalFile():
                        file_path = url.toLocalFile()
                        if file_path.lower().endswith('.pdf'):
                            if self.pdf_handler.open_document(file_path):
                                event.acceptProposedAction()
                                return
            
            event.ignore()
        except Exception as e:
            logger.error(f"Error in dropEvent: {e}")
            event.ignore()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Handle context menu events"""
        try:
            pos = event.pos()
            
            # Convert to document coordinates
            doc_pos = QPointF(
                pos.x() / self.pdf_handler.zoom_level,
                pos.y() / self.pdf_handler.zoom_level
            )
            
            # Find annotation under cursor
            clicked_annotation = self.annotation_manager.get_annotation_at_position(
                doc_pos, self.pdf_handler.current_page
            )
            
            if clicked_annotation:
                menu = QMenu(self)
                
                # Add reset color option for stamps
                if (clicked_annotation.type == "stamp" and
                    "color" in clicked_annotation.content and
                    clicked_annotation.content["color"] != "#000000"):
                    reset_color_action = menu.addAction("Reset Color")
                    reset_color_action.triggered.connect(
                        lambda: self._reset_stamp_color(clicked_annotation)
                    )
                    menu.addSeparator()
                
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
                if annotation == self.annotation_manager.state.selected_annotation:
                    self.annotation_manager.state.selected_annotation = None
                self.annotation_manager.remove_annotation(annotation)
                self.update()
        except Exception as e:
            logger.error(f"Error removing annotation: {e}")
            
    def _reset_stamp_color(self, annotation: Annotation) -> None:
        """Reset a stamp annotation's color to default black"""
        try:
            if annotation.type == "stamp" and "color" in annotation.content:
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

    def on_document_loaded(self, success: bool) -> None:
        """Handle document loaded signal"""
        if success:
            self.viewport_widget.update_page_display()

    def on_page_changed(self) -> None:
        """Handle page changed signal"""
        self.viewport_widget.update_page_display()

    def on_zoom_changed(self) -> None:
        """Handle zoom changed signal"""
        self.viewport_widget.update_page_display()

    def on_annotation_added(self, annotation) -> None:
        """Handle annotation added signal"""
        self.viewport_widget.annotation_manager.add_annotation(annotation)
        self.viewport_widget.update()

    def on_annotation_removed(self, index: int) -> None:
        """Handle annotation removed signal"""
        if 0 <= index < len(self.viewport_widget.annotation_manager.annotations):
            annotation = self.viewport_widget.annotation_manager.annotations[index]
            self.viewport_widget.annotation_manager.remove_annotation(annotation)
            self.viewport_widget.update()

