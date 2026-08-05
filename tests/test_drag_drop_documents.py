"""Extension routing for drag-and-drop of documents."""

import os

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


def test_temp_docx_file_survives_after_method_returns():
    """Regression test: QTemporaryFile must outlive this method.

    An Outlook-dropped Word attachment is written to a temp .docx, which
    PDFHandler.open_document converts to a separate temp PDF and remembers
    as source_word_path. If the temp .docx is deleted (QTemporaryFile's
    default autoRemove=True) once this method returns, signing later fails
    to produce the signed .docx because source_word_path points at a
    nonexistent file.
    """
    handler = DragDropHandler(FakePDFHandler())
    assert handler._save_and_open_temp_file(b"fake docx", suffix=".docx")
    opened_path = handler.pdf_handler.opened[0]
    try:
        assert os.path.exists(opened_path)
    finally:
        if os.path.exists(opened_path):
            os.remove(opened_path)


def test_temp_pdf_file_survives_after_method_returns():
    """Same guarantee for the default .pdf suffix case."""
    handler = DragDropHandler(FakePDFHandler())
    assert handler._save_and_open_temp_file(b"%PDF fake")
    opened_path = handler.pdf_handler.opened[0]
    try:
        assert os.path.exists(opened_path)
    finally:
        if os.path.exists(opened_path):
            os.remove(opened_path)
