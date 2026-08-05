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
