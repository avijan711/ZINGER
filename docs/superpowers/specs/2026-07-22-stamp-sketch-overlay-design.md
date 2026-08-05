# Stamp Sketch Overlay — Hand-Drawn Signatures on Stamps — Design

**Date:** 2026-07-22
**Status:** Approved design, pending implementation plan
**Builds on:** `2026-07-21-stamp-editing-design.md` (the non-destructive stamp editor, merged via PR #1 branch `feature/stamp-editing`)

## Goal

Let the user hand-sketch a signature (or any ink) directly onto a stamp inside the existing `StampEditorDialog`, and/or place a saved signature from the signature pad onto the stamp. The overlay is **fully re-editable**: reopening Edit lets the user undo individual strokes, clear the sketch, or move/resize/remove a placed signature — without touching the underlying stamp image.

Pen is configurable (color + width). The composite becomes part of the stamp asset everywhere: gallery thumbnail, drops onto PDFs, and saved documents — with no changes needed outside the editor/storage layer, because the processed stamp PNG already flows through those paths.

## 1. Data model — `sketch` in the edits schema

`DEFAULT_EDIT_PARAMS` gains one key: `"sketch": None`. `None` or absent means no overlay (backward compatible with all existing stamps). When present:

```json
"sketch": {
  "strokes": [
    { "color": "#1a3fbf", "width": 4, "points": [[x, y], [x, y], ...] }
  ],
  "signatures": [
    { "file": "<abs path under overlays/>", "rect": [x0, y0, x1, y1] }
  ]
}
```

- All coordinates are in the **rotated, pre-crop image space** — the same space as `crop`. Ink therefore stays glued to the stamp content when the crop changes later.
- `width` is in image pixels (of that space). Stroke `points` need ≥ 2 entries; a single-point stroke is stored as two identical points (renders as a dot).
- **Rotation changes transform the sketch instead of destroying it** (unlike `crop`, which still resets): on a 90° CW rotation of an image whose pre-rotation height is `H`, every point maps `(x, y) → (H − y, x)`; signature rects map by transforming their corners and re-normalizing. Hand-drawn ink survives orientation fixes.

### Exchange format vs. stored format

Newly placed signatures don't have a file yet (the stamp's overlay dir may not even exist at import time). The dialog therefore returns signature entries as `{"data": <PNG bytes>, "file": None, "rect": [...]}` for new placements and `{"data": None, "file": <path>, "rect": [...]}` for pre-existing ones. `StampManager` persists any `data` entries to disk and rewrites them to `file` entries before saving metadata (JSON never holds bytes). `apply_edits` accepts both forms (`data` preferred when present).

## 2. Processing — `src/core/image_processing.py`

Pipeline order becomes **rotation → crop → background removal → sketch composite**. Compositing last means the tolerance slider can never eat ink, and light-colored pens work.

New pure functions (headless, unit-tested):

- `render_sketch(size, sketch, crop_offset=(0, 0), supersample=2) -> RGBA Image` — renders strokes with `ImageDraw` at `supersample×` resolution (lines with round caps/joins via `joint="curve"` plus end-cap ellipses), then LANCZOS-downscales for anti-aliasing; alpha-composites each signature entry into its rect (aspect handled by the stored rect — the editor keeps it aspect-locked). `crop_offset` translates the stored pre-crop coordinates into the cropped image's space; content outside the canvas clips naturally.
- Placed signatures get **automatic white-background removal** (`remove_background`, fixed tolerance 12) at composite time — the signature pad exports on white; without this a white rectangle would stamp over the design. The copied file on disk stays pristine.
- `transform_sketch_90(sketch, pre_rotation_size, clockwise: bool) -> sketch` — the coordinate transform used when the editor rotates.
- `apply_edits` calls `render_sketch` and `Image.alpha_composite`s it as the final step when `params.get("sketch")` is non-empty.

## 3. Storage — `src/core/stamp_manager.py`

- Copied signature images live in `<stamps_dir>/overlays/{stamp_id}/{uuid}.png`. Copying (rather than referencing the signature pad's file by id) means deleting a signature from the pad later can never corrupt a stamp.
- `import_stamp` and `update_stamp_edits` both: persist any `data` entries in `sketch.signatures` to the overlay dir, rewrite them to `file` entries, then run `apply_edits` and save metadata as today.
- `update_stamp_edits` **prunes orphans**: overlay files no longer referenced by any `sketch.signatures` entry are deleted.
- `delete_stamp` removes the stamp's overlay directory.

## 4. Editor UI — `src/ui/dialogs/stamp_editor.py`

The dialog gains a two-mode toolbar: **Crop** (default, existing behavior) and **Draw**. The preview widget is extracted to `src/ui/dialogs/stamp_editor_preview.py` before it grows further (it becomes the file's dominant class otherwise); the dialog file keeps dialog logic only.

Draw mode controls (hidden in Crop mode):

- **Pen color** swatch button → `QColorDialog` (default black).
- **Pen width** slider (1–20 px, default 4).
- **Undo Stroke** — pops the last stroke in the list, regardless of which session drew it. Ctrl+Z triggers it while in Draw mode.
- **Clear Sketch** — removes all strokes and placed signatures (confirmation prompt).
- **Insert Signature** — a small picker dialog listing the signature pad's saved signatures as thumbnails (its own `SignatureManager(str(SIGNATURES_DIR))`, matching `SignaturePadDialog`'s pattern). Choosing one places it centered at 40% of the image width (aspect preserved); shows an info message if no saved signatures exist.

Draw-mode interaction on the preview:

- Left-drag on empty canvas draws a stroke (points mapped widget → image space; consecutive events appended; stroke committed on release).
- Clicking a placed signature selects it (blue border + corner handles); dragging moves it; corner handles resize aspect-locked (min 10 px); `Delete` removes it. Clicking elsewhere deselects and draws.
- Crop mode leaves the sketch visible but not interactive; the crop rectangle is only interactive in Crop mode.

Live preview: the preview paints processed-image → sketch overlay (strokes + signatures rendered via the same `render_sketch`, at preview scale) so what you see is exactly what `apply_edits` produces. Rotation buttons call `transform_sketch_90` so ink follows the image (crop still resets, unchanged).

The dialog's contract is unchanged for callers: `dialog.params` now may contain `sketch` (exchange format, §1); the gallery's import/edit flows pass it through untouched — `StampManager` does the persistence.

## 5. Error handling

- Missing overlay file at `apply_edits` time (metadata edited by hand, disk loss): that signature entry is skipped, processing continues — consistent with the module's return-degraded-not-crash convention.
- The empty-image guard is unchanged; a sketch-only stamp (everything else background-removed) is valid since ink contributes alpha.
- `Clear Sketch` and `Delete` on a selected signature act only on in-dialog state; nothing touches disk until OK (Cancel discards, as everywhere in the dialog).

## 6. Testing

pytest for the headless parts: `render_sketch` (stroke pixels land where expected, supersampling produces non-aliased edges ≥ threshold alpha, crop offset translation, out-of-bounds clipping), signature compositing (white-bg removal applied, rect placement, missing-file skip), `transform_sketch_90` (round-trip: 4× CW = identity; known point mappings), `apply_edits` with sketch (composite is last — ink survives max tolerance), StampManager persistence (data→file rewrite, orphan pruning, overlay dir deletion with stamp). Editor interaction is verified manually on Windows, together with the still-pending GUI pass from the previous feature.

## Out of scope

- Eraser, smoothing, pressure sensitivity.
- Free-angle rotation of placed signatures inside the editor (on-PDF rotation already exists).
- Sketch on signature-pad signatures themselves (stamps only).
- Reflowing sketch coordinates when crop changes (ink is glued to image content by design; only rotation transforms it).
