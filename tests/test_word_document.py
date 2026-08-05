"""Tests for the Word COM wrapper. COM itself is faked — real Word runs
are verified manually on Windows."""

import os

import pytest

from core import word_document


# --- is_word_file -----------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("contract.docx", True),
    ("contract.DOCX", True),
    ("legacy.doc", True),
    ("C:/some dir/מסמך.docx", True),
    ("report.pdf", False),
    ("archive.docx.zip", False),
    ("noext", False),
])
def test_is_word_file(path, expected):
    assert word_document.is_word_file(path) is expected


# --- graceful failure without pywin32 --------------------------------------

def test_is_word_available_false_without_com():
    # On Linux/WSL pywin32 is absent; must return False, not raise
    assert word_document.is_word_available() is False


def test_convert_to_pdf_returns_false_without_com(tmp_path):
    assert word_document.convert_to_pdf(
        str(tmp_path / "a.docx"), str(tmp_path / "a.pdf")) is False


def test_write_signatures_returns_false_without_com(tmp_path):
    assert word_document.write_signatures_to_docx(
        str(tmp_path / "a.docx"), str(tmp_path / "out.docx"),
        [(0, 10.0, 20.0, 100.0, 50.0, b"png")]) is False


# --- COM call sequence via fakes -------------------------------------------

class FakeShape:
    def __init__(self):
        self.WrapFormat = type("WF", (), {"Type": None})()
        self.props = {}

    def __setattr__(self, name, value):
        if name in ("WrapFormat", "props"):
            super().__setattr__(name, value)
        else:
            self.props[name] = value


class FakeShapes:
    def __init__(self):
        self.added = []

    def AddPicture(self, FileName, LinkToFile, SaveWithDocument, Anchor):
        assert os.path.exists(FileName)  # png temp file must exist
        shape = FakeShape()
        self.added.append({"file": FileName, "shape": shape})
        return shape


class FakeDoc:
    def __init__(self):
        self.Shapes = FakeShapes()
        self.exported = None
        self.saved_as = None
        self.closed = False

    def ExportAsFixedFormat(self, OutputFileName, ExportFormat):
        self.exported = (OutputFileName, ExportFormat)
        with open(OutputFileName, "wb") as f:
            f.write(b"%PDF-fake")

    def SaveAs2(self, path, FileFormat):
        self.saved_as = (path, FileFormat)
        with open(path, "wb") as f:
            f.write(b"PK-fake-docx")

    def Close(self, SaveChanges=0):
        self.closed = True


class FakeSelection:
    def __init__(self):
        self.gotos = []
        self.Range = object()

    def GoTo(self, What, Which, Count):
        self.gotos.append((What, Which, Count))


class FakeApp:
    def __init__(self, doc):
        self._doc = doc
        self.Selection = FakeSelection()
        self.Documents = type(
            "Docs", (), {"Open": lambda _s, *a, **k: doc})()

    def Quit(self, SaveChanges=0):
        pass


@pytest.fixture
def fake_word(monkeypatch):
    doc = FakeDoc()
    app = FakeApp(doc)

    from contextlib import contextmanager

    @contextmanager
    def fake_word_app():
        yield app

    monkeypatch.setattr(word_document, "_word_app", fake_word_app)
    return app, doc


def test_convert_to_pdf_exports_pdf(fake_word, tmp_path):
    app, doc = fake_word
    src = tmp_path / "in.docx"
    src.write_bytes(b"docx")
    out = tmp_path / "out.pdf"

    assert word_document.convert_to_pdf(str(src), str(out)) is True
    assert doc.exported[1] == word_document.WD_EXPORT_FORMAT_PDF
    assert os.path.exists(out)
    assert doc.closed is True


def test_write_signatures_places_shapes(fake_word, tmp_path):
    app, doc = fake_word
    src = tmp_path / "in.docx"
    src.write_bytes(b"docx")
    out = tmp_path / "out.docx"

    placements = [
        (0, 10.0, 20.0, 100.0, 50.0, b"png-a"),
        (2, 5.0, 7.0, 30.0, 40.0, b"png-b"),
    ]
    assert word_document.write_signatures_to_docx(
        str(src), str(out), placements) is True

    # Word pages are 1-based
    assert [g[2] for g in app.Selection.gotos] == [1, 3]

    assert len(doc.Shapes.added) == 2
    first = doc.Shapes.added[0]["shape"]
    assert first.WrapFormat.Type == word_document.WD_WRAP_NONE
    assert first.props["RelativeHorizontalPosition"] == \
        word_document.WD_REL_H_POSITION_PAGE
    assert first.props["RelativeVerticalPosition"] == \
        word_document.WD_REL_V_POSITION_PAGE
    assert first.props["Left"] == 10.0
    assert first.props["Top"] == 20.0
    assert first.props["Width"] == 100.0
    assert first.props["Height"] == 50.0

    assert doc.saved_as[1] == word_document.WD_FORMAT_DOCX
    assert doc.closed is True

    # temp PNGs must be cleaned up
    for added in doc.Shapes.added:
        assert not os.path.exists(added["file"])
