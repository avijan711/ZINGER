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
