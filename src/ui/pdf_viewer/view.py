"""Main PDF view widget providing scrollable viewport"""

from PyQt6.QtWidgets import QScrollArea
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
import logging

from core.pdf_handler import PDFHandler, Annotation
from .viewport import PDFViewport


logger = logging.getLogger(__name__)

class PDFView(QScrollArea):
    """Scrollable container for PDF viewport"""
    
    def __init__(self, pdf_handler: PDFHandler):
        super().__init__()
        self.pdf_handler = pdf_handler
        
        # Create viewport
        self.viewport_widget = PDFViewport(pdf_handler)
        self.setWidget(self.viewport_widget)
        self.setWidgetResizable(True)
        
        # Connect signals
        self._connect_signals()
        
    def _connect_signals(self) -> None:
        """Connect all PDF handler signals"""
        self.pdf_handler.document_loaded.connect(self._on_document_loaded)
        self.pdf_handler.page_changed.connect(self._on_page_changed)
        self.pdf_handler.zoom_changed.connect(self._on_zoom_changed)
        self.pdf_handler.annotation_added.connect(self._on_annotation_added)
        self.pdf_handler.annotation_removed.connect(self._on_annotation_removed)
        
    def _on_document_loaded(self, success: bool) -> None:
        """Handle document loaded signal"""
        if success:
            self.viewport_widget.update_page_display()
            
    def _on_page_changed(self, current: int, total: int) -> None:
        """Handle page changed signal"""
        self.viewport_widget.update_page_display()
        
    def _on_zoom_changed(self, zoom: float) -> None:
        """Handle zoom changed signal"""
        self.viewport_widget.update_page_display()
        
    def _on_annotation_added(self, annotation: Annotation) -> None:
        """Handle annotation added signal"""
        try:
            self.viewport_widget.annotation_manager.add_annotation(annotation)
            self.viewport_widget.update()
        except Exception as e:
            logger.error(f"Error adding annotation: {e}")
            
    def _on_annotation_removed(self, annotation_id: int) -> None:
        """Handle annotation removed signal"""
        try:
            annotations = self.viewport_widget.annotation_manager.annotations
            if 0 <= annotation_id < len(annotations):
                annotation = annotations[annotation_id]
                self.viewport_widget.annotation_manager.remove_annotation(annotation)
                self.viewport_widget.update()
        except Exception as e:
            logger.error(f"Error removing annotation: {e}")
            
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Forward drag enter events to viewport"""
        self.viewport_widget.dragEnterEvent(event)
        
    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Forward drag move events to viewport"""
        self.viewport_widget.dragMoveEvent(event)
        
    def dropEvent(self, event: QDropEvent) -> None:
        """Forward drop events to viewport"""
        self.viewport_widget.dropEvent(event)