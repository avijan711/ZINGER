# Stamp Editing, Cropping & On-PDF Manipulation — Design

**Date:** 2026-07-21
**Status:** Approved design, pending implementation plan

## Goal

Give PySign a full stamp-cleanup pipeline (crop, auto-trim, background removal, rotate) that works on both freshly imported and existing stamps, non-destructively. Add rotation and opacity to stamps placed on the PDF. Fix two latent bugs in the code being touched: placed signatures never render in the viewport, and `viewport.py` defines `_reset_stamp_color` twice.

Stamps come from a mix of scans/photos (white/off-white paper backgrounds, noise) and clean digital PNGs, so background removal needs an adjustable tolerance, not a fixed "delete pure white" rule.

## Phase 1 — Editor and non-destructive pipeline

### 1. Image processing core — new `src/core/image_processing.py`

Pure PIL functions with no Qt imports, so they are unit-testable:

- `remove_background(img: Image, tolerance: int) -> Image` — converts pixels whose RGB distance from white falls within `tolerance` to fully transparent. `tolerance` is 0–100 from the UI slider; 0 disables removal. Internally maps to a max Euclidean distance in RGB space.
- `auto_trim(img: Image, tolerance: int) -> tuple | None` — returns the bounding box `(x0, y0, x1, y1)` of non-background pixels, or `None` if everything is background.
- `apply_edits(original_bytes: bytes, params: dict) -> bytes` — applies edits in the fixed order **rotation → crop → background removal** and returns PNG bytes.

Edit params schema (stored in stamp metadata):

```json
{ "rotation": 0, "crop": [x0, y0, x1, y1] or null, "bg_tolerance": 0 }
```

`rotation` is limited to 0/90/180/270 in the editor. `crop` coordinates are in the rotated image's coordinate space.

### 2. Stamp Editor dialog — new `src/ui/dialogs/stamp_editor.py`

`StampEditorDialog(QDialog)`, structured like the existing `signature_pad.py`:

- Live preview on a checkerboard background (so transparency is visible), scaled to fit.
- Crop rectangle with draggable corner/edge handles over the preview.
- **Auto-Trim** button — calls `auto_trim` and sets the crop rect to the result.
- **Background removal slider** (0–100) — re-processes and refreshes the preview on change (debounced with a ~150 ms QTimer to keep the slider responsive on large images).
- **Rotate left / Rotate right** buttons (90° steps).
- **Reset** button — restores params to defaults (full image, no removal, no rotation).
- OK returns the params dict; Cancel discards.
- Guard: if the current params would produce an empty image (empty crop or full background removal), OK shows a warning and does not accept.

Entry points:

1. **Import flow** (`stamp_gallery.py`): after the user picks a file and name, the editor opens seeded with defaults; on OK the stamp is imported with those params applied.
2. **Gallery right-click → Edit** on a `StampThumbnail`: opens the editor seeded with the stamp's saved params against its original image. The thumbnail context menu is new and also carries Rename, Delete, and Change Color (existing buttons stay).

### 3. Non-destructive storage — `src/core/stamp_manager.py`

- `import_stamp(path, name, category, edits=None)` saves the untouched source image to `~/.pysign/stamps/stamps/originals/{id}.png` (sibling `originals/` under the existing stamps dir) and the processed result to the existing `{id}.png` location. Metadata gains `original_file` and `edits`.
- New method `update_stamp_edits(stamp_id, params) -> bool` — re-runs `apply_edits` on the original, overwrites the processed file, recomputes `original_width` / `original_height` / `aspect_ratio` from the processed result, saves metadata, emits new signal `stamp_updated(stamp_id)`.
- **Legacy migration is lazy:** stamps that predate this feature have no `original_file`. On first Edit, the current processed file is copied to `originals/` and recorded as the original.
- `StampGallery` connects `stamp_updated` to the same reload + PDF-viewport-cache-clear path already used for `stamp_color_changed`.

Note: the dimensions stored in metadata describe the **processed** image, since those drive drop sizing and aspect-locked resize.

### 4. Cleanups in touched code

- Delete the second (duplicate) `_reset_stamp_color` definition in `src/ui/pdf_viewer/viewport.py`; keep the first, better-guarded one.
- No change to the tint algorithm in `image_cache.py`: it already skips transparent and near-white pixels, so it behaves correctly once backgrounds are genuinely transparent.

## Phase 2 — On-PDF rotation and opacity

### 5. Annotation model

`Annotation.content` gains two optional keys with defaults: `rotation` (float degrees, default 0.0, free angle) and `opacity` (float 0.0–1.0, default 1.0). Absent keys mean defaults, so existing code paths and already-created annotations keep working.

### 6. Rendering — `src/ui/pdf_viewer/renderer.py`

`_render_annotation` is unified to render **both** `"stamp"` and `"signature"` types (fixing the bug where signatures are invisible until saved; signatures render without color tint). Rotation/opacity are applied around the viewport rect's center:

```
painter.save()
painter.translate(rect.center()); painter.rotate(rotation); painter.translate(-rect.center())
painter.setOpacity(opacity)
painter.drawImage(rect, img)
painter.restore()
```

Selection border and corner handles are drawn inside the same transform so they visually track the rotated stamp.

### 7. Interaction — `src/ui/pdf_viewer/viewport.py`

- **Rotate handle:** a small circle drawn ~20 px above the top-center of the selected annotation's rect. Dragging it rotates the annotation around its center (angle from center to cursor); holding Shift snaps to 15° increments.
- **Context menu additions** for any annotation: *Opacity* submenu (100% / 75% / 50% / 25%) and *Rotate* submenu (90° CW, 90° CCW, Reset rotation).
- **Hit-testing stays axis-aligned:** click/drag/resize detection continues to use the unrotated document rect. Rotation is a visual property until save. This is an accepted simplification; strongly rotated stamps will have a hit area that does not exactly match their appearance.
- Resize handles operate on the unrotated rect as today.

### 8. Saving — `src/core/pdf_handler.py`

The duplicated stamp/signature branches in `save_document` merge into one. Before `insert_image`, if `rotation != 0` or `opacity != 1.0`, the image bytes are baked with PIL:

- Opacity: multiply the alpha channel by `opacity`.
- Rotation: `img.rotate(-rotation, expand=True)` (PIL rotates counter-clockwise; screen rotation is clockwise-positive), then the target `fitz.Rect` is expanded to the rotated bounding box around the original rect's center so position and scale match the viewport preview.

Also switch to `page.insert_image(rect, stream=...)` with in-memory bytes, removing the temp-file dance.

## Error handling

- `apply_edits` failures (corrupt image, invalid params) return `None`; callers surface a QMessageBox and leave the stamp unchanged.
- Editor never persists params that produce an empty image (guard in §2).
- `update_stamp_edits` failure paths follow the existing StampManager convention (log, return `False`).

## Testing

- **pytest** (new dev dependency, first test infra in the repo): unit tests for `image_processing.py` only — background removal tolerance behavior, auto-trim bbox, `apply_edits` ordering, empty-result cases, and the save-path rotation/opacity baking helpers if extracted here.
- Dialogs and viewport interaction are verified manually (Windows target; drag/drop and COM paths are not automatable here).

## Phasing

- **Phase 1:** §1–§4 (processing core, editor dialog, non-destructive storage, cleanups).
- **Phase 2:** §5–§8 (annotation rotation/opacity, rendering incl. signature fix, interaction, save baking).

Each phase is independently shippable; Phase 2 does not depend on Phase 1's editor, only on shared PIL familiarity in `image_processing.py` (the alpha/rotation baking helpers may live there).

## Out of scope

- Free-angle rotation in the *editor* (90° steps only there; free angle exists only for placed annotations).
- Eraser brush, levels/contrast, perspective correction (revisit if photo stamps prove too messy).
- Rotation-aware hit-testing.
- Editing signatures with the stamp editor (stamps only for now).
