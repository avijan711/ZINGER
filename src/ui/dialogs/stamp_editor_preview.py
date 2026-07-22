"""Preview widget for the stamp editor: checkerboard, crop rect, (draw mode added later)"""

from PIL import Image

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QImage, QPen, QColor, QPainterPath
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from core.image_processing import render_sketch

HANDLE_RADIUS = 6      # px, half-size of crop handles in widget space
HANDLE_HIT = 10        # px, grab distance for handles
MIN_CROP = 5           # px, minimum crop dimension in image space
CHECKER = 12           # px, checkerboard square size
SIG_MIN_SIZE = 10          # px, minimum placed-signature dimension (image space)
SIG_HANDLE_HIT = 10        # px, grab distance for signature corner handles


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

    sketchChanged = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.qimage: QImage = QImage()
        self.crop = None
        self._drag_mode = None      # handle key, 'move', or None
        self._drag_start_img = None
        self._crop_start = None
        self.setMinimumSize(480, 360)

        self.mode = 'crop'                    # 'crop' | 'draw'
        self.sketch = {'strokes': [], 'signatures': []}
        self.pen_color = '#000000'
        self.pen_width = 4
        self.selected_sig = None              # index into sketch['signatures']
        self._active_stroke = None            # in-progress points (image coords)
        self._sig_drag = None                 # (kind, start_img_xy, orig_rect)
        self._overlay_qimage = None           # cached rendered sketch overlay
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_image(self, qimage: QImage, reset_crop: bool):
        self.qimage = qimage
        if reset_crop:
            self.crop = None
        self.invalidate_overlay()

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

        if self.mode == 'crop':
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

    def _crop_mouse_press(self, event):
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

    def _crop_mouse_move(self, event):
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

    def _crop_mouse_release(self, event):
        if self._drag_mode:
            # A crop equal to the full image is stored as None
            if self.crop == (0, 0, self.qimage.width(), self.qimage.height()):
                self.crop = None
            self._drag_mode = None
            self.update()
