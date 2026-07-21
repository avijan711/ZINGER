"""Tests for the headless stamp image-processing module."""
from io import BytesIO
from PIL import Image

from core.image_processing import remove_background


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
