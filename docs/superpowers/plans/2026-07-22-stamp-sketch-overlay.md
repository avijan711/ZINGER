# Stamp Sketch Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hand-drawn strokes and placed saved-signatures on stamps, fully re-editable, inside the existing StampEditorDialog.

**Architecture:** The sketch is vector data in the `edits` metadata (`strokes` + `signatures`), stored in rotated pre-crop image coordinates and composited by `apply_edits` as the final pipeline step (rotation → crop → bg removal → sketch). `StampManager` persists newly-placed signature bytes to per-stamp overlay files and prunes orphans. The editor gains a Crop/Draw mode toggle; the preview widget moves to its own file and grows draw-mode interaction.

**Tech Stack:** Python 3.11+, PyQt6, Pillow (ImageDraw), pytest.

**Spec:** `docs/superpowers/specs/2026-07-22-stamp-sketch-overlay-design.md`

## Global Constraints

- Imports rooted at `src/` (`from core.image_processing import ...`); `src/core/image_processing.py` keeps NO Qt imports.
- Sketch schema: `"sketch": None | {"strokes": [{"color": "#rrggbb", "width": int, "points": [[x,y],...]}], "signatures": [{"file": str|None, "rect": [x0,y0,x1,y1]} (+ transient "data": bytes|None in the dialog exchange format)]}`. All coordinates in **rotated, pre-crop** image space. `None`/absent sketch = no overlay.
- Pipeline order in `apply_edits`: rotation → crop → background removal → **sketch composite last**.
- Placed signatures get `remove_background(sig, 12)` at composite time (constant `SIGNATURE_BG_TOLERANCE = 12`); the copied file on disk stays pristine.
- 90° CW point mapping `(x, y) → (H − y, x)`; CCW `(x, y) → (y, W − x)` where `(W, H)` is the pre-rotation size. Rotation transforms the sketch; crop still resets on rotation.
- Signature copies live in `<stamps_dir>/overlays/{stamp_id}/{uuid}.png`; JSON metadata never holds bytes.
- Run tests with WSL system Python: `python3 -m pytest tests/ -v` from the repo root. Suite is currently 34 passing.
- Work on branch `feature/stamp-editing`. Commit after every task.

---

### Task 1: `render_sketch` + sketch composite in `apply_edits`

**Files:**
- Modify: `src/core/image_processing.py`
- Modify: `tests/test_image_processing.py`

**Interfaces:**
- Consumes: existing `remove_background`, `apply_edits`, `DEFAULT_EDIT_PARAMS`.
- Produces (used by Tasks 3 and 5):
  - `SIGNATURE_BG_TOLERANCE = 12` constant.
  - `DEFAULT_EDIT_PARAMS` gains `'sketch': None`.
  - `render_sketch(size: tuple[int,int], sketch: dict | None, crop_offset: tuple[int,int] = (0,0), supersample: int = 2) -> PIL.Image` (RGBA overlay of `size`; empty/None sketch → fully transparent).
  - `apply_edits` composites the sketch as its final step.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_image_processing.py`:

```python
from core.image_processing import render_sketch, SIGNATURE_BG_TOLERANCE


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_image_processing.py -v`
Expected: new tests FAIL with `ImportError: cannot import name 'render_sketch'`

- [ ] **Step 3: Write the implementation**

In `src/core/image_processing.py`: add `ImageDraw` to the PIL import (`from PIL import Image, ImageChops, ImageMath, ImageDraw` — keep whatever ImageChops/ImageMath imports Task "vectorize" left in place), change `DEFAULT_EDIT_PARAMS` to:

```python
DEFAULT_EDIT_PARAMS = {'rotation': 0, 'crop': None, 'bg_tolerance': 0, 'sketch': None}

SIGNATURE_BG_TOLERANCE = 12
```

Append:

```python
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
```

In `apply_edits`, after the `img = remove_background(...)` line and before the empty-image guard, insert:

```python
        sketch = params.get('sketch')
        if sketch and (sketch.get('strokes') or sketch.get('signatures')):
            offset = (int(crop[0]), int(crop[1])) if crop else (0, 0)
            overlay = render_sketch((img.width, img.height), sketch, offset)
            img = Image.alpha_composite(img, overlay)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -v`
Expected: all pass (34 existing + 10 new = 44). Existing stamp-manager tests comparing `edits == DEFAULT_EDIT_PARAMS` still pass because both sides carry the merged `'sketch': None`.

- [ ] **Step 5: Commit**

```bash
git add src/core/image_processing.py tests/test_image_processing.py
git commit -m "feat: render sketch overlays (strokes + signatures) in apply_edits"
```

---

### Task 2: `transform_sketch_90`

**Files:**
- Modify: `src/core/image_processing.py`
- Modify: `tests/test_image_processing.py`

**Interfaces:**
- Produces (used by Task 5): `transform_sketch_90(sketch: dict | None, pre_rotation_size: tuple[int,int], clockwise: bool) -> dict | None` — returns a NEW sketch with transformed coordinates; passes `None`/empty through unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_image_processing.py`:

```python
from core.image_processing import transform_sketch_90


def test_transform_sketch_none_passthrough():
    assert transform_sketch_90(None, (10, 20), True) is None


def test_transform_sketch_cw_point_mapping():
    # (x, y) -> (H - y, x) with pre-rotation size (W=30, H=20)
    sketch = {'strokes': [{'color': '#000000', 'width': 3,
                           'points': [[0, 0], [30, 20]]}], 'signatures': []}
    out = transform_sketch_90(sketch, (30, 20), clockwise=True)
    assert out['strokes'][0]['points'] == [[20, 0], [0, 30]]
    assert out['strokes'][0]['width'] == 3


def test_transform_sketch_ccw_point_mapping():
    # (x, y) -> (y, W - x) with pre-rotation size (W=30, H=20)
    sketch = {'strokes': [{'color': '#000000', 'width': 3,
                           'points': [[0, 0], [30, 20]]}], 'signatures': []}
    out = transform_sketch_90(sketch, (30, 20), clockwise=False)
    assert out['strokes'][0]['points'] == [[0, 30], [20, 0]]


def test_transform_sketch_rect_normalized():
    sketch = {'strokes': [], 'signatures': [
        {'file': 'x.png', 'rect': [2, 4, 10, 8]}]}
    out = transform_sketch_90(sketch, (30, 20), clockwise=True)
    # corners (2,4)->(16,2) and (10,8)->(12,10); normalized to [12,2,16,10]
    assert out['signatures'][0]['rect'] == [12, 2, 16, 10]
    assert out['signatures'][0]['file'] == 'x.png'


def test_transform_sketch_four_cw_is_identity():
    sketch = {'strokes': [{'color': '#123456', 'width': 5,
                           'points': [[3, 7], [11, 13]]}],
              'signatures': [{'file': 'x.png', 'rect': [1, 2, 5, 6]}]}
    size = (30, 20)
    out = sketch
    for _ in range(4):
        out = transform_sketch_90(out, size, clockwise=True)
        size = (size[1], size[0])
    assert out['strokes'][0]['points'] == [[3, 7], [11, 13]]
    assert out['signatures'][0]['rect'] == [1, 2, 5, 6]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_image_processing.py -v`
Expected: FAIL with `ImportError: cannot import name 'transform_sketch_90'`

- [ ] **Step 3: Write the implementation**

Append to `src/core/image_processing.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -v`
Expected: all pass (44 + 5 = 49)

- [ ] **Step 5: Commit**

```bash
git add src/core/image_processing.py tests/test_image_processing.py
git commit -m "feat: transform sketch coordinates through 90-degree rotations"
```

---

### Task 3: StampManager overlay persistence

**Files:**
- Modify: `src/core/stamp_manager.py`
- Modify: `tests/test_stamp_manager.py`

**Interfaces:**
- Consumes: `render_sketch`-aware `apply_edits` (Task 1).
- Produces (used by Task 5's flows, no signature change for callers):
  - `import_stamp` / `update_stamp_edits` persist transient `data` signature entries to `<stamps_dir>/overlays/{stamp_id}/{uuid}.png` and rewrite them to `file` entries before saving metadata.
  - `update_stamp_edits` prunes overlay files no longer referenced.
  - `delete_stamp` removes the stamp's overlay directory.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stamp_manager.py`:

```python
from io import BytesIO


def red_sig_png(size=(8, 8)):
    img = Image.new('RGBA', size, (255, 0, 0, 255))
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def sketch_with_data_sig():
    return {'strokes': [], 'signatures': [
        {'data': red_sig_png(), 'file': None, 'rect': [1, 1, 7, 7]}]}


def test_import_persists_sketch_signature_bytes(tmp_path):
    mgr = StampManager(str(tmp_path))
    edits = dict(DEFAULT_EDIT_PARAMS, sketch=sketch_with_data_sig())
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test", edits=edits)
    entry = mgr.stamps[stamp_id]['edits']['sketch']['signatures'][0]
    assert 'data' not in entry
    assert f"overlays" in entry['file'] and stamp_id in entry['file']
    assert Path(entry['file']).exists()
    with Image.open(mgr.stamps[stamp_id]['file']) as processed:
        assert processed.getpixel((4, 4))[0] > 200   # red ink composited


def test_update_persists_and_stores_sketch(tmp_path):
    mgr = StampManager(str(tmp_path))
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test")
    params = dict(DEFAULT_EDIT_PARAMS, sketch=sketch_with_data_sig())
    assert mgr.update_stamp_edits(stamp_id, params)
    entry = mgr.stamps[stamp_id]['edits']['sketch']['signatures'][0]
    assert 'data' not in entry and Path(entry['file']).exists()


def test_update_prunes_orphaned_overlays(tmp_path):
    mgr = StampManager(str(tmp_path))
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test")
    mgr.update_stamp_edits(stamp_id, dict(DEFAULT_EDIT_PARAMS,
                                          sketch=sketch_with_data_sig()))
    old_file = Path(mgr.stamps[stamp_id]['edits']['sketch']['signatures'][0]['file'])
    assert old_file.exists()
    assert mgr.update_stamp_edits(stamp_id, dict(DEFAULT_EDIT_PARAMS))  # sketch=None
    assert not old_file.exists()


def test_delete_stamp_removes_overlay_dir(tmp_path):
    mgr = StampManager(str(tmp_path))
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test",
                                edits=dict(DEFAULT_EDIT_PARAMS,
                                           sketch=sketch_with_data_sig()))
    overlay_dir = mgr.overlays_dir / stamp_id
    assert overlay_dir.exists()
    assert mgr.delete_stamp(stamp_id)
    assert not overlay_dir.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_stamp_manager.py -v`
Expected: FAIL (`overlays_dir` missing; `data` still in metadata)

- [ ] **Step 3: Implement StampManager changes**

In `src/core/stamp_manager.py`:

3a. In `__init__`, after `self.originals_dir = ...`:

```python
        self.overlays_dir = self.stamps_dir / "overlays"
```

In `_init_storage`, after the `originals_dir` mkdir:

```python
        self.overlays_dir.mkdir(parents=True, exist_ok=True)
```

3b. Add these methods after `update_stamp_edits`:

```python
    def _persist_sketch_signatures(self, stamp_id: str, params: Dict) -> Dict:
        """Write transient signature bytes to overlay files; rewrite entries."""
        sketch = params.get('sketch')
        if not sketch or not sketch.get('signatures'):
            return params
        params = dict(params)
        sketch = {'strokes': list(sketch.get('strokes') or []),
                  'signatures': []}
        stamp_overlays = self.overlays_dir / stamp_id
        for entry in params['sketch'].get('signatures') or []:
            new_entry = {k: v for k, v in entry.items() if k != 'data'}
            data = entry.get('data')
            if data:
                stamp_overlays.mkdir(parents=True, exist_ok=True)
                sig_path = stamp_overlays / f"{uuid.uuid4()}.png"
                sig_path.write_bytes(data)
                new_entry['file'] = str(sig_path)
            sketch['signatures'].append(new_entry)
        params['sketch'] = sketch
        return params

    def _prune_overlay_orphans(self, stamp_id: str, params: Dict) -> None:
        """Delete overlay files no longer referenced by the sketch."""
        try:
            stamp_overlays = self.overlays_dir / stamp_id
            if not stamp_overlays.exists():
                return
            sketch = params.get('sketch') or {}
            referenced = {entry.get('file')
                          for entry in sketch.get('signatures') or []}
            for f in stamp_overlays.iterdir():
                if str(f) not in referenced:
                    f.unlink()
            if not any(stamp_overlays.iterdir()):
                stamp_overlays.rmdir()
        except Exception as e:
            print(f"Error pruning overlay files: {e}")
```

3c. In `import_stamp`, replace the line `edits = dict(DEFAULT_EDIT_PARAMS, **(edits or {}))` with:

```python
            edits = dict(DEFAULT_EDIT_PARAMS, **(edits or {}))
            edits = self._persist_sketch_signatures(stamp_id, edits)
```

3d. In `update_stamp_edits`, after the `original is None` guard and before `apply_edits`, insert:

```python
            params = self._persist_sketch_signatures(stamp_id, params)
```

and after the successful metadata save (before `self.stamp_updated.emit(stamp_id)`), insert:

```python
            self._prune_overlay_orphans(stamp_id, info['edits'])
```

(`info['edits']` is already `dict(DEFAULT_EDIT_PARAMS, **params)` at that point.)

3e. In `delete_stamp`, after the stamp file unlink, add:

```python
            # Remove overlay files (placed signatures) and original
            shutil.rmtree(self.overlays_dir / stamp_id, ignore_errors=True)
            if 'original_file' in stamp_info:
                Path(stamp_info['original_file']).unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -v`
Expected: all pass (49 + 4 = 53)

- [ ] **Step 5: Commit**

```bash
git add src/core/stamp_manager.py tests/test_stamp_manager.py
git commit -m "feat: persist sketch signature overlays with orphan pruning"
```

---

### Task 4: Extract the preview widget to its own file (pure refactor)

**Files:**
- Create: `src/ui/dialogs/stamp_editor_preview.py`
- Modify: `src/ui/dialogs/stamp_editor.py`

**Interfaces:**
- Produces (used by Task 5): module `src/ui/dialogs/stamp_editor_preview.py` exporting `CropPreview`, `pil_to_qimage`, and the constants `HANDLE_RADIUS`, `HANDLE_HIT`, `MIN_CROP`, `CHECKER`. Zero behavior change.

- [ ] **Step 1: Move the code**

Create `src/ui/dialogs/stamp_editor_preview.py` containing, verbatim from the current `stamp_editor.py`: the module docstring `"""Preview widget for the stamp editor: checkerboard, crop rect, (draw mode added later)"""`, the imports it needs (`from io import BytesIO`, `from PIL import Image`, `from PyQt6.QtWidgets import QWidget`, `from PyQt6.QtGui import QPainter, QImage, QPen, QColor`, `from PyQt6.QtCore import Qt, QRectF, QPointF`), the four constants `HANDLE_RADIUS = 6`, `HANDLE_HIT = 10`, `MIN_CROP = 5`, `CHECKER = 12`, the `pil_to_qimage` function, and the entire `CropPreview` class — all moved unchanged.

In `stamp_editor.py`: delete the moved pieces and add:

```python
from .stamp_editor_preview import CropPreview, pil_to_qimage
```

Keep `MIN_CROP`-style constants only in the preview module (the dialog does not reference them directly today). The dialog keeps its own imports that it still uses (`QDialog` widgets, `QTimer`, PIL, `core.image_processing` functions).

- [ ] **Step 2: Verify (refactor must be invisible)**

Run: `python3 -m pytest tests/ -v` — all 53 pass.
Run: `cd src && python3 -c "from ui.dialogs.stamp_editor import StampEditorDialog; from ui.dialogs.stamp_editor_preview import CropPreview; print('ok')"` — prints ok.
Run: `grep -c "class CropPreview" src/ui/dialogs/*.py` — exactly one definition, in the new file.

- [ ] **Step 3: Commit**

```bash
git add src/ui/dialogs/stamp_editor.py src/ui/dialogs/stamp_editor_preview.py
git commit -m "refactor: extract stamp editor preview widget to its own module"
```

---

### Task 5: Draw mode — preview interaction + dialog controls + signature picker

**Files:**
- Modify: `src/ui/dialogs/stamp_editor_preview.py`
- Modify: `src/ui/dialogs/stamp_editor.py`

**Interfaces:**
- Consumes: `render_sketch`, `transform_sketch_90` (Tasks 1–2); `SignatureManager` from `core.signature_manager` (existing: `get_all_signatures() -> [{'id','name','file',...}]`, `get_signature_data(id) -> (bytes, name) | None`); `SIGNATURES_DIR` from `config.constants`.
- Produces: `dialog.params['sketch']` in the exchange format (Global Constraints); everything downstream (Task 3) already consumes it. No caller changes in `stamp_gallery.py`.

- [ ] **Step 1: Extend `CropPreview` with draw mode**

In `src/ui/dialogs/stamp_editor_preview.py`: extend imports —

```python
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QImage, QPen, QColor, QPainterPath
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from core.image_processing import render_sketch
```

Add constants:

```python
SIG_MIN_SIZE = 10          # px, minimum placed-signature dimension (image space)
SIG_HANDLE_HIT = 10        # px, grab distance for signature corner handles
```

Add to `CropPreview.__init__` (after existing fields):

```python
        self.mode = 'crop'                    # 'crop' | 'draw'
        self.sketch = {'strokes': [], 'signatures': []}
        self.pen_color = '#000000'
        self.pen_width = 4
        self.selected_sig = None              # index into sketch['signatures']
        self._active_stroke = None            # in-progress points (image coords)
        self._sig_drag = None                 # (kind, start_img_xy, orig_rect)
        self._overlay_qimage = None           # cached rendered sketch overlay
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
```

Add a signal on the class: `sketchChanged = pyqtSignal()`.

Add these methods:

```python
    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.selected_sig = None
        self.update()

    def set_sketch(self, sketch) -> None:
        sketch = sketch or {}
        self.sketch = {'strokes': list(sketch.get('strokes') or []),
                       'signatures': [dict(e) for e in sketch.get('signatures') or []]}
        self.invalidate_overlay()

    def sketch_or_none(self):
        """The sketch in exchange format, or None when empty."""
        if self.sketch['strokes'] or self.sketch['signatures']:
            return {'strokes': self.sketch['strokes'],
                    'signatures': self.sketch['signatures']}
        return None

    def invalidate_overlay(self) -> None:
        self._overlay_qimage = None
        self.update()

    def _sketch_overlay(self) -> QImage:
        """Rendered sketch at preview scale, cached until the sketch changes."""
        if self._overlay_qimage is None:
            s, _, _ = self._fit()
            w = max(1, round(self.qimage.width() * s))
            h = max(1, round(self.qimage.height() * s))
            scaled = {
                'strokes': [{'color': st.get('color', '#000000'),
                             'width': max(1, round(st.get('width', 4) * s)),
                             'points': [[x * s, y * s] for x, y in st['points']]}
                            for st in self.sketch['strokes']],
                'signatures': [dict(e, rect=[v * s for v in e['rect']])
                               for e in self.sketch['signatures']],
            }
            overlay = render_sketch((w, h), scaled)
            data = overlay.tobytes('raw', 'RGBA')
            self._overlay_qimage = QImage(
                data, overlay.width, overlay.height,
                QImage.Format.Format_RGBA8888).copy()
        return self._overlay_qimage

    def _sig_rect_widget(self, index: int) -> QRectF:
        x0, y0, x1, y1 = self.sketch['signatures'][index]['rect']
        tl = self._to_widget(x0, y0)
        br = self._to_widget(x1, y1)
        return QRectF(tl, br)

    def _sig_handle_at(self, pos: QPointF, index: int):
        rect = self._sig_rect_widget(index)
        for name, corner in (('tl', rect.topLeft()), ('tr', rect.topRight()),
                             ('bl', rect.bottomLeft()), ('br', rect.bottomRight())):
            if (abs(corner.x() - pos.x()) <= SIG_HANDLE_HIT and
                    abs(corner.y() - pos.y()) <= SIG_HANDLE_HIT):
                return name
        return None

    def keyPressEvent(self, event):
        if (self.mode == 'draw' and self.selected_sig is not None and
                event.key() == Qt.Key.Key_Delete):
            del self.sketch['signatures'][self.selected_sig]
            self.selected_sig = None
            self.invalidate_overlay()
            self.sketchChanged.emit()
        else:
            super().keyPressEvent(event)
```

Rework the three mouse handlers so the existing crop logic runs only in crop mode, and draw mode gets stroke/signature interaction. Replace `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent` with:

```python
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.qimage.isNull():
            return
        if self.mode == 'crop':
            self._crop_mouse_press(event)
            return
        pos = event.position()
        # Signature handle on the selected signature?
        if self.selected_sig is not None:
            handle = self._sig_handle_at(pos, self.selected_sig)
            if handle:
                self._sig_drag = (handle, self._to_image(pos),
                                  list(self.sketch['signatures'][self.selected_sig]['rect']))
                return
        # Click on a signature body (topmost last)?
        ix, iy = self._to_image(pos)
        for i in range(len(self.sketch['signatures']) - 1, -1, -1):
            x0, y0, x1, y1 = self.sketch['signatures'][i]['rect']
            if x0 <= ix <= x1 and y0 <= iy <= y1:
                self.selected_sig = i
                self._sig_drag = ('move', (ix, iy), [x0, y0, x1, y1])
                self.update()
                return
        # Otherwise: start a stroke
        self.selected_sig = None
        self._active_stroke = [[ix, iy]]
        self.update()

    def mouseMoveEvent(self, event):
        if self.mode == 'crop':
            self._crop_mouse_move(event)
            return
        pos = event.position()
        if self._active_stroke is not None:
            self._active_stroke.append(list(self._to_image(pos)))
            self.update()
            return
        if self._sig_drag is not None and self.selected_sig is not None:
            kind, (sx, sy), orig = self._sig_drag
            ix, iy = self._to_image(pos)
            dx, dy = ix - sx, iy - sy
            x0, y0, x1, y1 = orig
            if kind == 'move':
                self.sketch['signatures'][self.selected_sig]['rect'] = \
                    [x0 + dx, y0 + dy, x1 + dx, y1 + dy]
            else:
                w, h = x1 - x0, y1 - y0
                aspect = w / h if h else 1.0
                if kind == 'br':
                    nw = max(SIG_MIN_SIZE, w + dx)
                    rect = [x0, y0, x0 + nw, y0 + nw / aspect]
                elif kind == 'tl':
                    nw = max(SIG_MIN_SIZE, w - dx)
                    rect = [x1 - nw, y1 - nw / aspect, x1, y1]
                elif kind == 'bl':
                    nw = max(SIG_MIN_SIZE, w - dx)
                    rect = [x1 - nw, y0, x1, y0 + nw / aspect]
                else:  # 'tr'
                    nw = max(SIG_MIN_SIZE, w + dx)
                    rect = [x0, y1 - nw / aspect, x0 + nw, y1]
                self.sketch['signatures'][self.selected_sig]['rect'] = rect
            self.invalidate_overlay()

    def mouseReleaseEvent(self, event):
        if self.mode == 'crop':
            self._crop_mouse_release(event)
            return
        if self._active_stroke is not None:
            if len(self._active_stroke) >= 1:
                self.sketch['strokes'].append({
                    'color': self.pen_color,
                    'width': self.pen_width,
                    'points': self._active_stroke,
                })
            self._active_stroke = None
            self.invalidate_overlay()
            self.sketchChanged.emit()
        if self._sig_drag is not None:
            self._sig_drag = None
            self.sketchChanged.emit()
```

Rename the three original crop handlers' bodies to `_crop_mouse_press`, `_crop_mouse_move`, `_crop_mouse_release` (same code as today, unchanged).

In `paintEvent`, after `painter.drawImage(img_rect, self.qimage)` and before the crop-dim overlay block, insert sketch painting:

```python
        # Sketch overlay (visible in both modes)
        if self.sketch['strokes'] or self.sketch['signatures']:
            painter.drawImage(img_rect.topLeft(), self._sketch_overlay())

        # In-progress stroke drawn live
        if self._active_stroke and len(self._active_stroke) >= 1:
            s, _, _ = self._fit()
            pen = QPen(QColor(self.pen_color), max(1.0, self.pen_width * s))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            first = self._to_widget(*self._active_stroke[0])
            path.moveTo(first)
            for x, y in self._active_stroke[1:]:
                path.lineTo(self._to_widget(x, y))
            painter.drawPath(path)

        # Selected-signature chrome (draw mode only)
        if self.mode == 'draw' and self.selected_sig is not None:
            rect = self._sig_rect_widget(self.selected_sig)
            painter.setPen(QPen(QColor('#0078d4'), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
            painter.setBrush(QColor('white'))
            painter.setPen(QPen(QColor('#0078d4'), 1))
            for corner in (rect.topLeft(), rect.topRight(),
                           rect.bottomLeft(), rect.bottomRight()):
                painter.drawRect(QRectF(corner.x() - HANDLE_RADIUS,
                                        corner.y() - HANDLE_RADIUS,
                                        HANDLE_RADIUS * 2, HANDLE_RADIUS * 2))
```

Gate the existing crop-dim/handles painting on `self.mode == 'crop'` (wrap the crop overlay + border + handles block in `if self.mode == 'crop':`).

Also: `set_image` must call `self.invalidate_overlay()` instead of bare `self.update()` (scale may have changed).

- [ ] **Step 2: Add dialog controls and the signature picker**

In `src/ui/dialogs/stamp_editor.py`: extend imports —

```python
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSlider, QDialogButtonBox, QMessageBox, QWidget,
    QButtonGroup, QColorDialog, QListWidget, QListWidgetItem
)
from PyQt6.QtGui import QIcon, QPixmap, QImage, QColor, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QTimer, QSize
from core.image_processing import (
    remove_background, auto_trim, apply_edits, DEFAULT_EDIT_PARAMS,
    transform_sketch_90
)
from core.signature_manager import SignatureManager
from config.constants import SIGNATURES_DIR
```

Add after the module constants:

```python
SIG_PLACEMENT_FRACTION = 0.4   # inserted signature width vs image width


class SignaturePickerDialog(QDialog):
    """Pick one saved signature from the signature pad's store."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Insert Signature")
        self.signature_manager = SignatureManager(str(SIGNATURES_DIR))
        self.selected_bytes = None

        layout = QVBoxLayout(self)
        self.listw = QListWidget()
        self.listw.setViewMode(QListWidget.ViewMode.IconMode)
        self.listw.setIconSize(QSize(120, 60))
        self.listw.setResizeMode(QListWidget.ResizeMode.Adjust)
        for sig in self.signature_manager.get_all_signatures():
            data = self.signature_manager.get_signature_data(sig['id'])
            if not data:
                continue
            pixmap = QPixmap.fromImage(QImage.fromData(data[0]))
            item = QListWidgetItem(QIcon(pixmap), data[1])
            item.setData(Qt.ItemDataRole.UserRole, data[0])
            self.listw.addItem(item)
        self.listw.itemDoubleClicked.connect(lambda _: self.accept())
        layout.addWidget(self.listw)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def accept(self):
        item = self.listw.currentItem()
        if item is None:
            QMessageBox.information(self, "Insert Signature",
                                    "Select a signature first.")
            return
        self.selected_bytes = item.data(Qt.ItemDataRole.UserRole)
        super().accept()
```

In `StampEditorDialog.__init__`, after `self.params = ...`, seed the preview sketch (add right after `self._build_ui()`):

```python
        self.preview.set_sketch(self.params.get('sketch'))
```

(The preview's `sketchChanged` signal has no dialog-side listener today; it exists so the preview's mutation points are explicit and future consumers can hook them.)

Add to `_build_ui`, between the preview and the slider row — the mode toggle and draw controls:

```python
        mode_row = QHBoxLayout()
        self.crop_mode_btn = QPushButton("Crop")
        self.crop_mode_btn.setCheckable(True)
        self.crop_mode_btn.setChecked(True)
        self.draw_mode_btn = QPushButton("Draw")
        self.draw_mode_btn.setCheckable(True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.crop_mode_btn)
        group.addButton(self.draw_mode_btn)
        self.crop_mode_btn.clicked.connect(lambda: self._set_mode('crop'))
        self.draw_mode_btn.clicked.connect(lambda: self._set_mode('draw'))
        mode_row.addWidget(self.crop_mode_btn)
        mode_row.addWidget(self.draw_mode_btn)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self.draw_controls = QWidget()
        draw_row = QHBoxLayout(self.draw_controls)
        draw_row.setContentsMargins(0, 0, 0, 0)
        self.pen_color_btn = QPushButton()
        self.pen_color_btn.setFixedSize(28, 28)
        self.pen_color_btn.setToolTip("Pen color")
        self.pen_color_btn.clicked.connect(self._pick_pen_color)
        self._set_pen_swatch('#000000')
        draw_row.addWidget(self.pen_color_btn)
        draw_row.addWidget(QLabel("Width:"))
        self.pen_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.pen_width_slider.setRange(1, 20)
        self.pen_width_slider.setValue(4)
        self.pen_width_slider.setFixedWidth(120)
        self.pen_width_slider.valueChanged.connect(self._on_pen_width)
        draw_row.addWidget(self.pen_width_slider)
        undo_btn = QPushButton("Undo Stroke")
        undo_btn.clicked.connect(self._undo_stroke)
        draw_row.addWidget(undo_btn)
        clear_btn = QPushButton("Clear Sketch")
        clear_btn.clicked.connect(self._clear_sketch)
        draw_row.addWidget(clear_btn)
        insert_btn = QPushButton("Insert Signature")
        insert_btn.clicked.connect(self._insert_signature)
        draw_row.addWidget(insert_btn)
        draw_row.addStretch()
        self.draw_controls.setVisible(False)
        layout.addWidget(self.draw_controls)

        QShortcut(QKeySequence.StandardKey.Undo, self,
                  activated=self._undo_stroke)
```

Add the handler methods to `StampEditorDialog`:

```python
    def _set_mode(self, mode: str) -> None:
        self.preview.set_mode(mode)
        self.draw_controls.setVisible(mode == 'draw')

    def _set_pen_swatch(self, color: str) -> None:
        self.pen_color_btn.setStyleSheet(
            f"background-color: {color}; border: 1px solid #ced4da;"
            f" border-radius: 4px;")
        self.preview.pen_color = color

    def _pick_pen_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.preview.pen_color), self,
                                      "Pen Color")
        if color.isValid():
            self._set_pen_swatch(color.name())

    def _on_pen_width(self, value: int) -> None:
        self.preview.pen_width = value

    def _undo_stroke(self) -> None:
        if self.preview.mode != 'draw' or not self.preview.sketch['strokes']:
            return
        self.preview.sketch['strokes'].pop()
        self.preview.invalidate_overlay()

    def _clear_sketch(self) -> None:
        if self.preview.mode != 'draw':
            return
        reply = QMessageBox.question(
            self, "Clear Sketch",
            "Remove all strokes and placed signatures?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.preview.set_sketch(None)
            self.preview.selected_sig = None

    def _insert_signature(self) -> None:
        picker = SignaturePickerDialog(self)
        if picker.listw.count() == 0:
            QMessageBox.information(
                self, "Insert Signature",
                "No saved signatures. Create one in the Signature Pad first.")
            return
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        sig_bytes = picker.selected_bytes
        img = QImage.fromData(sig_bytes)
        if img.isNull():
            return
        iw = max(1, self.preview.qimage.width())
        ih = max(1, self.preview.qimage.height())
        w = iw * SIG_PLACEMENT_FRACTION
        h = w * img.height() / max(1, img.width())
        x0 = (iw - w) / 2
        y0 = (ih - h) / 2
        self.preview.sketch['signatures'].append({
            'data': sig_bytes, 'file': None,
            'rect': [x0, y0, x0 + w, y0 + h]})
        self.preview.selected_sig = len(self.preview.sketch['signatures']) - 1
        self.preview.invalidate_overlay()
```

Wire rotation and accept: in `_rotate`, BEFORE mutating `self.params['rotation']`, add:

```python
        pre_size = (self._working_img.width, self._working_img.height)
        self.preview.set_sketch(transform_sketch_90(
            self.preview.sketch_or_none(), pre_size, clockwise=(delta > 0)))
```

In `accept()`, next to the crop line, add:

```python
        self.params['sketch'] = self.preview.sketch_or_none()
```

In `_reset()`, also clear the sketch: after resetting params, add `self.preview.set_sketch(None)`.

- [ ] **Step 3: Verify**

Run: `python3 -m pytest tests/ -v` — all 53 pass.
Run: `cd src && python3 -c "from ui.dialogs.stamp_editor import StampEditorDialog, SignaturePickerDialog; print('ok')"` — prints ok.

Manual check on Windows (`cd C:\PySign && .venv\Scripts\python src\main.py`):
1. Gallery → right-click a stamp → Edit → click **Draw**: pen controls appear; drag on the preview draws smooth ink; change color/width and draw again.
2. **Undo Stroke** (and Ctrl+Z) removes the last stroke; **Clear Sketch** asks, then wipes everything.
3. **Insert Signature** lists saved signatures; picking one places it centered; drag to move, corner handles resize aspect-locked, Delete key removes it; its white background does not paint over the stamp.
4. Switch to **Crop** mode: sketch stays visible, crop handles work, drawing is disabled.
5. Rotate Left/Right: ink and placed signatures rotate with the image.
6. OK → thumbnail shows the ink; re-open Edit → strokes and signatures are still individually editable; drop the stamp on a PDF and Sign → ink is in the saved PDF.
7. Background-removal slider at 100 does not erase the ink.

- [ ] **Step 4: Commit**

```bash
git add src/ui/dialogs/stamp_editor.py src/ui/dialogs/stamp_editor_preview.py
git commit -m "feat: draw mode with pen, undo, and signature placement in stamp editor"
```
