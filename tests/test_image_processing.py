"""Tests for the headless stamp image-processing module."""
import math
from io import BytesIO
from PIL import Image

from core.image_processing import remove_background, auto_trim, apply_edits, DEFAULT_EDIT_PARAMS, bake_rotation_opacity, rotated_bounding_size, render_sketch, SIGNATURE_BG_TOLERANCE


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


def test_bake_opacity_halves_alpha():
    img = Image.new('RGBA', (2, 2), (0, 0, 0, 200))
    out = bake_rotation_opacity(png_bytes(img), 0.0, 0.5)
    result = Image.open(BytesIO(out))
    assert result.getpixel((0, 0))[3] == 100


def test_bake_rotation_90_swaps_size():
    img = Image.new('RGBA', (10, 4), (0, 0, 0, 255))
    out = bake_rotation_opacity(png_bytes(img), 90.0, 1.0)
    assert Image.open(BytesIO(out)).size == (4, 10)


def test_bake_no_change_roundtrips():
    img = Image.new('RGBA', (3, 3), (10, 20, 30, 255))
    out = bake_rotation_opacity(png_bytes(img), 0.0, 1.0)
    assert Image.open(BytesIO(out)).getpixel((1, 1)) == (10, 20, 30, 255)


def test_bake_corrupt_bytes_returns_none():
    assert bake_rotation_opacity(b'garbage', 45.0, 0.5) is None


def test_rotated_bounding_size_90():
    w, h = rotated_bounding_size(10, 4, 90)
    assert math.isclose(w, 4, abs_tol=1e-9)
    assert math.isclose(h, 10, abs_tol=1e-9)


def test_rotated_bounding_size_45():
    w, h = rotated_bounding_size(10, 10, 45)
    expected = 10 * math.sqrt(2)
    assert math.isclose(w, expected, rel_tol=1e-9)
    assert math.isclose(h, expected, rel_tol=1e-9)


def test_rotated_bounding_size_0_is_identity():
    assert rotated_bounding_size(7, 3, 0) == (7, 3)


def test_apply_edits_rotation_is_clockwise():
    # Horizontal strip [red, blue]; 90 deg clockwise puts red at the TOP.
    img = Image.new('RGBA', (2, 1))
    img.putdata([(255, 0, 0, 255), (0, 0, 255, 255)])
    out = apply_edits(png_bytes(img), {'rotation': 90, 'crop': None, 'bg_tolerance': 0})
    result = Image.open(BytesIO(out))
    assert result.size == (1, 2)
    assert result.getpixel((0, 0)) == (255, 0, 0, 255)   # red on top
    assert result.getpixel((0, 1)) == (0, 0, 255, 255)   # blue below


def test_bake_rotation_is_clockwise():
    img = Image.new('RGBA', (2, 1))
    img.putdata([(255, 0, 0, 255), (0, 0, 255, 255)])
    out = bake_rotation_opacity(png_bytes(img), 90.0, 1.0)
    result = Image.open(BytesIO(out))
    assert result.size == (1, 2)
    assert result.getpixel((0, 0)) == (255, 0, 0, 255)
    assert result.getpixel((0, 1)) == (0, 0, 255, 255)


def red_sig_png(size=(8, 8)):
    """Solid red RGBA signature image (no white background)."""
    return png_bytes(Image.new('RGBA', size, (255, 0, 0, 255)))


def white_bg_sig_png(size=(10, 10)):
    """White background with a black center dot, like a signature-pad export."""
    img = Image.new('RGBA', size, (255, 255, 255, 255))
    for x in range(4, 6):
        for y in range(4, 6):
            img.putpixel((x, y), (0, 0, 0, 255))
    return png_bytes(img)


def test_render_sketch_empty_is_transparent():
    for sketch in (None, {}, {'strokes': [], 'signatures': []}):
        overlay = render_sketch((10, 10), sketch)
        assert overlay.size == (10, 10)
        assert overlay.getchannel('A').getbbox() is None


def test_render_sketch_stroke_puts_ink_on_path():
    sketch = {'strokes': [{'color': '#000000', 'width': 4,
                           'points': [[5, 10], [15, 10]]}], 'signatures': []}
    overlay = render_sketch((20, 20), sketch)
    assert overlay.getpixel((10, 10))[3] > 200   # ink on the path
    assert overlay.getpixel((0, 0))[3] == 0      # corner untouched


def test_render_sketch_respects_crop_offset():
    sketch = {'strokes': [{'color': '#000000', 'width': 4,
                           'points': [[5, 10], [15, 10]]}], 'signatures': []}
    overlay = render_sketch((20, 20), sketch, crop_offset=(5, 0))
    assert overlay.getpixel((5, 10))[3] > 200    # shifted left by 5
    assert overlay.getpixel((19, 10))[3] == 0


def test_render_sketch_single_point_renders_dot():
    sketch = {'strokes': [{'color': '#ff0000', 'width': 6,
                           'points': [[10, 10]]}], 'signatures': []}
    overlay = render_sketch((20, 20), sketch)
    px = overlay.getpixel((10, 10))
    assert px[3] > 200 and px[0] > 200


def test_render_sketch_places_signature_from_data():
    sketch = {'strokes': [], 'signatures': [
        {'data': red_sig_png(), 'file': None, 'rect': [2, 2, 8, 8]}]}
    overlay = render_sketch((10, 10), sketch)
    assert overlay.getpixel((5, 5))[0] > 200     # red ink inside rect
    assert overlay.getpixel((0, 0))[3] == 0      # outside rect empty


def test_render_sketch_signature_white_bg_removed():
    sketch = {'strokes': [], 'signatures': [
        {'data': white_bg_sig_png(), 'file': None, 'rect': [0, 0, 10, 10]}]}
    overlay = render_sketch((10, 10), sketch)
    assert overlay.getpixel((0, 0))[3] == 0      # white corner transparent
    assert overlay.getpixel((4, 4))[3] > 0       # black dot survives


def test_render_sketch_missing_file_skipped():
    sketch = {'strokes': [], 'signatures': [
        {'data': None, 'file': '/nonexistent/sig.png', 'rect': [0, 0, 5, 5]}]}
    overlay = render_sketch((10, 10), sketch)
    assert overlay.getchannel('A').getbbox() is None


def test_render_sketch_out_of_bounds_signature_clipped():
    sketch = {'strokes': [], 'signatures': [
        {'data': red_sig_png(), 'file': None, 'rect': [-4, -4, 6, 6]}]}
    overlay = render_sketch((10, 10), sketch)     # must not raise
    assert overlay.getpixel((2, 2))[3] > 0


def test_apply_edits_sketch_survives_max_bg_removal():
    # All-white stamp: bg removal at 100 erases everything; stroke ink must remain
    src = png_bytes(Image.new('RGBA', (20, 20), (255, 255, 255, 255)))
    params = {'rotation': 0, 'crop': None, 'bg_tolerance': 100,
              'sketch': {'strokes': [{'color': '#000000', 'width': 4,
                                      'points': [[5, 10], [15, 10]]}],
                         'signatures': []}}
    out = apply_edits(src, params)
    result = Image.open(BytesIO(out))
    assert result.getpixel((10, 10))[3] > 200


def test_apply_edits_sketch_coords_are_precrop():
    # Crop [5,0,20,20]; stroke at x=10 pre-crop must land at x=5 post-crop
    src = png_bytes(Image.new('RGBA', (20, 20), (0, 0, 255, 255)))
    params = {'rotation': 0, 'crop': [5, 0, 20, 20], 'bg_tolerance': 0,
              'sketch': {'strokes': [{'color': '#ff0000', 'width': 2,
                                      'points': [[10, 10], [12, 10]]}],
                         'signatures': []}}
    out = apply_edits(src, params)
    result = Image.open(BytesIO(out))
    assert result.size == (15, 20)
    assert result.getpixel((5, 10))[0] > 150     # red ink at translated x
