"""Pure PIL image-processing functions for stamp editing.

No Qt imports — this module must stay headless and unit-testable.
"""
import math
from io import BytesIO
from typing import Optional, Tuple
from PIL import Image, ImageChops, ImageMath, ImageDraw

# Slider tolerance 0-100 maps linearly to a max Euclidean RGB distance
# from pure white. 100 -> distance 220 (aggressive removal).
_TOLERANCE_SCALE = 2.2

DEFAULT_EDIT_PARAMS = {'rotation': 0, 'crop': None, 'bg_tolerance': 0, 'sketch': None}

SIGNATURE_BG_TOLERANCE = 12


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


def _load_signature_image(entry: dict) -> Optional[Image.Image]:
    """Load a placed signature from its transient bytes or stored file."""
    try:
        data = entry.get('data')
        if data:
            return Image.open(BytesIO(data)).convert('RGBA')
        file = entry.get('file')
        if file:
            with Image.open(file) as img:
                return img.convert('RGBA')
    except Exception:
        pass
    return None


def _paste_clipped(canvas: Image.Image, img: Image.Image,
                   dest_x: int, dest_y: int) -> None:
    """Alpha-composite img onto canvas at (dest_x, dest_y), clipping to bounds."""
    x0, y0 = max(0, dest_x), max(0, dest_y)
    x1 = min(canvas.width, dest_x + img.width)
    y1 = min(canvas.height, dest_y + img.height)
    if x1 <= x0 or y1 <= y0:
        return
    region = img.crop((x0 - dest_x, y0 - dest_y, x1 - dest_x, y1 - dest_y))
    canvas.alpha_composite(region, (x0, y0))


def render_sketch(size, sketch, crop_offset=(0, 0), supersample=2):
    """Render a sketch overlay (strokes + placed signatures) as an RGBA image.

    size: (width, height) of the target canvas.
    sketch coordinates are in the rotated pre-crop space; crop_offset is the
    crop origin used to translate them into the canvas space.
    """
    width, height = int(size[0]), int(size[1])
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    if not sketch:
        return overlay
    ox, oy = crop_offset
    ss = max(1, int(supersample))

    strokes = sketch.get('strokes') or []
    if strokes:
        layer = Image.new('RGBA', (width * ss, height * ss), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for stroke in strokes:
            color = stroke.get('color', '#000000')
            w = max(1, int(stroke.get('width', 4)) * ss)
            pts = [((x - ox) * ss, (y - oy) * ss)
                   for x, y in (stroke.get('points') or [])]
            if len(pts) == 1:
                pts = pts * 2
            if len(pts) < 2:
                continue
            draw.line(pts, fill=color, width=w, joint='curve')
            r = w / 2
            for px, py in (pts[0], pts[-1]):
                draw.ellipse([px - r, py - r, px + r, py + r], fill=color)
        overlay = layer.resize((width, height), Image.Resampling.LANCZOS)

    for entry in sketch.get('signatures') or []:
        sig = _load_signature_image(entry)
        if sig is None:
            continue
        x0, y0, x1, y1 = [int(v) for v in entry['rect']]
        x0, y0, x1, y1 = x0 - int(ox), y0 - int(oy), x1 - int(ox), y1 - int(oy)
        if x1 <= x0 or y1 <= y0:
            continue
        sig = sig.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
        sig = remove_background(sig, SIGNATURE_BG_TOLERANCE)
        _paste_clipped(overlay, sig, x0, y0)

    return overlay


def apply_edits(original_bytes: bytes, params: dict) -> Optional[bytes]:
    """Apply rotation -> crop -> background removal -> sketch composite; return PNG bytes.

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

        sketch = params.get('sketch')
        if sketch and (sketch.get('strokes') or sketch.get('signatures')):
            offset = (int(crop[0]), int(crop[1])) if crop else (0, 0)
            overlay = render_sketch((img.width, img.height), sketch, offset)
            img = Image.alpha_composite(img, overlay)

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


def transform_sketch_90(sketch, pre_rotation_size, clockwise):
    """Map sketch coordinates through a 90-degree rotation.

    CW: (x, y) -> (H - y, x); CCW: (x, y) -> (y, W - x),
    where (W, H) is the image size BEFORE this rotation step.
    """
    if not sketch:
        return sketch
    w, h = pre_rotation_size

    def pt(x, y):
        return [h - y, x] if clockwise else [y, w - x]

    out = {'strokes': [], 'signatures': []}
    for stroke in sketch.get('strokes') or []:
        out['strokes'].append({
            'color': stroke.get('color', '#000000'),
            'width': stroke.get('width', 4),
            'points': [pt(x, y) for x, y in (stroke.get('points') or [])],
        })
    for entry in sketch.get('signatures') or []:
        x0, y0, x1, y1 = entry['rect']
        c1, c2 = pt(x0, y0), pt(x1, y1)
        new_entry = dict(entry)
        new_entry['rect'] = [min(c1[0], c2[0]), min(c1[1], c2[1]),
                             max(c1[0], c2[0]), max(c1[1], c2[1])]
        out['signatures'].append(new_entry)
    return out
