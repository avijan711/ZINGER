"""Stamp editor: crop, auto-trim, background removal, 90-degree rotation.

Non-destructive: works on the original image bytes and returns edit
params; callers persist params via StampManager.
"""
from io import BytesIO
from PIL import Image

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSlider, QDialogButtonBox, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer

from core.image_processing import (
    remove_background, auto_trim, apply_edits, DEFAULT_EDIT_PARAMS
)
from .stamp_editor_preview import CropPreview, pil_to_qimage


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
