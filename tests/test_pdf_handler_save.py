"""Save-path tests: build a real PDF with fitz, annotate, save, re-open."""
from io import BytesIO
import fitz
from PIL import Image

from core.pdf_handler import PDFHandler, Annotation


def red_png():
    img = Image.new('RGBA', (10, 10), (255, 0, 0, 255))
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def blank_pdf(tmp_path):
    path = tmp_path / "doc.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(str(path))
    doc.close()
    return str(path)


def make_handler(tmp_path):
    handler = PDFHandler()
    assert handler.open_document(blank_pdf(tmp_path))
    return handler


def image_count(path):
    doc = fitz.open(path)
    count = len(doc[0].get_images(full=True))
    doc.close()
    return count


def test_save_stamp_annotation(tmp_path):
    handler = make_handler(tmp_path)
    handler.add_annotation(Annotation(
        type='stamp', rect=(10, 10, 60, 60),
        content={'image_data': red_png()}, page=0))
    out = str(tmp_path / "out.pdf")
    assert handler.save_document(out)
    assert image_count(out) == 1


def test_save_signature_with_image_data_key(tmp_path):
    handler = make_handler(tmp_path)
    handler.add_annotation(Annotation(
        type='signature', rect=(10, 10, 60, 40),
        content={'image_data': red_png()}, page=0))
    out = str(tmp_path / "out.pdf")
    assert handler.save_document(out)
    assert image_count(out) == 1


def test_save_legacy_signature_data_key(tmp_path):
    handler = make_handler(tmp_path)
    handler.add_annotation(Annotation(
        type='signature', rect=(10, 10, 60, 40),
        content={'signature_data': red_png()}, page=0))
    out = str(tmp_path / "out.pdf")
    assert handler.save_document(out)
    assert image_count(out) == 1


def test_save_with_rotation_and_opacity(tmp_path):
    handler = make_handler(tmp_path)
    handler.add_annotation(Annotation(
        type='stamp', rect=(50, 50, 150, 100),
        content={'image_data': red_png(), 'rotation': 45.0, 'opacity': 0.5},
        page=0))
    out = str(tmp_path / "out.pdf")
    assert handler.save_document(out)
    assert image_count(out) == 1


def test_save_rotation_expands_rect_within_page(tmp_path):
    # A 100x50 rect rotated 90 deg has bounding box 50x100 around the
    # same center; verify the placed image rect reflects that.
    handler = make_handler(tmp_path)
    handler.add_annotation(Annotation(
        type='stamp', rect=(50, 75, 150, 125),
        content={'image_data': red_png(), 'rotation': 90.0}, page=0))
    out = str(tmp_path / "out.pdf")
    assert handler.save_document(out)
    doc = fitz.open(out)
    info = doc[0].get_image_info()[0]
    bbox = info['bbox']
    doc.close()
    assert abs((bbox[2] - bbox[0]) - 50) < 1.0   # width ~50
    assert abs((bbox[3] - bbox[1]) - 100) < 1.0  # height ~100
    assert abs((bbox[0] + bbox[2]) / 2 - 100) < 1.0  # center x preserved


import io

import pytest


@pytest.fixture
def png_bytes():
    buf = io.BytesIO()
    # Create a 4x8 (non-square) red image so rotation produces visually different content
    Image.new("RGBA", (4, 8), (255, 0, 0, 255)).save(buf, format="PNG")
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
