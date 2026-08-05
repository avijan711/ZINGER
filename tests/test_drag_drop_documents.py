"""Extension routing for drag-and-drop of documents."""

import pytest

from ui.pdf_viewer.drag_drop_handler import (
    DragDropHandler, is_supported_document)


@pytest.mark.parametrize("filename,expected", [
    ("contract.pdf", True),
    ("contract.docx", True),
    ("contract.DOCX", True),
    ("legacy.doc", True),
    ("photo.png", False),
    ("archive.zip", False),
    ("", False),
])
def test_is_supported_document(filename, expected):
    assert is_supported_document(filename) is expected


class FakePDFHandler:
    def __init__(self):
        self.opened = []

    def open_document(self, path):
        self.opened.append(path)
        return True


def test_temp_file_preserves_docx_extension():
    handler = DragDropHandler(FakePDFHandler())
    assert handler._save_and_open_temp_file(b"fake docx", suffix=".docx")
    opened = handler.pdf_handler.opened[0]
    assert opened.lower().endswith(".docx")


def test_temp_file_default_suffix_is_pdf():
    handler = DragDropHandler(FakePDFHandler())
    assert handler._save_and_open_temp_file(b"%PDF fake")
    opened = handler.pdf_handler.opened[0]
    assert opened.lower().endswith(".pdf")
