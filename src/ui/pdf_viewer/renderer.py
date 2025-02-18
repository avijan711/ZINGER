"""Handles rendering of PDF pages and annotations"""

from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath, QPixmap
from PyQt6.QtCore import Qt, QRectF, QRect
import fitz
from typing import Optional, List
import logging
from .image_cache import ImageCache
from .annotation_manager import AnnotationManager
from core.pdf_handler import PDFHandler, Annotation

logger = logging.getLogger(__name__)

# Constants
HANDLE_SIZE = 8
DROP_ZONE_PADDING = 20
CORNER_RADIUS = 10

class PDFRenderer:
    """Handles rendering of PDF pages and annotations"""
    
    def __init__(self, pdf_handler: PDFHandler, image_cache: ImageCache):
        self.pdf_handler = pdf_handler
        self.image_cache = image_cache
        self.page_pixmap: Optional[QPixmap] = None
        
    def render_page(self, page_number: int, zoom_level: float) -> Optional[QPixmap]:
        """Render a PDF page at the given zoom level"""
        try:
            page = self.pdf_handler.get_page(page_number)
            if not page:
                return None
                
            # Calculate zoom matrix
            zoom_matrix = fitz.Matrix(zoom_level, zoom_level)
            
            # Render page to pixmap
            pix = page.get_pixmap(matrix=zoom_matrix, alpha=True)
            
            # Convert to QPixmap
            self.page_pixmap = QPixmap.fromImage(QPixmap(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QPixmap.Format.Format_RGBA8888
            ))
            
            return self.page_pixmap
            
        except Exception as e:
            logger.error(f"Error rendering page: {e}")
            return None
            
    def render_annotations(self, painter: QPainter, annotations: List[Annotation], 
                         current_page: int, zoom_level: float, selected_annotation: Optional[Annotation]) -> None:
        """Render annotations on the current page"""
        try:
            for annotation in annotations:
                if annotation.page == current_page:
                    self._render_annotation(painter, annotation, zoom_level, 
                                         annotation == selected_annotation)
        except Exception as e:
            logger.error(f"Error rendering annotations: {e}")
            
    def _render_annotation(self, painter: QPainter, annotation: Annotation, 
                         zoom_level: float, is_selected: bool) -> None:
        """Render a single annotation"""
        try:
            # Convert coordinates
            doc_coords = [float(x) for x in annotation.rect]
            viewport_rect = QRectF(
                doc_coords[0] * zoom_level,
                doc_coords[1] * zoom_level,
                (doc_coords[2] - doc_coords[0]) * zoom_level,
                (doc_coords[3] - doc_coords[1]) * zoom_level
            )
            
            if annotation.type == "stamp":
                img = self.image_cache.get_scaled_image(
                    annotation.content["image_data"],
                    int(viewport_rect.width()),
                    int(viewport_rect.height())
                )
                painter.drawImage(viewport_rect, img)
                
                if is_selected:
                    self._draw_selection_handles(painter, viewport_rect)
                    
        except Exception as e:
            logger.error(f"Error rendering annotation: {e}")
            
    def _draw_selection_handles(self, painter: QPainter, viewport_rect: QRectF) -> None:
        """Draw selection handles on the annotation"""
        # Draw border
        painter.setPen(Qt.GlobalColor.blue)
        painter.drawRect(viewport_rect)
        
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
                pos.x() - HANDLE_SIZE/2,
                pos.y() - HANDLE_SIZE/2,
                HANDLE_SIZE,
                HANDLE_SIZE
            )
            painter.drawRect(handle_rect)
            
    def draw_drop_zone(self, painter: QPainter, rect: QRect) -> None:
        """Draw the drop zone indicator when no document is loaded"""
        # Set up painter for drop zone
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f8f9fa"))
        
        # Draw rounded rectangle
        drop_rect = rect.adjusted(DROP_ZONE_PADDING, DROP_ZONE_PADDING, 
                                -DROP_ZONE_PADDING, -DROP_ZONE_PADDING)
        painter.drawRoundedRect(drop_rect, CORNER_RADIUS, CORNER_RADIUS)
        
        # Draw dashed border
        pen = QPen(QColor("#dee2e6"), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(drop_rect, CORNER_RADIUS, CORNER_RADIUS)
        
        self._draw_drop_zone_content(painter, drop_rect)
        
    def _draw_drop_zone_content(self, painter: QPainter, drop_rect: QRect) -> None:
        """Draw the content of the drop zone (icon and text)"""
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
        painter.drawText(subtext_rect, Qt.AlignmentFlag.AlignCenter, 
                        "or click Open to select a file")