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


def auto_trim(img: Image.Image, tolerance: int) -> Optional[Tuple[int, int, int, int]]:
    """Bounding box of non-background pixels, or None if all background."""
    rgba = remove_background(img, tolerance)
    return rgba.getchannel('A').getbbox()


def apply_edits(original_bytes: bytes, params: dict) -> Optional[bytes]:
    """Apply rotation -> crop -> background removal; return PNG bytes.

    Returns None for invalid input or an empty result.
    """
    try:
        with Image.open(BytesIO(original_bytes)) as src:
            img = src.convert('RGBA')

        rotation = int(params.get('rotation', 0)) % 360
        if rotation:
            img = img.rotate(-rotation, expand=True)

        crop = params.get('crop')
        if crop:
            x0, y0, x1, y1 = (int(v) for v in crop)
            if x1 <= x0 or y1 <= y0:
                return None
            img = img.crop((x0, y0, x1, y1))

        img = remove_background(img, int(params.get('bg_tolerance', 0)))

        if img.width == 0 or img.height == 0:
            return None

        buf = BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        return None
