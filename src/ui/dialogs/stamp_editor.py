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
