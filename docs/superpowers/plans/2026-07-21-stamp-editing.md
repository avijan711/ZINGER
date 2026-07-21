# Stamp Editing, Cropping & On-PDF Rotation/Opacity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a non-destructive stamp editor (crop, auto-trim, background removal, 90° rotate) reachable at import and from the gallery, plus rotation/opacity for stamps placed on the PDF.

**Architecture:** Pure-PIL processing lives in a new headless module `src/core/image_processing.py` (unit-tested with pytest). A new `StampEditorDialog` drives it with a live preview. `StampManager` keeps untouched originals and regenerates processed PNGs from stored edit params. Phase 2 adds `rotation`/`opacity` keys to `Annotation.content`, rendered via QPainter transforms and baked with PIL at save time.

**Tech Stack:** Python 3.11+, PyQt6, Pillow, PyMuPDF (fitz), pytest (new dev dependency).

**Spec:** `docs/superpowers/specs/2026-07-21-stamp-editing-design.md`

## Global Constraints

- Imports are rooted at `src/` (the app runs with `src/` on `sys.path`): use `from core.image_processing import ...`, never `from src.core...`.
- `src/core/image_processing.py` must have **no Qt imports** — it is the headless, testable module.
- Edit params schema everywhere: `{"rotation": 0|90|180|270, "crop": [x0,y0,x1,y1] | null, "bg_tolerance": 0-100}`. Edits apply in fixed order **rotation → crop → background removal**.
- `Annotation.content` Phase 2 keys: `rotation` (float degrees clockwise, default 0.0), `opacity` (float 0.0–1.0, default 1.0). Absent keys mean defaults.
- Screen rotation is clockwise-positive; PIL's `Image.rotate` is counter-clockwise, so always call `img.rotate(-rotation, expand=True)`.
- Do not touch the legacy dead-code dirs `utils/` and `views/` at repo root, or the empty stubs `src/ui/pdf_renderer.py`, `src/ui/annotations/`, `src/ui/mixins/`.
- Run tests with the project's Python environment: `python -m pytest tests/ -v` from the repo root (on Windows: `.venv\Scripts\python -m pytest tests/ -v`).
- Commit after every task with a `feat:`/`fix:`/`test:` prefixed message.

---

## Phase 1 — Editor and non-destructive pipeline

### Task 1: Test infra + `remove_background`

**Files:**
- Create: `pytest.ini`
- Create: `tests/test_image_processing.py`
- Create: `src/core/image_processing.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `remove_background(img: PIL.Image, tolerance: int) -> PIL.Image` (RGBA result; `tolerance` 0–100, 0 = no-op conversion to RGBA).

- [ ] **Step 1: Create pytest config and add dev dependency**

`pytest.ini` (repo root):

```ini
[pytest]
pythonpath = src
testpaths = tests
```

Append to `requirements.txt`:

```
pytest>=7.0  # Dev: unit tests for image processing
```

- [ ] **Step 2: Write the failing tests**

`tests/test_image_processing.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_image_processing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.image_processing'`

- [ ] **Step 4: Write the implementation**

`src/core/image_processing.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_image_processing.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add pytest.ini requirements.txt tests/test_image_processing.py src/core/image_processing.py
git commit -m "feat: add image_processing module with background removal + pytest infra"
```

---

### Task 2: `auto_trim` and `apply_edits`

**Files:**
- Modify: `src/core/image_processing.py`
- Modify: `tests/test_image_processing.py`

**Interfaces:**
- Consumes: `remove_background` from Task 1.
- Produces: `auto_trim(img: PIL.Image, tolerance: int) -> tuple[int,int,int,int] | None`; `apply_edits(original_bytes: bytes, params: dict) -> bytes | None` (PNG bytes, `None` on failure/empty result); `DEFAULT_EDIT_PARAMS` dict constant.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_image_processing.py`:

```python
from core.image_processing import auto_trim, apply_edits, DEFAULT_EDIT_PARAMS


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_image_processing.py -v`
Expected: new tests FAIL with `ImportError: cannot import name 'auto_trim'`

- [ ] **Step 3: Write the implementation**

Append to `src/core/image_processing.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_image_processing.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_image_processing.py src/core/image_processing.py
git commit -m "feat: add auto_trim and apply_edits to image processing"
```

---

### Task 3: Non-destructive storage in StampManager

**Files:**
- Modify: `src/core/stamp_manager.py`
- Create: `tests/test_stamp_manager.py`

**Interfaces:**
- Consumes: `apply_edits`, `DEFAULT_EDIT_PARAMS` from Task 2.
- Produces (used by Tasks 4–5):
  - `StampManager.import_stamp(path: str, name: str, category: str = "General", edits: dict | None = None) -> str | None`
  - `StampManager.get_original_data(stamp_id: str) -> bytes | None` (lazily migrates legacy stamps)
  - `StampManager.update_stamp_edits(stamp_id: str, params: dict) -> bool`
  - New signal: `stamp_updated = pyqtSignal(str)`
  - Metadata keys per stamp: existing ones plus `original_file: str`, `edits: dict`.

- [ ] **Step 1: Write the failing tests**

`tests/test_stamp_manager.py`:

```python
"""Tests for non-destructive stamp storage. QObject works headless (no QApplication)."""
from io import BytesIO
from pathlib import Path
from PIL import Image

from core.stamp_manager import StampManager
from core.image_processing import DEFAULT_EDIT_PARAMS


def make_stamp_file(tmp_path, size=(10, 10)):
    img = Image.new('RGBA', size, (255, 255, 255, 255))
    for x in range(3, 7):
        for y in range(3, 7):
            img.putpixel((x, y), (0, 0, 0, 255))
    path = tmp_path / "source.png"
    img.save(path, 'PNG')
    return str(path)


def test_import_saves_original_and_processed(tmp_path):
    mgr = StampManager(str(tmp_path))
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test")
    assert stamp_id is not None
    info = mgr.stamps[stamp_id]
    assert Path(info['file']).exists()
    assert Path(info['original_file']).exists()
    assert 'originals' in info['original_file']
    assert info['edits'] == DEFAULT_EDIT_PARAMS
    assert info['original_width'] == 10


def test_import_with_edits_applies_them(tmp_path):
    mgr = StampManager(str(tmp_path))
    edits = {'rotation': 0, 'crop': [3, 3, 7, 7], 'bg_tolerance': 0}
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test", edits=edits)
    info = mgr.stamps[stamp_id]
    assert info['original_width'] == 4          # processed dims recorded
    assert info['original_height'] == 4
    with Image.open(info['original_file']) as orig:
        assert orig.size == (10, 10)            # original untouched


def test_update_stamp_edits_regenerates_processed(tmp_path):
    mgr = StampManager(str(tmp_path))
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test")
    updates = []
    mgr.stamp_updated.connect(updates.append)
    assert mgr.update_stamp_edits(stamp_id, {'rotation': 0, 'crop': [3, 3, 7, 7], 'bg_tolerance': 0})
    info = mgr.stamps[stamp_id]
    assert info['original_width'] == 4
    assert info['aspect_ratio'] == 1.0
    assert info['edits']['crop'] == [3, 3, 7, 7]
    assert updates == [stamp_id]


def test_update_stamp_edits_rejects_empty_result(tmp_path):
    mgr = StampManager(str(tmp_path))
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test")
    assert not mgr.update_stamp_edits(stamp_id, {'rotation': 0, 'crop': [2, 2, 2, 8], 'bg_tolerance': 0})


def test_legacy_stamp_migrates_lazily(tmp_path):
    mgr = StampManager(str(tmp_path))
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test")
    # Simulate a stamp imported before this feature existed
    original_path = Path(mgr.stamps[stamp_id]['original_file'])
    original_path.unlink()
    del mgr.stamps[stamp_id]['original_file']
    del mgr.stamps[stamp_id]['edits']
    mgr._save_metadata()

    data = mgr.get_original_data(stamp_id)
    assert data is not None
    assert 'original_file' in mgr.stamps[stamp_id]
    assert Path(mgr.stamps[stamp_id]['original_file']).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_stamp_manager.py -v`
Expected: FAIL (`original_file` KeyError / missing methods)

- [ ] **Step 3: Implement StampManager changes**

In `src/core/stamp_manager.py`:

3a. Add imports at top (after existing imports):

```python
from core.image_processing import apply_edits, DEFAULT_EDIT_PARAMS
from io import BytesIO
```

3b. Add the signal next to the existing ones:

```python
    stamp_updated = pyqtSignal(str)  # stamp_id (edits re-applied)
```

3c. In `__init__`, after `self.stamps_dir = ...`, add:

```python
        self.originals_dir = self.stamps_dir / "originals"
```

In `_init_storage`, after `self.stamps_dir.mkdir(...)`, add:

```python
        self.originals_dir.mkdir(parents=True, exist_ok=True)
```

3d. Replace the whole `import_stamp` method:

```python
    def import_stamp(self, path: str, name: str, category: str = "General",
                     edits: Optional[Dict] = None) -> Optional[str]:
        """Import a stamp, keeping the untouched original alongside the
        processed image so edits can be re-applied later."""
        try:
            if category not in self.categories:
                self.add_category(category)

            stamp_id = str(uuid.uuid4())
            edits = dict(DEFAULT_EDIT_PARAMS, **(edits or {}))

            # Normalize the source to RGBA PNG and keep it as the original
            with Image.open(path) as img:
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                original_path = self.originals_dir / f"{stamp_id}.png"
                img.save(original_path, 'PNG')

            processed = apply_edits(original_path.read_bytes(), edits)
            if processed is None:
                original_path.unlink(missing_ok=True)
                return None

            stamp_path = self.stamps_dir / f"{stamp_id}.png"
            stamp_path.write_bytes(processed)
            with Image.open(BytesIO(processed)) as out:
                width, height = out.size

            self.stamps[stamp_id] = {
                'name': name,
                'category': category,
                'file': str(stamp_path),
                'original_file': str(original_path),
                'edits': edits,
                'original_width': width,
                'original_height': height,
                'aspect_ratio': width / height,
                'color': '#000000'
            }
            self.categories[category].append(stamp_id)
            self._save_metadata()
            self.stamp_added.emit(stamp_id, category)
            return stamp_id
        except Exception as e:
            print(f"Error importing stamp: {e}")
            return None
```

3e. Add the two new methods after `update_stamp_color`:

```python
    def get_original_data(self, stamp_id: str) -> Optional[bytes]:
        """Return the untouched original image bytes, migrating legacy
        stamps (no stored original) by adopting their processed file."""
        if stamp_id not in self.stamps:
            return None
        try:
            info = self.stamps[stamp_id]
            original_path = Path(info['original_file']) if 'original_file' in info else None
            if original_path is None or not original_path.exists():
                original_path = self.originals_dir / f"{stamp_id}.png"
                shutil.copyfile(info['file'], original_path)
                info['original_file'] = str(original_path)
                info.setdefault('edits', dict(DEFAULT_EDIT_PARAMS))
                self._save_metadata()
            return original_path.read_bytes()
        except Exception as e:
            print(f"Error reading original stamp data: {e}")
            return None

    def update_stamp_edits(self, stamp_id: str, params: Dict) -> bool:
        """Re-apply edit params to the original and refresh the processed file."""
        original = self.get_original_data(stamp_id)
        if original is None:
            return False
        try:
            processed = apply_edits(original, params)
            if processed is None:
                return False
            info = self.stamps[stamp_id]
            Path(info['file']).write_bytes(processed)
            with Image.open(BytesIO(processed)) as out:
                width, height = out.size
            info['edits'] = dict(DEFAULT_EDIT_PARAMS, **params)
            info['original_width'] = width
            info['original_height'] = height
            info['aspect_ratio'] = width / height
            self._save_metadata()
            self.stamp_updated.emit(stamp_id)
            return True
        except Exception as e:
            print(f"Error updating stamp edits: {e}")
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: all pass (15 + 5)

- [ ] **Step 5: Commit**

```bash
git add src/core/stamp_manager.py tests/test_stamp_manager.py
git commit -m "feat: non-destructive stamp storage with originals and edit params"
```

---

### Task 4: StampEditorDialog

**Files:**
- Create: `src/ui/dialogs/stamp_editor.py`

**Interfaces:**
- Consumes: `remove_background`, `auto_trim`, `apply_edits`, `DEFAULT_EDIT_PARAMS` from Tasks 1–2.
- Produces (used by Task 5): `StampEditorDialog(original_bytes: bytes, params: dict | None = None, parent=None)`. After `exec()` returns `QDialog.DialogCode.Accepted`, read `dialog.params` (final edit params dict).

- [ ] **Step 1: Write the dialog**

`src/ui/dialogs/stamp_editor.py`:

```python
"""Stamp editor: crop, auto-trim, background removal, 90-degree rotation.

Non-destructive: works on the original image bytes and returns edit
params; callers persist params via StampManager.
"""
from io import BytesIO
from PIL import Image

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSlider, QDialogButtonBox, QMessageBox, QWidget
)
from PyQt6.QtGui import QPainter, QImage, QPen, QColor
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer

from core.image_processing import (
    remove_background, auto_trim, apply_edits, DEFAULT_EDIT_PARAMS
)

HANDLE_RADIUS = 6      # px, half-size of crop handles in widget space
HANDLE_HIT = 10        # px, grab distance for handles
MIN_CROP = 5           # px, minimum crop dimension in image space
CHECKER = 12           # px, checkerboard square size


def pil_to_qimage(img: Image.Image) -> QImage:
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    data = img.tobytes('raw', 'RGBA')
    # .copy() detaches from the Python buffer before it is GC'd
    return QImage(data, img.width, img.height,
                  QImage.Format.Format_RGBA8888).copy()


class CropPreview(QWidget):
    """Checkerboard-backed preview with a draggable crop rectangle.

    self.crop is (x0, y0, x1, y1) in image coordinates, or None = full image.
    """

    def __init__(self):
        super().__init__()
        self.qimage: QImage = QImage()
        self.crop = None
        self._drag_mode = None      # handle key, 'move', or None
        self._drag_start_img = None
        self._crop_start = None
        self.setMinimumSize(480, 360)

    def set_image(self, qimage: QImage, reset_crop: bool):
        self.qimage = qimage
        if reset_crop:
            self.crop = None
        self.update()

    # --- image <-> widget coordinate mapping ---
    def _fit(self):
        iw = max(1, self.qimage.width())
        ih = max(1, self.qimage.height())
        scale = max(0.01, min((self.width() - 20) / iw, (self.height() - 20) / ih))
        ox = (self.width() - iw * scale) / 2
        oy = (self.height() - ih * scale) / 2
        return scale, ox, oy

    def _to_widget(self, x, y) -> QPointF:
        s, ox, oy = self._fit()
        return QPointF(ox + x * s, oy + y * s)

    def _to_image(self, pos: QPointF):
        s, ox, oy = self._fit()
        return (pos.x() - ox) / s, (pos.y() - oy) / s

    def _crop_or_full(self):
        if self.crop:
            return self.crop
        return (0, 0, max(1, self.qimage.width()), max(1, self.qimage.height()))

    def _handles(self):
        x0, y0, x1, y1 = self._crop_or_full()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return {'tl': (x0, y0), 'tr': (x1, y0), 'bl': (x0, y1), 'br': (x1, y1),
                't': (cx, y0), 'b': (cx, y1), 'l': (x0, cy), 'r': (x1, cy)}

    # --- painting ---
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#e9ecef'))
        if self.qimage.isNull():
            return
        s, ox, oy = self._fit()
        img_rect = QRectF(ox, oy, self.qimage.width() * s, self.qimage.height() * s)

        # Checkerboard under the image so transparency is visible
        painter.save()
        painter.setClipRect(img_rect)
        light, dark = QColor('#ffffff'), QColor('#d0d0d0')
        y = img_rect.top()
        row = 0
        while y < img_rect.bottom():
            x = img_rect.left()
            col = 0
            while x < img_rect.right():
                painter.fillRect(QRectF(x, y, CHECKER, CHECKER),
                                 light if (row + col) % 2 == 0 else dark)
                x += CHECKER
                col += 1
            y += CHECKER
            row += 1
        painter.restore()

        painter.drawImage(img_rect, self.qimage)

        # Dim everything outside the crop rect
        x0, y0, x1, y1 = self._crop_or_full()
        tl = self._to_widget(x0, y0)
        br = self._to_widget(x1, y1)
        crop_rect = QRectF(tl, br)
        painter.save()
        painter.setClipRect(img_rect)
        dim = QColor(0, 0, 0, 110)
        painter.fillRect(QRectF(img_rect.topLeft(),
                                QPointF(img_rect.right(), crop_rect.top())), dim)
        painter.fillRect(QRectF(QPointF(img_rect.left(), crop_rect.bottom()),
                                img_rect.bottomRight()), dim)
        painter.fillRect(QRectF(QPointF(img_rect.left(), crop_rect.top()),
                                QPointF(crop_rect.left(), crop_rect.bottom())), dim)
        painter.fillRect(QRectF(QPointF(crop_rect.right(), crop_rect.top()),
                                QPointF(img_rect.right(), crop_rect.bottom())), dim)
        painter.restore()

        # Crop border + handles
        painter.setPen(QPen(QColor('#0078d4'), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(crop_rect)
        painter.setBrush(QColor('white'))
        painter.setPen(QPen(QColor('#0078d4'), 1))
        for hx, hy in self._handles().values():
            p = self._to_widget(hx, hy)
            painter.drawRect(QRectF(p.x() - HANDLE_RADIUS, p.y() - HANDLE_RADIUS,
                                    HANDLE_RADIUS * 2, HANDLE_RADIUS * 2))

    # --- interaction ---
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.qimage.isNull():
            return
        pos = event.position()
        for key, (hx, hy) in self._handles().items():
            p = self._to_widget(hx, hy)
            if (abs(p.x() - pos.x()) <= HANDLE_HIT and
                    abs(p.y() - pos.y()) <= HANDLE_HIT):
                self._drag_mode = key
                break
        else:
            x0, y0, x1, y1 = self._crop_or_full()
            ix, iy = self._to_image(pos)
            self._drag_mode = 'move' if x0 <= ix <= x1 and y0 <= iy <= y1 else None
        if self._drag_mode:
            self._drag_start_img = self._to_image(pos)
            self._crop_start = self._crop_or_full()

    def mouseMoveEvent(self, event):
        if not self._drag_mode:
            return
        iw, ih = self.qimage.width(), self.qimage.height()
        ix, iy = self._to_image(event.position())
        dx = ix - self._drag_start_img[0]
        dy = iy - self._drag_start_img[1]
        x0, y0, x1, y1 = self._crop_start

        if self._drag_mode == 'move':
            w, h = x1 - x0, y1 - y0
            nx0 = min(max(0, x0 + dx), iw - w)
            ny0 = min(max(0, y0 + dy), ih - h)
            self.crop = (int(nx0), int(ny0), int(nx0 + w), int(ny0 + h))
        else:
            if 'l' in self._drag_mode or self._drag_mode in ('tl', 'bl'):
                x0 = min(max(0, x0 + dx), x1 - MIN_CROP)
            if 'r' in self._drag_mode or self._drag_mode in ('tr', 'br'):
                x1 = max(min(iw, x1 + dx), x0 + MIN_CROP)
            if 't' in self._drag_mode or self._drag_mode in ('tl', 'tr'):
                y0 = min(max(0, y0 + dy), y1 - MIN_CROP)
            if 'b' in self._drag_mode or self._drag_mode in ('bl', 'br'):
                y1 = max(min(ih, y1 + dy), y0 + MIN_CROP)
            self.crop = (int(x0), int(y0), int(x1), int(y1))
        self.update()

    def mouseReleaseEvent(self, event):
        if self._drag_mode:
            # A crop equal to the full image is stored as None
            if self.crop == (0, 0, self.qimage.width(), self.qimage.height()):
                self.crop = None
            self._drag_mode = None
            self.update()


class StampEditorDialog(QDialog):
    """Edit a stamp's crop / background removal / rotation, non-destructively."""

    def __init__(self, original_bytes: bytes, params=None, parent=None):
        super().__init__(parent)
        self.original_bytes = original_bytes
        self.params = dict(DEFAULT_EDIT_PARAMS, **(params or {}))
        self.setWindowTitle("Edit Stamp")
        self._working_img = None   # rotated + bg-removed PIL image

        self._build_ui()

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._refresh)

        crop = self.params.get('crop')
        self._refresh(reset_crop=False)
        self.preview.crop = tuple(crop) if crop else None
        self.preview.update()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.preview = CropPreview()
        layout.addWidget(self.preview, 1)

        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("Background removal:"))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(int(self.params['bg_tolerance']))
        self.slider.valueChanged.connect(self._on_slider)
        slider_row.addWidget(self.slider, 1)
        self.slider_label = QLabel(str(self.params['bg_tolerance']))
        slider_row.addWidget(self.slider_label)
        layout.addLayout(slider_row)

        buttons_row = QHBoxLayout()
        trim_btn = QPushButton("Auto-Trim")
        trim_btn.clicked.connect(self._auto_trim)
        buttons_row.addWidget(trim_btn)
        rot_l = QPushButton("Rotate Left")
        rot_l.clicked.connect(lambda: self._rotate(-90))
        buttons_row.addWidget(rot_l)
        rot_r = QPushButton("Rotate Right")
        rot_r.clicked.connect(lambda: self._rotate(90))
        buttons_row.addWidget(rot_r)
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset)
        buttons_row.addWidget(reset_btn)
        buttons_row.addStretch()
        layout.addLayout(buttons_row)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _refresh(self, reset_crop: bool = False):
        """Rebuild the working image (rotation + bg removal) and preview."""
        try:
            with Image.open(BytesIO(self.original_bytes)) as src:
                img = src.convert('RGBA')
        except Exception:
            QMessageBox.critical(self, "Error", "Could not read the stamp image.")
            self.reject()
            return
        rotation = int(self.params['rotation']) % 360
        if rotation:
            img = img.rotate(-rotation, expand=True)
        img = remove_background(img, int(self.params['bg_tolerance']))
        self._working_img = img
        self.preview.set_image(pil_to_qimage(img), reset_crop)

    def _on_slider(self, value: int):
        self.params['bg_tolerance'] = value
        self.slider_label.setText(str(value))
        self._debounce.start()

    def _rotate(self, delta: int):
        self.params['rotation'] = (int(self.params['rotation']) + delta) % 360
        # Crop coords are in rotated space; dimensions changed, so reset
        self.params['crop'] = None
        self._refresh(reset_crop=True)

    def _auto_trim(self):
        bbox = auto_trim(self._working_img, int(self.params['bg_tolerance']))
        if bbox is None:
            QMessageBox.warning(self, "Auto-Trim",
                                "No content found — the whole image is background.")
            return
        self.preview.crop = bbox
        self.preview.update()

    def _reset(self):
        self.params = dict(DEFAULT_EDIT_PARAMS)
        self.slider.setValue(0)
        self._refresh(reset_crop=True)

    def accept(self):
        self.params['crop'] = list(self.preview.crop) if self.preview.crop else None
        if apply_edits(self.original_bytes, self.params) is None:
            QMessageBox.warning(self, "Edit Stamp",
                                "These edits would produce an empty image. "
                                "Adjust the crop or background removal.")
            return
        super().accept()
```

- [ ] **Step 2: Run the full test suite (no regressions)**

Run: `python -m pytest tests/ -v`
Expected: all pass (dialog has no unit tests; it is verified in Task 5's manual check)

- [ ] **Step 3: Commit**

```bash
git add src/ui/dialogs/stamp_editor.py
git commit -m "feat: add StampEditorDialog with crop, auto-trim, bg removal, rotate"
```

---

### Task 5: Gallery integration (import flow, context menu, cache refresh)

**Files:**
- Modify: `src/ui/stamp_gallery.py`

**Interfaces:**
- Consumes: `StampEditorDialog` (Task 4); `StampManager.import_stamp(..., edits=)`, `get_original_data`, `update_stamp_edits`, `stamp_updated` (Task 3).
- Produces: `StampGallery.edit_stamp(stamp_id: str)`; `StampThumbnail` context menu (Edit / Rename / Delete / Change Color).

- [ ] **Step 1: Wire the editor into the import flow**

In `src/ui/stamp_gallery.py`, add imports at the top:

```python
from .dialogs.stamp_editor import StampEditorDialog
from PyQt6.QtWidgets import QDialog, QMenu
```

(Extend the existing `PyQt6.QtWidgets` import list rather than adding a duplicate import line.)

Replace the body of `import_stamp` (the `if ok and name:` block):

```python
            if ok and name:
                try:
                    with open(file_path, 'rb') as f:
                        source_bytes = f.read()
                except OSError:
                    QMessageBox.critical(self, "Error", "Could not read the image file.")
                    return
                editor = StampEditorDialog(source_bytes, parent=self)
                if editor.exec() != QDialog.DialogCode.Accepted:
                    return
                category = self.category_combo.currentText()
                stamp_id = self.stamp_manager.import_stamp(
                    file_path, name, category, edits=editor.params
                )
                if not stamp_id:
                    QMessageBox.critical(self, "Error", "Failed to import stamp.")
```

- [ ] **Step 2: Add `edit_stamp` and the `stamp_updated` wiring to StampGallery**

In `StampGallery.__init__`, after the existing signal connections, add:

```python
        self.stamp_manager.stamp_updated.connect(self.on_stamp_updated)
```

Add these methods next to the other signal handlers:

```python
    def edit_stamp(self, stamp_id: str):
        """Open the non-destructive editor for an existing stamp."""
        original = self.stamp_manager.get_original_data(stamp_id)
        if original is None:
            QMessageBox.critical(self, "Error", "Could not load the stamp's original image.")
            return
        params = self.stamp_manager.stamps.get(stamp_id, {}).get('edits')
        editor = StampEditorDialog(original, params=params, parent=self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            if not self.stamp_manager.update_stamp_edits(stamp_id, editor.params):
                QMessageBox.critical(self, "Error", "Failed to update the stamp.")

    def on_stamp_updated(self, stamp_id: str):
        """Reload thumbnails and clear viewer caches after an edit."""
        self.load_stamps(self.category_combo.currentText())
        self.clear_image_cache()
```

Change `clear_image_cache`'s signature so both callers work (it is connected to `stamp_color_changed(str, str)` and now called with no args):

```python
    def clear_image_cache(self, *args):
```

- [ ] **Step 3: Add the thumbnail context menu**

Add to `StampThumbnail` (after `mouseMoveEvent`):

```python
    def contextMenuEvent(self, event):
        """Right-click menu: Edit / Rename / Delete / Change Color."""
        if not self.gallery:
            return
        self.gallery.select_stamp(self)
        menu = QMenu(self)
        edit_action = menu.addAction("Edit...")
        rename_action = menu.addAction("Rename...")
        color_action = menu.addAction("Change Color...")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(event.globalPos())
        if chosen == edit_action:
            self.gallery.edit_stamp(self.stamp_id)
        elif chosen == rename_action:
            self.gallery.rename_stamp()
        elif chosen == color_action:
            self.show_color_picker()
        elif chosen == delete_action:
            self.gallery.delete_stamp()
```

- [ ] **Step 4: Run the test suite and manually verify**

Run: `python -m pytest tests/ -v` — Expected: all pass.

Manual check (run the app: `cd src && python main.py`):
1. Import Stamp → pick an image → name it → editor opens. Slider makes white areas show checkerboard; Auto-Trim snaps the crop box to content; Rotate Left/Right turns the preview; drag crop handles; OK.
2. New stamp appears in gallery, cropped/cleaned.
3. Right-click the stamp → Edit… → previous settings are pre-loaded; change crop → OK → thumbnail updates.
4. Right-click → Rename / Delete / Change Color all work.
5. Drop the edited stamp on an open PDF — it renders with transparent background.

- [ ] **Step 5: Commit**

```bash
git add src/ui/stamp_gallery.py
git commit -m "feat: stamp editor in import flow and gallery context menu"
```

---

### Task 6: Remove duplicate `_reset_stamp_color`

**Files:**
- Modify: `src/ui/pdf_viewer/viewport.py:589-601`

**Interfaces:** none changed — deletes dead code (the second definition currently shadows the first).

- [ ] **Step 1: Delete the second definition**

In `src/ui/pdf_viewer/viewport.py`, delete lines 589–601 (the second `_reset_stamp_color`, whose docstring reads `"""Reset a stamp annotation's color to default"""` and which lacks the `annotation.type == "stamp"` guard). Keep the first definition at line 571.

- [ ] **Step 2: Verify**

Run: `python -m pytest tests/ -v` — Expected: all pass.
Manual: right-click a colored stamp on a PDF → Reset Color still works.

- [ ] **Step 3: Commit**

```bash
git add src/ui/pdf_viewer/viewport.py
git commit -m "fix: remove duplicate _reset_stamp_color shadowing the guarded version"
```

---

## Phase 2 — On-PDF rotation and opacity

### Task 7: Baking helpers in image_processing

**Files:**
- Modify: `src/core/image_processing.py`
- Modify: `tests/test_image_processing.py`

**Interfaces:**
- Produces (used by Task 8):
  - `bake_rotation_opacity(image_bytes: bytes, rotation: float, opacity: float) -> bytes | None` — PNG bytes with opacity multiplied into alpha and clockwise rotation baked (expand=True).
  - `rotated_bounding_size(width: float, height: float, rotation: float) -> tuple[float, float]` — bounding-box size of a w×h rect rotated by `rotation` degrees.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_image_processing.py`:

```python
import math
from core.image_processing import bake_rotation_opacity, rotated_bounding_size


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_image_processing.py -v`
Expected: FAIL with `ImportError: cannot import name 'bake_rotation_opacity'`

- [ ] **Step 3: Write the implementation**

Append to `src/core/image_processing.py` (add `import math` at the top of the file):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_image_processing.py -v`
Expected: 22 passed

- [ ] **Step 5: Commit**

```bash
git add src/core/image_processing.py tests/test_image_processing.py
git commit -m "feat: add rotation/opacity baking helpers for PDF save"
```

---

### Task 8: Unified, baking save path in PDFHandler

**Files:**
- Modify: `src/core/pdf_handler.py:179-247` (`save_document`)
- Create: `tests/test_pdf_handler_save.py`

**Interfaces:**
- Consumes: `bake_rotation_opacity`, `rotated_bounding_size` (Task 7).
- Produces: `save_document` unchanged signature; now handles both `image_data` and legacy `signature_data` content keys, bakes `rotation`/`opacity`, and uses `page.insert_image(rect, stream=...)` (no temp files).

Note: this also fixes a latent bug — the old signature branch read `content['signature_data']`, but signature drops store `image_data`, so saving a document with a signature failed silently.

- [ ] **Step 1: Write the failing tests**

`tests/test_pdf_handler_save.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pdf_handler_save.py -v`
Expected: `test_save_signature_with_image_data_key`, `test_save_with_rotation_and_opacity`, and `test_save_rotation_expands_rect_within_page` FAIL (KeyError path / no baking); stamp test may pass.

- [ ] **Step 3: Rewrite the annotation loop in `save_document`**

In `src/core/pdf_handler.py`: add to the top of the file

```python
from core.image_processing import bake_rotation_opacity, rotated_bounding_size
```

Remove the now-unused `import tempfile`. Replace the entire `# Apply all annotations` for-loop (the two `if annotation.type == 'stamp'` / `elif annotation.type == 'signature'` branches with their temp-file handling) with:

```python
            # Apply all annotations (stamps and signatures are both images)
            for annotation in self.annotations:
                page = doc_copy[annotation.page]
                image_data = (annotation.content.get('image_data')
                              or annotation.content.get('signature_data'))
                if not image_data:
                    continue

                rect = fitz.Rect(*annotation.rect)
                rotation = float(annotation.content.get('rotation', 0.0))
                opacity = float(annotation.content.get('opacity', 1.0))

                if rotation % 360 != 0 or opacity < 1.0:
                    image_data = bake_rotation_opacity(image_data, rotation, opacity)
                    if image_data is None:
                        continue
                    if rotation % 360 != 0:
                        w, h = rotated_bounding_size(rect.width, rect.height, rotation)
                        cx = (rect.x0 + rect.x1) / 2
                        cy = (rect.y0 + rect.y1) / 2
                        rect = fitz.Rect(cx - w / 2, cy - h / 2,
                                         cx + w / 2, cy + h / 2)

                page.insert_image(rect, stream=image_data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: all pass (22 image-processing + 5 stamp-manager + 5 save-path)

- [ ] **Step 5: Commit**

```bash
git add src/core/pdf_handler.py tests/test_pdf_handler_save.py
git commit -m "fix: unify annotation save path, bake rotation/opacity, stream images"
```

---

### Task 9: Renderer — rotation, opacity, and visible signatures

**Files:**
- Modify: `src/ui/pdf_viewer/renderer.py:67-121`
- Modify: `src/ui/pdf_viewer/constants.py`

**Interfaces:**
- Produces (used by Task 10): constants `ROTATE_HANDLE_OFFSET = 20`, `ROTATE_HANDLE_RADIUS = 6` in `src/ui/pdf_viewer/constants.py`; `_render_annotation` renders both `"stamp"` and `"signature"` types with `rotation`/`opacity` from content; `_draw_rotate_handle(painter, viewport_rect)` on `PDFRenderer`.

Note: this fixes the latent bug where placed signatures never rendered in the viewport (only `type == "stamp"` was drawn).

- [ ] **Step 1: Add constants**

Append to `src/ui/pdf_viewer/constants.py`:

```python
# Rotate handle (Phase 2 on-PDF rotation)
ROTATE_HANDLE_OFFSET = 20
ROTATE_HANDLE_RADIUS = 6
```

- [ ] **Step 2: Rewrite `_render_annotation` and add `_draw_rotate_handle`**

In `src/ui/pdf_viewer/renderer.py`, add to the imports:

```python
from PyQt6.QtCore import Qt, QRectF, QRect, QPointF
from .constants import ROTATE_HANDLE_OFFSET, ROTATE_HANDLE_RADIUS
```

Replace `_render_annotation` with:

```python
    def _render_annotation(self, painter: QPainter, annotation: Annotation,
                         zoom_level: float, is_selected: bool) -> None:
        """Render a single annotation (stamp or signature)"""
        try:
            doc_coords = [float(x) for x in annotation.rect]
            viewport_rect = QRectF(
                doc_coords[0] * zoom_level,
                doc_coords[1] * zoom_level,
                (doc_coords[2] - doc_coords[0]) * zoom_level,
                (doc_coords[3] - doc_coords[1]) * zoom_level
            )

            image_data = (annotation.content.get("image_data")
                          or annotation.content.get("signature_data"))
            if not image_data:
                return

            # Only stamps carry a tint color
            color = annotation.content.get("color") if annotation.type == "stamp" else None
            rotation = float(annotation.content.get("rotation", 0.0))
            opacity = float(annotation.content.get("opacity", 1.0))

            img = self.image_cache.get_scaled_image(
                image_data,
                max(1, int(viewport_rect.width())),
                max(1, int(viewport_rect.height())),
                color
            )

            painter.save()
            if rotation % 360 != 0:
                center = viewport_rect.center()
                painter.translate(center)
                painter.rotate(rotation)
                painter.translate(-center)
            painter.setOpacity(opacity)
            painter.drawImage(viewport_rect, img)
            painter.setOpacity(1.0)

            if is_selected:
                self._draw_selection_handles(painter, viewport_rect)
                self._draw_rotate_handle(painter, viewport_rect)
            painter.restore()

        except Exception as e:
            logger.error(f"Error rendering annotation: {e}")

    def _draw_rotate_handle(self, painter: QPainter, viewport_rect: QRectF) -> None:
        """Draw the rotate handle above the top-center of the selection"""
        top_center = QPointF(viewport_rect.center().x(), viewport_rect.top())
        handle_center = QPointF(top_center.x(),
                                top_center.y() - ROTATE_HANDLE_OFFSET)
        painter.setPen(QPen(Qt.GlobalColor.blue, 1))
        painter.drawLine(top_center, handle_center)
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawEllipse(handle_center, ROTATE_HANDLE_RADIUS, ROTATE_HANDLE_RADIUS)
```

- [ ] **Step 3: Verify**

Run: `python -m pytest tests/ -v` — Expected: all pass.

Manual (run the app): drop a signature from the signature pad onto a PDF — **it now renders immediately** (previously invisible). Drop a stamp; select it; a circular handle appears above it.

- [ ] **Step 4: Commit**

```bash
git add src/ui/pdf_viewer/renderer.py src/ui/pdf_viewer/constants.py
git commit -m "feat: render rotation/opacity; fix invisible signature annotations"
```

---

### Task 10: Viewport interaction — rotate handle, context-menu controls

**Files:**
- Modify: `src/ui/pdf_viewer/viewport.py`

**Interfaces:**
- Consumes: `ROTATE_HANDLE_OFFSET`, `ROTATE_HANDLE_RADIUS` (Task 9); `AnnotationManager.start_resize(pos, annotation, handle)` (existing — reused with handle name `'rotate'`).
- Produces: user-facing rotation drag (Shift snaps to 15°), context-menu Opacity/Rotate submenus for all annotations.

- [ ] **Step 1: Add rotate-handle hit-testing and drag**

In `src/ui/pdf_viewer/viewport.py`, add to the imports:

```python
import math
from PyQt6.QtWidgets import QWidget, QSizePolicy, QMenu, QApplication
from .constants import ROTATE_HANDLE_OFFSET, ROTATE_HANDLE_RADIUS
```

Add these methods after `_get_resize_handle`:

```python
    def _get_rotate_handle_rect(self, viewport_rect: QRectF) -> QRectF:
        """Hit area of the rotate handle (axis-aligned, like all hit-testing)"""
        cx = viewport_rect.center().x()
        cy = viewport_rect.top() - ROTATE_HANDLE_OFFSET
        r = ROTATE_HANDLE_RADIUS + 3  # slightly generous grab area
        return QRectF(cx - r, cy - r, r * 2, r * 2)

    def _handle_rotate(self, pos: QPointF) -> None:
        """Rotate the selected annotation to face the cursor; Shift snaps 15 deg"""
        try:
            state = self.annotation_manager.state
            if not state.selected_annotation:
                return
            doc_coords = [float(x) for x in state.selected_annotation.rect]
            center = self._get_viewport_rect(doc_coords).center()
            # 0 deg when the cursor is straight above center, clockwise-positive
            angle = math.degrees(math.atan2(pos.x() - center.x(),
                                            center.y() - pos.y()))
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
                angle = round(angle / 15.0) * 15.0
            state.selected_annotation.content['rotation'] = angle % 360
            self.update()
        except Exception as e:
            logger.error(f"Error handling rotate: {e}")
```

- [ ] **Step 2: Route press/move events through the rotate handle**

In `mousePressEvent`, inside the `if state.selected_annotation:` block, insert the rotate check **before** the corner-handle check:

```python
            if state.selected_annotation:
                doc_coords = [float(x) for x in state.selected_annotation.rect]
                viewport_rect = self._get_viewport_rect(doc_coords)

                # Check rotate handle first (sits above the rect)
                if self._get_rotate_handle_rect(viewport_rect).contains(pos):
                    self.annotation_manager.start_resize(
                        pos, state.selected_annotation, 'rotate')
                    return

                # Check for corner handle hit
                handle = self._get_resize_handle(pos, viewport_rect)
                if handle:
                    self.annotation_manager.start_resize(pos, state.selected_annotation, handle)
                    return
```

In `mouseMoveEvent`, change the drag/resize dispatch to:

```python
            if (event.buttons() & Qt.MouseButton.LeftButton and
                state.drag_start_pos and state.selected_annotation):
                if state.resize_handle == 'rotate':
                    self._handle_rotate(pos)
                elif state.resize_handle:
                    self._handle_resize(pos)
                else:
                    self._handle_drag(pos)
```

- [ ] **Step 3: Extend the context menu (and fix its zoom bug)**

Replace the beginning of `contextMenuEvent` — the position lookup currently forgets to convert to document coordinates, so it misses at zoom ≠ 100%:

```python
        try:
            pos = event.pos()
            doc_pos = QPointF(
                pos.x() / self.pdf_handler.zoom_level,
                pos.y() / self.pdf_handler.zoom_level
            )
            clicked_annotation = self.annotation_manager.get_annotation_at_position(
                doc_pos, self.pdf_handler.current_page
            )
```

Inside the `if clicked_annotation:` block, after the existing Reset Color logic and before the Remove action, add:

```python
                # Opacity presets
                opacity_menu = menu.addMenu("Opacity")
                current_opacity = float(clicked_annotation.content.get('opacity', 1.0))
                for percent in (100, 75, 50, 25):
                    action = opacity_menu.addAction(f"{percent}%")
                    action.setCheckable(True)
                    action.setChecked(abs(current_opacity - percent / 100) < 0.01)
                    action.triggered.connect(
                        lambda checked, p=percent, a=clicked_annotation:
                        self._set_annotation_opacity(a, p / 100)
                    )

                # Rotation
                rotate_menu = menu.addMenu("Rotate")
                rotate_menu.addAction("90° Clockwise").triggered.connect(
                    lambda: self._rotate_annotation(clicked_annotation, 90))
                rotate_menu.addAction("90° Counter-clockwise").triggered.connect(
                    lambda: self._rotate_annotation(clicked_annotation, -90))
                rotate_menu.addAction("Reset Rotation").triggered.connect(
                    lambda: self._set_annotation_rotation(clicked_annotation, 0.0))

                menu.addSeparator()
```

Add the three helper methods after `_remove_annotation`:

```python
    def _set_annotation_opacity(self, annotation: Annotation, opacity: float) -> None:
        annotation.content['opacity'] = opacity
        self.update()

    def _rotate_annotation(self, annotation: Annotation, delta: float) -> None:
        current = float(annotation.content.get('rotation', 0.0))
        annotation.content['rotation'] = (current + delta) % 360
        self.update()

    def _set_annotation_rotation(self, annotation: Annotation, rotation: float) -> None:
        annotation.content['rotation'] = rotation
        self.update()
```

- [ ] **Step 4: Run tests and manually verify**

Run: `python -m pytest tests/ -v` — Expected: all pass.

Manual (run the app, open a PDF, drop a stamp):
1. Select the stamp → drag the circular handle → stamp rotates freely; with Shift it snaps in 15° steps.
2. Right-click → Opacity → 50% → stamp becomes translucent; the current preset is checked.
3. Right-click → Rotate → 90° Clockwise / Reset Rotation behave as labeled.
4. Zoom in (Ctrl++), right-click a stamp → menu still finds it (zoom fix).
5. Sign (Ctrl+Return) → open the `_signed.pdf` → rotation and opacity match the preview; a rotated stamp stays centered where it was placed.
6. Known accepted limitation: with large rotations, the selection box and grab areas stay axis-aligned while the image is rotated.

- [ ] **Step 5: Commit**

```bash
git add src/ui/pdf_viewer/viewport.py
git commit -m "feat: rotate handle, opacity/rotation context menus, zoom-aware menu hit"
```
