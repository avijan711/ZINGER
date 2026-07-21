"""Pure PIL image-processing functions for stamp editing.

No Qt imports — this module must stay headless and unit-testable.
"""
from io import BytesIO
from typing import Optional, Tuple
from PIL import Image

# Slider tolerance 0-100 maps linearly to a max Euclidean RGB distance
# from pure white. 100 -> distance 220 (aggressive removal).
_TOLERANCE_SCALE = 2.2

DEFAULT_EDIT_PARAMS = {'rotation': 0, 'crop': None, 'bg_tolerance': 0}


def remove_background(img: Image.Image, tolerance: int) -> Image.Image:
    """Make near-white pixels transparent.

    tolerance: 0-100 slider value; 0 only ensures RGBA mode.
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    if tolerance <= 0:
        return img

    max_dist_sq = (tolerance * _TOLERANCE_SCALE) ** 2
    out = []
    for r, g, b, a in img.getdata():
        if a > 0:
            dist_sq = (255 - r) ** 2 + (255 - g) ** 2 + (255 - b) ** 2
            if dist_sq <= max_dist_sq:
                a = 0
        out.append((r, g, b, a))
    result = Image.new('RGBA', img.size)
    result.putdata(out)
    return result
