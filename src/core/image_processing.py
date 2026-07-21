"""Pure PIL image-processing functions for stamp editing.

No Qt imports — this module must stay headless and unit-testable.
"""
import math
from io import BytesIO
from typing import Optional, Tuple
from PIL import Image, ImageChops, ImageMath

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

    r, g, b, a = img.split()
    dist_sq = ImageMath.lambda_eval(
        lambda args: (255 - args["r"]) * (255 - args["r"])
                   + (255 - args["g"]) * (255 - args["g"])
                   + (255 - args["b"]) * (255 - args["b"]),
        r=r, g=g, b=b)
    keep = ImageMath.lambda_eval(
        lambda args: (args["d"] > args["t"]) * 255,
        d=dist_sq, t=int(max_dist_sq)).convert('L')

    result = img.copy()
    result.putalpha(ImageChops.multiply(a, keep))
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


def bake_rotation_opacity(image_bytes: bytes, rotation: float,
                          opacity: float) -> Optional[bytes]:
    """Bake clockwise rotation and opacity into PNG bytes for saving."""
    try:
        with Image.open(BytesIO(image_bytes)) as src:
            img = src.convert('RGBA')
        if opacity < 1.0:
            opacity = max(0.0, opacity)
            alpha = img.getchannel('A').point(lambda a: int(a * opacity))
            img.putalpha(alpha)
        if rotation % 360 != 0:
            img = img.rotate(-rotation, expand=True,
                             resample=Image.Resampling.BICUBIC)
        buf = BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        return None


def rotated_bounding_size(width: float, height: float,
                          rotation: float) -> Tuple[float, float]:
    """Axis-aligned bounding-box size of a rect rotated by `rotation` degrees."""
    theta = math.radians(rotation % 360)
    c, s = abs(math.cos(theta)), abs(math.sin(theta))
    return width * c + height * s, width * s + height * c
