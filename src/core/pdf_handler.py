import fitz
import os
import logging
import tempfile
import uuid
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal

from core.image_processing import bake_rotation_opacity, rotated_bounding_size
from core import word_document

logger = logging.getLogger(__name__)

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
        self.source_word_path: Optional[str] = None
        self._temp_pdf_path: Optional[str] = None
        self.last_open_error: Optional[str] = None
        self.last_saved_paths: List[str] = []
        self.word_writeback_failed: bool = False

    def open_document(self, path: str) -> bool:
        """Open a PDF or Word document (Word files convert via Word COM)"""
        try:
            self.close_document()
            self.last_open_error = None

            pdf_path = path
            if word_document.is_word_file(path):
                temp_pdf = os.path.join(
                    tempfile.gettempdir(), f"pysign_{uuid.uuid4().hex}.pdf")
                if not word_document.convert_to_pdf(path, temp_pdf):
                    self.last_open_error = (
                        'word_missing'
                        if not word_document.is_word_available()
                        else 'convert_failed')
                    self.document_loaded.emit(False)
                    return False
                self.source_word_path = path
                self._temp_pdf_path = temp_pdf
                pdf_path = temp_pdf

            self.document = fitz.open(pdf_path)
            self.current_page = 0
            self.zoom_level = 1.0
            self.annotations = []
            self.undo_stack.clear()
            self.redo_stack.clear()

            self.document_loaded.emit(True)
            self.page_changed.emit(0, len(self.document))
            return True
        except Exception:
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
        self.source_word_path = None
        self._cleanup_temp_pdf()

    def _cleanup_temp_pdf(self):
        """Remove the temp PDF created for a Word document, if any."""
        if self._temp_pdf_path and os.path.exists(self._temp_pdf_path):
            try:
                os.remove(self._temp_pdf_path)
            except OSError:
                logger.warning("Could not remove temp PDF %s",
                               self._temp_pdf_path)
        self._temp_pdf_path = None

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
            undo_action = {
                'type': 'add_annotation',
                'annotation': annotation
            }
            self.undo_stack.append(undo_action)
            self.redo_stack.clear()

            self.annotations.append(annotation)
            self.annotation_added.emit(annotation)
            return True
        except:
            return False

    def remove_annotation(self, annotation_id: int) -> bool:
        """Remove an annotation by its ID"""
        if 0 <= annotation_id < len(self.annotations):
            undo_action = {
                'type': 'remove_annotation',
                'annotation': self.annotations[annotation_id],
                'annotation_id': annotation_id
            }
            self.undo_stack.append(undo_action)
            self.redo_stack.clear()

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

    def get_signed_path(self) -> Optional[str]:
        """Get the path where the signed document would be saved"""
        if not self.document:
            return None

        # For Word-originated documents, name after the original file,
        # not the temp conversion PDF
        original_path = self.source_word_path or self.document.name
        base, _ = os.path.splitext(original_path)
        return f"{base}_signed.pdf"

    def get_annotation_placements(self) -> List[Tuple[int, Tuple[float, float, float, float], bytes]]:
        """Final (page, rect, png_bytes) per annotation, as saved to the PDF.

        Rotation/opacity are baked into the image bytes and the rect is
        expanded to the rotated bounding box — the docx write-back reuses
        this so both outputs are pixel-identical.
        """
        placements = []
        for annotation in self.annotations:
            image_data = (annotation.content.get('image_data')
                          or annotation.content.get('signature_data'))
            if not image_data:
                logger.warning(
                    "Skipping %s annotation on page %d: no image data",
                    annotation.type, annotation.page)
                continue

            rect = fitz.Rect(*annotation.rect)
            rotation = float(annotation.content.get('rotation', 0.0))
            opacity = float(annotation.content.get('opacity', 1.0))

            if rotation % 360 != 0 or opacity < 1.0:
                image_data = bake_rotation_opacity(image_data, rotation, opacity)
                if image_data is None:
                    logger.warning(
                        "Skipping %s annotation on page %d: "
                        "bake_rotation_opacity failed", annotation.type,
                        annotation.page)
                    continue
                if rotation % 360 != 0:
                    w, h = rotated_bounding_size(rect.width, rect.height, rotation)
                    cx = (rect.x0 + rect.x1) / 2
                    cy = (rect.y0 + rect.y1) / 2
                    rect = fitz.Rect(cx - w / 2, cy - h / 2,
                                     cx + w / 2, cy + h / 2)

            placements.append(
                (annotation.page, (rect.x0, rect.y0, rect.x1, rect.y1),
                 image_data))
        return placements

    def save_document(self, path: Optional[str] = None) -> bool:
        """Save the document with all annotations"""
        if not self.document:
            return False

        try:
            # If no path provided, use automatic naming
            if path is None:
                path = self.get_signed_path()
                if not path:
                    return False

            # Create a copy of the document for saving
            doc_copy = fitz.open()
            doc_copy.insert_pdf(self.document)

            # Apply all annotations (stamps and signatures are both images)
            for page_num, rect, image_data in self.get_annotation_placements():
                doc_copy[page_num].insert_image(fitz.Rect(*rect),
                                                stream=image_data)

            # Ensure path has .pdf extension
            base, ext = os.path.splitext(path)
            if not ext.lower() == '.pdf':
                path = base + '.pdf'

            # Save and verify the document
            doc_copy.save(path, garbage=3, deflate=True, clean=True)
            doc_copy.close()

            # Verify the saved file
            saved_ok = False
            if os.path.exists(path):
                try:
                    test_doc = fitz.open(path)
                    saved_ok = test_doc.is_pdf
                    test_doc.close()
                except Exception:
                    saved_ok = False
                if not saved_ok and os.path.exists(path):
                    os.remove(path)
            if not saved_ok:
                return False

            self.last_saved_paths = [path]
            self.word_writeback_failed = False

            # For Word-originated documents, also write a signed .docx copy.
            # Failure here is non-fatal: the PDF is the authoritative output.
            if self.source_word_path:
                docx_path = os.path.splitext(path)[0] + '.docx'
                placements = [
                    (page, rect[0], rect[1],
                     rect[2] - rect[0], rect[3] - rect[1], image_data)
                    for page, rect, image_data
                    in self.get_annotation_placements()
                ]
                if word_document.write_signatures_to_docx(
                        self.source_word_path, docx_path, placements):
                    self.last_saved_paths.append(docx_path)
                else:
                    self.word_writeback_failed = True

            return True
        except Exception:
            return False