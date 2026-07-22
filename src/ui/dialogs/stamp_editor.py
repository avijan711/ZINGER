"""Stamp editor: crop, auto-trim, background removal, 90-degree rotation.

Non-destructive: works on the original image bytes and returns edit
params; callers persist params via StampManager.
"""
from io import BytesIO
from PIL import Image

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
from .stamp_editor_preview import CropPreview, pil_to_qimage


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


class StampEditorDialog(QDialog):
    """Edit a stamp's crop / background removal / rotation, non-destructively."""

    def __init__(self, original_bytes: bytes, params=None, parent=None):
        super().__init__(parent)
        self.original_bytes = original_bytes
        self.params = dict(DEFAULT_EDIT_PARAMS, **(params or {}))
        self.setWindowTitle("Edit Stamp")
        self._working_img = None   # rotated + bg-removed PIL image

        self._build_ui()
        self.preview.set_sketch(self.params.get('sketch'))

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
        pre_size = (self._working_img.width, self._working_img.height)
        self.preview.set_sketch(transform_sketch_90(
            self.preview.sketch_or_none(), pre_size, clockwise=(delta > 0)))
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
        self.preview.set_sketch(None)

    def accept(self):
        self.params['crop'] = list(self.preview.crop) if self.preview.crop else None
        self.params['sketch'] = self.preview.sketch_or_none()
        if apply_edits(self.original_bytes, self.params) is None:
            QMessageBox.warning(self, "Edit Stamp",
                                "These edits would produce an empty image. "
                                "Adjust the crop or background removal.")
            return
        super().accept()
