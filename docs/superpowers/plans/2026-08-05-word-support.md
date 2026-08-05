# MS Word Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open, sign, save, and share Microsoft Word documents (`.docx`/`.doc`) in PySign — producing both a signed PDF and a signed `.docx` copy.

**Architecture:** A self-contained Word COM conversion layer (`src/core/word_document.py`) sits in front of the untouched PDF pipeline. Word files are converted to a temp PDF on open (Word's own layout engine, so PDF coordinates match the docx 1:1 in points); on save, the existing fitz pipeline writes the signed PDF and the same baked annotation images are written back into a `.docx` copy as floating shapes positioned relative to the page.

**Tech Stack:** PyQt6, PyMuPDF (fitz), Pillow, pywin32 (Word COM — already a dependency), pytest.

**Spec:** `docs/superpowers/specs/2026-08-05-word-support-design.md`

## Global Constraints

- All `win32com`/`pythoncom` imports MUST be lazy (inside functions), so every module stays importable and testable on Linux/WSL where pywin32 is absent.
- Coordinates are PDF points (1/72"), origin top-left of the page — identical to Word's page-relative shape coordinates. No scaling anywhere.
- Annotation pages are 0-based (fitz); Word's `GoTo` page count is 1-based (`page + 1`).
- Docx write-back failure is NON-FATAL: `save_document` still returns True if the PDF saved; the UI shows a warning, not an error.
- Word COM enum values are hardcoded module constants (no `win32com.client.constants`, which requires makepy caches).
- Output of write-back is always `.docx` (`wdFormatDocumentDefault = 16`), including for `.doc` input.
- Tests run on WSL: `pytest` from repo root (`pytest.ini` sets `pythonpath = src`). COM behavior is faked/monkeypatched; real Word runs are manual on Windows.
- No LibreOffice fallback, no docx text editing, no other Office formats.

---

### Task 1: Word COM module `word_document.py`

**Files:**
- Create: `src/core/word_document.py`
- Test: `tests/test_word_document.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces (used by Tasks 3, 6):
  - `word_document.WORD_EXTENSIONS: tuple[str, str]` = `('.docx', '.doc')`
  - `word_document.is_word_file(path: str) -> bool`
  - `word_document.is_word_available() -> bool`
  - `word_document.convert_to_pdf(word_path: str, out_pdf_path: str) -> bool`
  - `word_document.write_signatures_to_docx(word_path: str, out_docx_path: str, placements: list[tuple[int, float, float, float, float, bytes]]) -> bool` — placements are `(page_0_based, x, y, width, height, png_bytes)` in points.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_word_document.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/PySign && python -m pytest tests/test_word_document.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'core.word_document'`

- [ ] **Step 3: Implement `src/core/word_document.py`**

```python
"""Word COM automation: Word→PDF conversion and signature write-back.

Requires Microsoft Word on Windows. All win32com/pythoncom imports are
lazy so this module stays importable (and testable) on other platforms.

Coordinate contract: placements are in PDF points (1/72"), origin at the
top-left of the page. Because the PDF PySign displays was exported by
Word itself, these are exactly Word's page-relative shape coordinates.
"""

import logging
import os
import tempfile
from contextlib import contextmanager
from typing import List, Tuple

logger = logging.getLogger(__name__)

WORD_EXTENSIONS = ('.docx', '.doc')

# Word object-model enum values (hardcoded: win32com.client.constants
# requires a makepy cache that may not exist on the user's machine)
WD_EXPORT_FORMAT_PDF = 17    # WdExportFormat.wdExportFormatPDF
WD_GOTO_PAGE = 1             # WdGoToItem.wdGoToPage
WD_GOTO_ABSOLUTE = 1         # WdGoToDirection.wdGoToAbsolute
WD_REL_H_POSITION_PAGE = 1   # wdRelativeHorizontalPositionPage
WD_REL_V_POSITION_PAGE = 1   # wdRelativeVerticalPositionPage
WD_WRAP_NONE = 3             # WdWrapType.wdWrapNone (floats in front of text)
WD_FORMAT_DOCX = 16          # WdSaveFormat.wdFormatDocumentDefault (.docx)
MSO_FALSE = 0

# (page 0-based, x, y, width, height, png_bytes) in points
Placement = Tuple[int, float, float, float, float, bytes]


def is_word_file(path: str) -> bool:
    """Whether the path looks like a Word document we can open."""
    return path.lower().endswith(WORD_EXTENSIONS)


def _create_word_app():
    """Create a hidden Word.Application instance (raises on failure)."""
    import win32com.client
    app = win32com.client.Dispatch('Word.Application')
    app.Visible = False
    app.DisplayAlerts = 0
    return app


@contextmanager
def _word_app():
    """Yield a hidden Word instance, always quitting it afterwards."""
    import pythoncom
    pythoncom.CoInitialize()
    app = None
    try:
        app = _create_word_app()
        yield app
    finally:
        if app is not None:
            try:
                app.Quit(SaveChanges=0)
            except Exception:
                logger.exception("Failed to quit Word")
        pythoncom.CoUninitialize()


def is_word_available() -> bool:
    """Whether Microsoft Word can be started via COM."""
    try:
        with _word_app():
            return True
    except Exception:
        return False


def convert_to_pdf(word_path: str, out_pdf_path: str) -> bool:
    """Export a Word document to PDF using Word's own layout engine."""
    try:
        with _word_app() as app:
            doc = app.Documents.Open(os.path.abspath(word_path),
                                     ReadOnly=True)
            try:
                doc.ExportAsFixedFormat(
                    OutputFileName=os.path.abspath(out_pdf_path),
                    ExportFormat=WD_EXPORT_FORMAT_PDF)
            finally:
                doc.Close(SaveChanges=0)
        return os.path.exists(out_pdf_path)
    except Exception:
        logger.exception("Word→PDF conversion failed for %s", word_path)
        return False


def write_signatures_to_docx(word_path: str, out_docx_path: str,
                             placements: List[Placement]) -> bool:
    """Save a copy of the Word document with signature images placed on it.

    Each image becomes a floating shape anchored to its page, positioned
    relative to the page in points — matching what the user saw on the
    converted PDF.
    """
    temp_pngs = []
    try:
        with _word_app() as app:
            doc = app.Documents.Open(os.path.abspath(word_path),
                                     ReadOnly=False)
            try:
                for page, x, y, width, height, png_bytes in placements:
                    fd, png_path = tempfile.mkstemp(suffix='.png')
                    with os.fdopen(fd, 'wb') as f:
                        f.write(png_bytes)
                    temp_pngs.append(png_path)

                    # Word pages are 1-based; ours are 0-based
                    app.Selection.GoTo(What=WD_GOTO_PAGE,
                                       Which=WD_GOTO_ABSOLUTE,
                                       Count=page + 1)
                    shape = doc.Shapes.AddPicture(
                        FileName=png_path,
                        LinkToFile=False,
                        SaveWithDocument=True,
                        Anchor=app.Selection.Range)
                    shape.WrapFormat.Type = WD_WRAP_NONE
                    shape.RelativeHorizontalPosition = WD_REL_H_POSITION_PAGE
                    shape.RelativeVerticalPosition = WD_REL_V_POSITION_PAGE
                    shape.LockAspectRatio = MSO_FALSE
                    shape.Left = x
                    shape.Top = y
                    shape.Width = width
                    shape.Height = height

                doc.SaveAs2(os.path.abspath(out_docx_path),
                            FileFormat=WD_FORMAT_DOCX)
            finally:
                doc.Close(SaveChanges=0)
        return os.path.exists(out_docx_path)
    except Exception:
        logger.exception("Signature write-back failed for %s", word_path)
        return False
    finally:
        for png_path in temp_pngs:
            try:
                os.remove(png_path)
            except OSError:
                pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/PySign && python -m pytest tests/test_word_document.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `cd /mnt/c/PySign && python -m pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/core/word_document.py tests/test_word_document.py
git commit -m "feat: Word COM module for docx→PDF conversion and signature write-back"
```

---

### Task 2: Extract annotation placement helper in `PDFHandler`

**Files:**
- Modify: `src/core/pdf_handler.py` (the annotation loop inside `save_document`, currently lines ~199–229)
- Test: `tests/test_pdf_handler_save.py` (append)

**Interfaces:**
- Consumes: `bake_rotation_opacity`, `rotated_bounding_size` from `core.image_processing` (already imported in `pdf_handler.py`).
- Produces (used by Task 3): `PDFHandler.get_annotation_placements() -> List[Tuple[int, Tuple[float, float, float, float], bytes]]` — per annotation: `(page_0_based, (x0, y0, x1, y1), png_bytes)` with rotation/opacity already baked into the bytes and the rect expanded to the rotated bounding box. Exactly the images/rects the PDF save inserts.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pdf_handler_save.py` this self-contained block (it brings its own fixtures; if identically-named fixtures already exist in that file, rename these to avoid collision):

```python
import io

import fitz
import pytest
from PIL import Image

from core.pdf_handler import PDFHandler, Annotation


@pytest.fixture
def png_bytes():
    buf = io.BytesIO()
    Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def handler_with_doc(tmp_path):
    pdf_path = str(tmp_path / "blank.pdf")
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(pdf_path)
    doc.close()

    handler = PDFHandler()
    assert handler.open_document(pdf_path)
    yield handler
    handler.close_document()


class TestGetAnnotationPlacements:
    def test_plain_annotation_passes_through(self, handler_with_doc, png_bytes):
        handler = handler_with_doc
        handler.add_annotation(Annotation(
            type='stamp', rect=(10.0, 20.0, 110.0, 70.0),
            content={'image_data': png_bytes}, page=0))

        placements = handler.get_annotation_placements()

        assert len(placements) == 1
        page, rect, data = placements[0]
        assert page == 0
        assert rect == (10.0, 20.0, 110.0, 70.0)
        assert data == png_bytes  # untouched: no rotation/opacity

    def test_rotated_annotation_is_baked_and_rect_expanded(
            self, handler_with_doc, png_bytes):
        handler = handler_with_doc
        handler.add_annotation(Annotation(
            type='stamp', rect=(100.0, 100.0, 200.0, 150.0),
            content={'image_data': png_bytes, 'rotation': 90.0}, page=0))

        placements = handler.get_annotation_placements()

        page, rect, data = placements[0]
        assert data != png_bytes  # baked
        # 90°: width/height swap around the same center (150, 125)
        x0, y0, x1, y1 = rect
        assert (x0 + x1) / 2 == pytest.approx(150.0)
        assert (y0 + y1) / 2 == pytest.approx(125.0)
        assert x1 - x0 == pytest.approx(50.0)
        assert y1 - y0 == pytest.approx(100.0)

    def test_annotation_without_image_data_is_skipped(self, handler_with_doc):
        handler = handler_with_doc
        handler.add_annotation(Annotation(
            type='stamp', rect=(0, 0, 10, 10), content={}, page=0))

        assert handler.get_annotation_placements() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/PySign && python -m pytest tests/test_pdf_handler_save.py -v -k Placements`
Expected: FAIL with `AttributeError: ... has no attribute 'get_annotation_placements'`

- [ ] **Step 3: Implement the helper and refactor `save_document` to use it**

Add to `PDFHandler`:

```python
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
```

In `save_document`, replace the entire `for annotation in self.annotations:` loop (through `page.insert_image(rect, stream=image_data)`) with:

```python
            # Apply all annotations (stamps and signatures are both images)
            for page_num, rect, image_data in self.get_annotation_placements():
                doc_copy[page_num].insert_image(fitz.Rect(*rect),
                                                stream=image_data)
```

- [ ] **Step 4: Run the full suite (existing save tests must still pass)**

Run: `cd /mnt/c/PySign && python -m pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/pdf_handler.py tests/test_pdf_handler_save.py
git commit -m "refactor: extract get_annotation_placements from PDF save for reuse by docx write-back"
```

---

### Task 3: Word routing in `PDFHandler` (open/convert, signed path, save write-back, temp cleanup)

**Files:**
- Modify: `src/core/pdf_handler.py` (`__init__`, `open_document`, `close_document`, `get_signed_path`, `save_document`)
- Test: `tests/test_pdf_handler_word.py` (create)

**Interfaces:**
- Consumes: `core.word_document` (Task 1): `is_word_file`, `is_word_available`, `convert_to_pdf`, `write_signatures_to_docx`; `get_annotation_placements` (Task 2).
- Produces (used by Task 6):
  - `PDFHandler.source_word_path: Optional[str]` — original Word file path, `None` for plain PDFs.
  - `PDFHandler.last_open_error: Optional[str]` — `None`, `'word_missing'`, or `'convert_failed'` after `open_document`.
  - `PDFHandler.last_saved_paths: List[str]` — files written by the last successful `save_document` (PDF first, then docx if written).
  - `PDFHandler.word_writeback_failed: bool` — True when the PDF saved but the docx copy failed.
  - `open_document(path)` now accepts `.docx`/`.doc` paths.
  - `get_signed_path()` for Word docs returns `<original word dir/base>_signed.pdf`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pdf_handler_word.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/PySign && python -m pytest tests/test_pdf_handler_word.py -v`
Expected: FAIL (`AttributeError` on `source_word_path` / `last_open_error`, conversion not attempted so `.docx` fails to open with fitz, etc.)

- [ ] **Step 3: Implement in `pdf_handler.py`**

Add imports at the top (after the existing ones):

```python
import tempfile
import uuid

from core import word_document
```

In `__init__`, add:

```python
        self.source_word_path: Optional[str] = None
        self._temp_pdf_path: Optional[str] = None
        self.last_open_error: Optional[str] = None
        self.last_saved_paths: List[str] = []
        self.word_writeback_failed: bool = False
```

Replace `open_document` with:

```python
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
```

Replace `close_document` with:

```python
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
```

Add:

```python
    def _cleanup_temp_pdf(self):
        """Remove the temp PDF created for a Word document, if any."""
        if self._temp_pdf_path and os.path.exists(self._temp_pdf_path):
            try:
                os.remove(self._temp_pdf_path)
            except OSError:
                logger.warning("Could not remove temp PDF %s",
                               self._temp_pdf_path)
        self._temp_pdf_path = None
```

Replace `get_signed_path` with:

```python
    def get_signed_path(self) -> Optional[str]:
        """Get the path where the signed document would be saved"""
        if not self.document:
            return None

        # For Word-originated documents, name after the original file,
        # not the temp conversion PDF
        original_path = self.source_word_path or self.document.name
        base, _ = os.path.splitext(original_path)
        return f"{base}_signed.pdf"
```

In `save_document`, replace the final verification block (from `# Save and verify the document` to the end of the method) with:

```python
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
```

Note: `open_document` now calls `close_document()` first (needed so the previous temp PDF can be deleted and the old fitz document is not leaked). This also means opening a new file clears prior state even if the new open fails — acceptable and matches the signals the UI already handles.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/PySign && python -m pytest tests/test_pdf_handler_word.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `cd /mnt/c/PySign && python -m pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/core/pdf_handler.py tests/test_pdf_handler_word.py
git commit -m "feat: open Word documents via conversion; write signed docx copy on save"
```

---

### Task 4: Drag-and-drop accepts Word files

**Files:**
- Modify: `src/ui/pdf_viewer/drag_drop_handler.py`
- Test: `tests/test_drag_drop_documents.py` (create)

**Interfaces:**
- Consumes: `pdf_handler.open_document` (Task 3 — already dispatches by extension).
- Produces: module-level `SUPPORTED_DOCUMENT_EXTENSIONS = ('.pdf', '.docx', '.doc')` and `is_supported_document(filename: str) -> bool` in `drag_drop_handler.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_drag_drop_documents.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/PySign && python -m pytest tests/test_drag_drop_documents.py -v`
Expected: FAIL with `ImportError: cannot import name 'is_supported_document'`

- [ ] **Step 3: Implement in `drag_drop_handler.py`**

Add after the `PDF_MIME_TYPES` list:

```python
# Extensions the app can open (PDFs directly, Word via conversion)
SUPPORTED_DOCUMENT_EXTENSIONS = ('.pdf', '.docx', '.doc')


def is_supported_document(filename: str) -> bool:
    """Whether the filename has an extension PySign can open."""
    return filename.lower().endswith(SUPPORTED_DOCUMENT_EXTENSIONS)
```

Then replace every per-extension check:

1. `handle_drag_enter`, URL loop — replace
   `url.toLocalFile().lower().endswith('.pdf')` with
   `is_supported_document(url.toLocalFile())`.
2. `handle_drop`, Outlook branch — replace
   `filename.lower().endswith('.pdf')` with
   `is_supported_document(filename)`, and pass the extension through:

```python
            outlook_data = self._get_outlook_data(mime_data)
            if outlook_data:
                filename, file_contents = outlook_data
                if is_supported_document(filename):
                    import os
                    suffix = os.path.splitext(filename)[1].lower() or '.pdf'
                    if self._save_and_open_temp_file(file_contents,
                                                     suffix=suffix):
                        event.acceptProposedAction()
                        return True
```

   (Put `import os` at the top of the module with the other imports, not inline.)
3. `handle_drop`, URL loop — replace
   `file_path.lower().endswith('.pdf')` with
   `is_supported_document(file_path)`.
4. `_check_outlook_attachment` — replace the final
   `return filename.lower().endswith('.pdf')` with
   `return is_supported_document(filename)`.
5. `_save_and_open_temp_file` — the temp file must keep the right
   extension so `open_document` dispatches Word files to conversion:

```python
    def _save_and_open_temp_file(self, data: bytes,
                                 suffix: str = '.pdf') -> bool:
        """Save data to a temporary file (keeping its extension) and open it"""
        try:
            temp_file = QTemporaryFile(
                QDir.tempPath() + "/pysign_XXXXXX" + suffix)
            if temp_file.open():
                temp_file.write(data)
                temp_file.close()
                return self.pdf_handler.open_document(temp_file.fileName())
        except Exception as e:
            logger.error(f"Error saving temporary file: {e}")
            return False
```

   Add `QDir` to the existing `from PyQt6.QtCore import ...` import.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/PySign && python -m pytest tests/test_drag_drop_documents.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `cd /mnt/c/PySign && python -m pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/ui/pdf_viewer/drag_drop_handler.py tests/test_drag_drop_documents.py
git commit -m "feat: accept Word documents in drag-and-drop (files and Outlook attachments)"
```

---

### Task 5: Multi-attachment email sharing

**Files:**
- Modify: `src/core/share_manager.py`
- Test: `tests/test_share_manager.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces (used by Task 6): `ShareManager.share_via_email(file_paths, subject="", body="") -> bool` where `file_paths` is a `str` (backward compatible) or a `List[str]`; every path is attached to one email. `share_via_whatsapp` unchanged. The `import win32com.client` moves from module top into `_get_outlook` so the module imports on Linux.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_share_manager.py`:

```python
"""Email sharing attachment handling, with Outlook COM faked."""

from core.share_manager import ShareManager


class FakeMail:
    def __init__(self):
        self.Subject = None
        self.Body = None
        self.displayed = False
        self.Attachments = self
        self.added = []

    def Add(self, path):
        self.added.append(path)

    def Display(self, modal):
        self.displayed = True


class FakeOutlook:
    def __init__(self):
        self.mail = FakeMail()

    def CreateItem(self, item_type):
        return self.mail


def make_manager(monkeypatch):
    manager = ShareManager()
    outlook = FakeOutlook()
    monkeypatch.setattr(manager, "_get_outlook", lambda: outlook)
    return manager, outlook


def test_single_path_string_still_works(monkeypatch, tmp_path):
    manager, outlook = make_manager(monkeypatch)
    f = tmp_path / "signed.pdf"
    f.write_bytes(b"pdf")

    assert manager.share_via_email(str(f)) is True
    assert len(outlook.mail.added) == 1
    assert outlook.mail.added[0].endswith("signed.pdf")
    assert outlook.mail.displayed is True


def test_multiple_attachments(monkeypatch, tmp_path):
    manager, outlook = make_manager(monkeypatch)
    pdf = tmp_path / "signed.pdf"
    pdf.write_bytes(b"pdf")
    docx = tmp_path / "signed.docx"
    docx.write_bytes(b"docx")

    assert manager.share_via_email([str(pdf), str(docx)]) is True
    assert len(outlook.mail.added) == 2


def test_missing_file_returns_false(monkeypatch, tmp_path):
    manager, outlook = make_manager(monkeypatch)
    assert manager.share_via_email(str(tmp_path / "missing.pdf")) is False
    assert outlook.mail.added == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/PySign && python -m pytest tests/test_share_manager.py -v`
Expected: ERROR at collection with `ModuleNotFoundError: No module named 'win32com'` (the module-level import) — that failure is part of what this task fixes.

- [ ] **Step 3: Implement in `share_manager.py`**

1. Delete the module-level `import win32com.client` (line 1) and add the
   import inside `_get_outlook`:

```python
    def _get_outlook(self) -> Optional[object]:
        """Get or create Outlook application instance"""
        if self._outlook is None:
            try:
                import win32com.client
                self._outlook = win32com.client.Dispatch('Outlook.Application')
            except Exception as e:
                print(f"Error connecting to Outlook: {e}")
                return None
        return self._outlook
```

2. Update the typing import to `from typing import List, Optional, Union`.

3. Replace `share_via_email` with:

```python
    def share_via_email(self, file_paths: Union[str, List[str]],
                        subject: str = "", body: str = "") -> bool:
        """Share one or more files as attachments in a single Outlook email"""
        try:
            if isinstance(file_paths, str):
                file_paths = [file_paths]

            outlook = self._get_outlook()
            if not outlook:
                print("Outlook not available")
                return False

            for file_path in file_paths:
                if not os.path.exists(file_path):
                    print(f"File not found: {file_path}")
                    return False

            try:
                # Create new email
                mail = outlook.CreateItem(0)  # 0 = olMailItem

                # Set email properties
                mail.Subject = subject or ""
                mail.Body = body or ""

                # Add attachments
                for file_path in file_paths:
                    mail.Attachments.Add(os.path.abspath(file_path))

                # Display the email
                mail.Display(True)
            except Exception as e:
                error_msg = str(e).lower()
                if "dialog box is open" in error_msg or "תיבת הדו-שיח פתוחה" in error_msg:
                    QMessageBox.warning(
                        None,
                        "Warning",
                        "Please close any open Outlook windows and try again.\n"
                        "נא לסגור את כל החלונות הפתוחים של Outlook ולנסות שוב."
                    )
                else:
                    raise  # Re-raise other exceptions

            return True

        except Exception as e:
            print(f"Error creating email: {e}")
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/PySign && python -m pytest tests/test_share_manager.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `cd /mnt/c/PySign && python -m pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/core/share_manager.py tests/test_share_manager.py
git commit -m "feat: multi-attachment email sharing; lazy win32com import"
```

---

### Task 6: UI wiring (open dialog, wait cursor, messages, share both files)

**Files:**
- Modify: `src/config/constants.py`
- Modify: `src/ui/main_window.py` (`open_document`, `sign_document`, `share_via_email`, `share_via_whatsapp`)

**Interfaces:**
- Consumes: `SUPPORTED_DOCUMENT_FORMATS` (new constant), `word_document.is_word_file`, `PDFHandler.last_open_error` / `last_saved_paths` / `word_writeback_failed` (Task 3), `ShareManager.share_via_email(list)` (Task 5).
- Produces: user-facing behavior only; nothing consumed by later tasks.

No unit tests for this task (pure GUI wiring; the logic it calls is tested in Tasks 3 and 5). Verification is `py_compile` + full suite + the manual Windows checklist in Task 7.

- [ ] **Step 1: Add the constant**

In `src/config/constants.py`, after `SUPPORTED_PDF_FORMATS`:

```python
SUPPORTED_DOCUMENT_FORMATS = "*.pdf *.docx *.doc"
```

- [ ] **Step 2: Update `main_window.py` imports**

- Extend the existing `from config.constants import ...` line with `SUPPORTED_DOCUMENT_FORMATS`.
- Add `from core import word_document`.
- Ensure `QApplication` is importable where needed: extend the existing `from PyQt6.QtWidgets import ...` with `QApplication`, and ensure `Qt` is imported from `PyQt6.QtCore` (both may already be present — check first).

- [ ] **Step 3: Rewrite `open_document`**

```python
    def open_document(self):
        """Open a PDF or Word document"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Document",
            "",
            f"Documents ({SUPPORTED_DOCUMENT_FORMATS})"
        )
        if not file_path:
            return

        is_word = word_document.is_word_file(file_path)
        if is_word:
            self.status_bar.showMessage("Converting Word document...")
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            opened = self.pdf_handler.open_document(file_path)
        finally:
            if is_word:
                QApplication.restoreOverrideCursor()

        if not opened:
            if self.pdf_handler.last_open_error == 'word_missing':
                message = ("Microsoft Word is required to open Word "
                           "documents. Please install Microsoft Word "
                           "and try again.")
            elif is_word:
                message = "Failed to convert the Word document."
            else:
                message = "Failed to open the PDF document."
            QMessageBox.critical(self, "Error", message)
```

- [ ] **Step 4: Update `sign_document` success branch**

Inside `sign_document`, replace the success branch (`if self.pdf_handler.save_document(): ...`) with:

```python
            if self.pdf_handler.save_document():
                print("Document saved successfully")
                saved_paths = ", ".join(
                    self.pdf_handler.last_saved_paths) or signed_path
                self.status_bar.showMessage(
                    f"Document signed and saved to: {saved_paths}")
                if self.pdf_handler.word_writeback_failed:
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "The signed PDF was saved, but the signed Word "
                        "copy could not be created."
                    )
                # Update drag source with the new file (always the PDF)
                print("Updating drag source with new file")
                self.drag_source.setPDFPath(signed_path)
```

- [ ] **Step 5: Update `share_via_email` to attach both files**

In `share_via_email`, replace the inner success branch (`if self.pdf_handler.save_document(file_path): ...` down to the error dialog) with:

```python
        if file_path:
            if self.pdf_handler.save_document(file_path):
                if self.pdf_handler.word_writeback_failed:
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "The signed PDF was saved, but the signed Word "
                        "copy could not be created."
                    )
                attachments = (self.pdf_handler.last_saved_paths
                               or [file_path])
                # Share via email
                if not self.share_manager.share_via_email(
                    attachments,
                    "",  # No default subject
                    ""   # No default body
                ):
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to create email. Please check if Outlook is installed and running."
                    )
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to save the document for sharing."
                )
```

- [ ] **Step 6: Update `share_via_whatsapp` to always send the PDF**

In `share_via_whatsapp`, replace the inner success branch (`if self.pdf_handler.save_document(file_path): ...`) so the shared file is the saved PDF path (`save_document` normalizes the extension to `.pdf`, so the dialog path may differ from the actual file):

```python
        if file_path:
            if self.pdf_handler.save_document(file_path):
                pdf_path = (self.pdf_handler.last_saved_paths[0]
                            if self.pdf_handler.last_saved_paths
                            else file_path)
                # Share via WhatsApp (single file: the signed PDF)
                if not self.share_manager.share_via_whatsapp(pdf_path):
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to open WhatsApp Web. Please try again."
                    )
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to save the document for sharing."
                )
```

- [ ] **Step 7: Verify compilation and run the full suite**

Run: `cd /mnt/c/PySign && python -m py_compile src/ui/main_window.py src/config/constants.py && python -m pytest -q`
Expected: compiles; all tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/config/constants.py src/ui/main_window.py
git commit -m "feat: Word documents in open dialog, conversion feedback, share both signed files"
```

---

### Task 7: Docs, final verification, manual Windows checklist

**Files:**
- Modify: `README.md` (feature list / requirements section)

**Interfaces:** none.

- [ ] **Step 1: Update README**

Add to the features/requirements sections of `README.md` (match its existing style — read it first):

- Feature: "Sign Microsoft Word documents (.docx/.doc) — produces both a signed PDF and a signed Word copy".
- Requirement: "Microsoft Word (required only for opening Word documents)".

- [ ] **Step 2: Full suite + compile check**

Run: `cd /mnt/c/PySign && python -m pytest -q && python -m py_compile src/main.py`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document MS Word signing support"
```

- [ ] **Step 4: Manual verification on Windows (record results, do not skip)**

This half cannot run in WSL/CI. On the Windows machine (`C:\PySign`, `.venv\Scripts\python`):

1. Open a multi-page `.docx` via the file dialog → converts, renders, page count correct.
2. Drag a `.docx` from Explorer onto the viewer → opens.
3. Drag a Word attachment from Outlook onto the viewer → opens.
4. Place a stamp + a signature (one rotated, one semi-transparent) on page 2, click Sign → `<name>_signed.pdf` and `<name>_signed.docx` appear next to the original; open the docx in Word and confirm the images sit exactly where they were placed on screen.
5. Legacy `.doc` input → output copy is `.docx`.
6. Share via Email → Outlook draft has both attachments. Share Online → WhatsApp gets the PDF link.
7. Plain PDF flow unchanged (open/sign/share).
8. Rename Word temporarily unavailable is impractical — instead verify the error path by opening a corrupt/password-protected docx → clear error, app stays usable.

If placement in step 4 is off, the coordinate contract (points, page-relative, top-left origin) is the first thing to re-check.
