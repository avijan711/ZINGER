"""Word-document routing in PDFHandler, with word_document COM mocked."""

import io
import os

import fitz
import pytest
from PIL import Image

from core import word_document
from core.pdf_handler import PDFHandler, Annotation


def _make_png():
    buf = io.BytesIO()
    Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


PNG_1PX = _make_png()


@pytest.fixture
def fake_convert(monkeypatch):
    """convert_to_pdf writes a real one-page PDF so fitz can open it."""
    calls = []

    def convert(word_path, out_pdf_path):
        calls.append((word_path, out_pdf_path))
        doc = fitz.open()
        doc.new_page(width=595, height=842)
        doc.save(out_pdf_path)
        doc.close()
        return True

    monkeypatch.setattr(word_document, "convert_to_pdf", convert)
    return calls


@pytest.fixture
def docx_file(tmp_path):
    path = tmp_path / "contract.docx"
    path.write_bytes(b"fake docx")
    return str(path)


class TestOpenWordDocument:
    def test_opens_via_conversion(self, fake_convert, docx_file):
        handler = PDFHandler()
        assert handler.open_document(docx_file) is True
        assert handler.document is not None
        assert handler.source_word_path == docx_file
        assert handler.last_open_error is None
        assert fake_convert[0][0] == docx_file
        handler.close_document()

    def test_pdf_open_leaves_word_state_unset(self, tmp_path):
        pdf_path = str(tmp_path / "plain.pdf")
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        handler = PDFHandler()
        assert handler.open_document(pdf_path) is True
        assert handler.source_word_path is None
        handler.close_document()

    def test_convert_failure_sets_error(self, monkeypatch, docx_file):
        monkeypatch.setattr(word_document, "convert_to_pdf",
                            lambda *a: False)
        monkeypatch.setattr(word_document, "is_word_available",
                            lambda: True)
        handler = PDFHandler()
        assert handler.open_document(docx_file) is False
        assert handler.last_open_error == 'convert_failed'

    def test_word_missing_sets_error(self, monkeypatch, docx_file):
        monkeypatch.setattr(word_document, "convert_to_pdf",
                            lambda *a: False)
        monkeypatch.setattr(word_document, "is_word_available",
                            lambda: False)
        handler = PDFHandler()
        assert handler.open_document(docx_file) is False
        assert handler.last_open_error == 'word_missing'

    def test_close_removes_temp_pdf(self, fake_convert, docx_file):
        handler = PDFHandler()
        handler.open_document(docx_file)
        temp_pdf = handler.document.name
        assert os.path.exists(temp_pdf)
        handler.close_document()
        assert not os.path.exists(temp_pdf)
        assert handler.source_word_path is None


class TestSignedPathForWord:
    def test_uses_original_word_location(self, fake_convert, docx_file):
        handler = PDFHandler()
        handler.open_document(docx_file)
        base = os.path.splitext(docx_file)[0]
        assert handler.get_signed_path() == f"{base}_signed.pdf"
        handler.close_document()


class TestSaveWithWriteback:
    def _open_with_annotation(self, docx_file):
        handler = PDFHandler()
        handler.open_document(docx_file)
        handler.add_annotation(Annotation(
            type='stamp', rect=(10.0, 20.0, 110.0, 70.0),
            content={'image_data': PNG_1PX}, page=0))
        return handler

    def test_save_writes_pdf_and_docx(self, fake_convert, docx_file,
                                      monkeypatch, tmp_path):
        writeback_calls = []

        def fake_writeback(word_path, out_docx_path, placements):
            writeback_calls.append((word_path, out_docx_path, placements))
            return True

        monkeypatch.setattr(word_document, "write_signatures_to_docx",
                            fake_writeback)
        handler = self._open_with_annotation(docx_file)
        out_pdf = str(tmp_path / "contract_signed.pdf")

        assert handler.save_document(out_pdf) is True

        word_path, out_docx_path, placements = writeback_calls[0]
        assert word_path == docx_file
        assert out_docx_path == str(tmp_path / "contract_signed.docx")
        # (page, x, y, width, height, png_bytes)
        assert placements == [(0, 10.0, 20.0, 100.0, 50.0, PNG_1PX)]
        assert handler.last_saved_paths == [out_pdf, out_docx_path]
        assert handler.word_writeback_failed is False
        handler.close_document()

    def test_writeback_failure_is_nonfatal(self, fake_convert, docx_file,
                                           monkeypatch, tmp_path):
        monkeypatch.setattr(word_document, "write_signatures_to_docx",
                            lambda *a: False)
        handler = self._open_with_annotation(docx_file)
        out_pdf = str(tmp_path / "contract_signed.pdf")

        assert handler.save_document(out_pdf) is True  # PDF still saved
        assert os.path.exists(out_pdf)
        assert handler.last_saved_paths == [out_pdf]
        assert handler.word_writeback_failed is True
        handler.close_document()

    def test_plain_pdf_save_never_calls_writeback(self, monkeypatch,
                                                  tmp_path):
        def boom(*a):
            raise AssertionError("write-back must not run for plain PDFs")

        monkeypatch.setattr(word_document, "write_signatures_to_docx", boom)
        pdf_path = str(tmp_path / "plain.pdf")
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        handler = PDFHandler()
        handler.open_document(pdf_path)
        out = str(tmp_path / "plain_signed.pdf")
        assert handler.save_document(out) is True
        assert handler.last_saved_paths == [out]
        handler.close_document()
