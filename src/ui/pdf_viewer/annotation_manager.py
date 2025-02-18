"""Manages PDF annotations and their state"""

from PyQt6.QtCore import QPointF, QRectF
from dataclasses import dataclass
from typing import Optional, List, Dict
import logging
from core.pdf_handler import Annotation

logger = logging.getLogger(__name__)

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
        
    def get_annotation_by_index(self, index: int) -> Optional[Annotation]:
        """Get annotation by its index"""
        try:
            return self.annotations[index] if 0 <= index < len(self.annotations) else None
        except Exception as e:
            logger.error(f"Error getting annotation by index: {e}")
            return None
            
    def clear_state(self) -> None:
        """Clear the viewport state"""
        self.state = ViewportState()
        
    def start_drag(self, pos: QPointF, annotation: Annotation) -> None:
        """Start dragging an annotation"""
        self.state.drag_start_pos = pos
        self.state.selected_annotation = annotation
        self.state.drag_start_rect = QRectF(*[float(x) for x in annotation.rect])
        
    def start_resize(self, pos: QPointF, annotation: Annotation, handle: str) -> None:
        """Start resizing an annotation"""
        self.state.drag_start_pos = pos
        self.state.selected_annotation = annotation
        self.state.resize_handle = handle
        self.state.drag_start_rect = QRectF(*[float(x) for x in annotation.rect])
        
    def update_hover(self, annotation: Optional[Annotation]) -> bool:
        """Update the hovered annotation state"""
        if annotation != self.state.hovered_annotation:
            self.state.hovered_annotation = annotation
            return True
        return False
        
    def get_annotations_for_page(self, page: int) -> List[Annotation]:
        """Get all annotations for a specific page"""
        return [ann for ann in self.annotations if ann.page == page]
        
    def clear_annotations(self) -> None:
        """Remove all annotations"""
        self.annotations.clear()
        self.clear_state()