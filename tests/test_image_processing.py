"""Tests for the headless stamp image-processing module."""
from io import BytesIO
from PIL import Image

from core.image_processing import remove_background, auto_trim, apply_edits, DEFAULT_EDIT_PARAMS


def make_image(pixels, size):
    """Build an RGBA image from a flat list of RGBA tuples."""
    img = Image.new('RGBA', size)
    img.putdata(pixels)
    return img


def test_remove_background_zero_tolerance_is_noop():
    img = make_image([(255, 255, 255, 255), (0, 0, 0, 255)], (2, 1))
    out = remove_background(img, 0)
    assert list(out.getdata()) == [(255, 255, 255, 255), (0, 0, 0, 255)]


def test_remove_background_clears_pure_white():
    img = make_image([(255, 255, 255, 255), (0, 0, 0, 255)], (2, 1))
    out = remove_background(img, 10)
    data = list(out.getdata())
    assert data[0][3] == 0          # white became transparent
    assert data[1] == (0, 0, 0, 255)  # black untouched


def test_remove_background_tolerance_widens_match():
    off_white = (245, 245, 240, 255)
    img = make_image([off_white], (1, 1))
    # distance from white ~20.6; tolerance 5 -> max distance 11: kept
    assert list(remove_background(img, 5).getdata())[0][3] == 255
    # tolerance 20 -> max distance 44: cleared
    assert list(remove_background(img, 20).getdata())[0][3] == 0


def test_remove_background_converts_rgb_input():
    img = Image.new('RGB', (1, 1), (255, 255, 255))
    out = remove_background(img, 10)
    assert out.mode == 'RGBA'
    assert list(out.getdata())[0][3] == 0


def test_remove_background_preserves_existing_transparency():
    img = make_image([(255, 255, 255, 0)], (1, 1))
    out = remove_background(img, 0)
    assert list(out.getdata())[0][3] == 0


def png_bytes(img):
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def make_stamp_png(size=(10, 10), mark_box=(3, 3, 7, 7)):
    """White canvas with a black rectangle at mark_box."""
    img = Image.new('RGBA', size, (255, 255, 255, 255))
    for x in range(mark_box[0], mark_box[2]):
        for y in range(mark_box[1], mark_box[3]):
            img.putpixel((x, y), (0, 0, 0, 255))
    return png_bytes(img)


def test_auto_trim_finds_content_bbox():
    img = Image.open(BytesIO(make_stamp_png()))
    assert auto_trim(img, 10) == (3, 3, 7, 7)


def test_auto_trim_all_background_returns_none():
    img = Image.new('RGBA', (5, 5), (255, 255, 255, 255))
    assert auto_trim(img, 10) is None


def test_auto_trim_zero_tolerance_uses_alpha_only():
    img = Image.new('RGBA', (5, 5), (255, 255, 255, 255))
    assert auto_trim(img, 0) == (0, 0, 5, 5)


def test_apply_edits_defaults_roundtrip():
    src = make_stamp_png()
    out = apply_edits(src, dict(DEFAULT_EDIT_PARAMS))
    assert out is not None
    assert Image.open(BytesIO(out)).size == (10, 10)


def test_apply_edits_crop():
    out = apply_edits(make_stamp_png(), {'rotation': 0, 'crop': [3, 3, 7, 7], 'bg_tolerance': 0})
    assert Image.open(BytesIO(out)).size == (4, 4)


def test_apply_edits_rotation_swaps_dimensions():
    img = Image.new('RGBA', (10, 4), (0, 0, 0, 255))
    out = apply_edits(png_bytes(img), {'rotation': 90, 'crop': None, 'bg_tolerance': 0})
    assert Image.open(BytesIO(out)).size == (4, 10)


def test_apply_edits_rotation_then_crop_order():
    # 10x4 black image rotated 90 becomes 4x10; crop [0,0,4,5] is only
    # valid in the rotated space — proves rotation happens before crop.
    img = Image.new('RGBA', (10, 4), (0, 0, 0, 255))
    out = apply_edits(png_bytes(img), {'rotation': 90, 'crop': [0, 0, 4, 5], 'bg_tolerance': 0})
    assert Image.open(BytesIO(out)).size == (4, 5)


def test_apply_edits_background_removal_applied():
    out = apply_edits(make_stamp_png(), {'rotation': 0, 'crop': None, 'bg_tolerance': 10})
    result = Image.open(BytesIO(out))
    assert result.getpixel((0, 0))[3] == 0    # white corner now transparent
    assert result.getpixel((5, 5))[3] == 255  # black mark kept


def test_apply_edits_empty_crop_returns_none():
    assert apply_edits(make_stamp_png(), {'rotation': 0, 'crop': [2, 2, 2, 8], 'bg_tolerance': 0}) is None


def test_apply_edits_corrupt_bytes_returns_none():
    assert apply_edits(b'not an image', dict(DEFAULT_EDIT_PARAMS)) is None
