import fitz
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal

@dataclass
class PageInfo:
    number: int
    size: Tuple[float, float]
    rotation: int

@dataclass
class Annotation:
    type: str  # 'stamp' or 'signature'
    rect: Tuple[float, float, float, float]
    content: Dict
    page: int

class PDFHandler(QObject):
    # Signals
    document_loaded = pyqtSignal(bool)
    page_changed = pyqtSignal(int, int)  # current_page, total_pages
    zoom_changed = pyqtSignal(float)
    annotation_added = pyqtSignal(Annotation)
    annotation_removed = pyqtSignal(int)  # annotation_id

    def __init__(self):
        super().__init__()
        self.document: Optional[fitz.Document] = None
        self.current_page: int = 0
        self.zoom_level: float = 1.0
        self.annotations: List[Annotation] = []
        self.undo_stack: List[Dict] = []
        self.redo_stack: List[Dict] = []

    def open_document(self, path: str) -> bool:
        """Open a PDF document and initialize it"""
        try:
            self.document = fitz.open(path)
            self.current_page = 0
            self.zoom_level = 1.0
            self.annotations = []
            self.undo_stack.clear()
            self.redo_stack.clear()
            
            # Emit signals
            self.document_loaded.emit(True)
            self.page_changed.emit(0, len(self.document))
            return True
        except Exception as e:
            print(f"Error opening document: {e}")
            self.document_loaded.emit(False)
            return False

    def close_document(self):
        """Close the current document"""
        if self.document:
            self.document.close()
            self.document = None
            self.current_page = 0
            self.annotations = []
            self.undo_stack.clear()
            self.redo_stack.clear()

    def get_page(self, page_number: int) -> Optional[fitz.Page]:
        """Get a specific page from the document"""
        if self.document and 0 <= page_number < len(self.document):
            return self.document[page_number]
        return None

    def get_page_info(self, page_number: int) -> Optional[PageInfo]:
        """Get information about a specific page"""
        page = self.get_page(page_number)
        if page:
            return PageInfo(
                number=page_number,
                size=page.rect.width_height,
                rotation=page.rotation
            )
        return None

    def navigate_to_page(self, page_number: int) -> bool:
        """Navigate to a specific page"""
        if self.document and 0 <= page_number < len(self.document):
            self.current_page = page_number
            self.page_changed.emit(page_number, len(self.document))
            return True
        return False

    def set_zoom(self, zoom_level: float) -> bool:
        """Set zoom level for document viewing"""
        if 0.1 <= zoom_level <= 5.0:
            self.zoom_level = zoom_level
            self.zoom_changed.emit(zoom_level)
            return True
        return False

    def add_annotation(self, annotation: Annotation) -> bool:
        """Add an annotation to the current page"""
        if not self.document:
            return False

        try:
            # Store the action for undo
            undo_action = {
                'type': 'add_annotation',
                'annotation': annotation
            }
            self.undo_stack.append(undo_action)
            self.redo_stack.clear()

            # Add annotation to the list
            self.annotations.append(annotation)
            self.annotation_added.emit(annotation)
            return True
        except Exception as e:
            print(f"Error adding annotation: {e}")
            return False

    def remove_annotation(self, annotation_id: int) -> bool:
        """Remove an annotation by its ID"""
        if 0 <= annotation_id < len(self.annotations):
            # Store the action for undo
            undo_action = {
                'type': 'remove_annotation',
                'annotation': self.annotations[annotation_id],
                'annotation_id': annotation_id
            }
            self.undo_stack.append(undo_action)
            self.redo_stack.clear()

            # Remove the annotation
            self.annotations.pop(annotation_id)
            self.annotation_removed.emit(annotation_id)
            return True
        return False

    def undo(self) -> bool:
        """Undo the last action"""
        if not self.undo_stack:
            return False

        action = self.undo_stack.pop()
        self.redo_stack.append(action)

        if action['type'] == 'add_annotation':
            annotation_id = self.annotations.index(action['annotation'])
            return self.remove_annotation(annotation_id)
        elif action['type'] == 'remove_annotation':
            return self.add_annotation(action['annotation'])

        return False

    def redo(self) -> bool:
        """Redo the last undone action"""
        if not self.redo_stack:
            return False

        action = self.redo_stack.pop()
        self.undo_stack.append(action)

        if action['type'] == 'add_annotation':
            return self.add_annotation(action['annotation'])
        elif action['type'] == 'remove_annotation':
            annotation_id = self.annotations.index(action['annotation'])
            return self.remove_annotation(annotation_id)

        return False

    def save_document(self, path: str) -> bool:
        """Save the document with all annotations"""
        if not self.document:
            return False

        try:
            # Create a copy of the document for saving
            doc_copy = fitz.open()
            doc_copy.insert_pdf(self.document)

            # Apply all annotations
            for annotation in self.annotations:
                page = doc_copy[annotation.page]
                if annotation.type == 'stamp':
                    # Add stamp annotation
                    rect = fitz.Rect(*annotation.rect)
                    page.insert_image(rect, stream=annotation.content['image_data'])
                elif annotation.type == 'signature':
                    # Add signature annotation
                    rect = fitz.Rect(*annotation.rect)
                    page.insert_image(rect, stream=annotation.content['signature_data'])

            # Save the document
            doc_copy.save(path)
            doc_copy.close()
            return True
        except Exception as e:
            print(f"Error saving document: {e}")
            return False