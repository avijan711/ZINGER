from PyQt6.QtCore import Qt, QRect, QSize, QPoint
from PyQt6.QtWidgets import QLayout, QSizePolicy

class FlowLayout(QLayout):
    """A custom layout that arranges widgets in a flow, similar to word wrapping"""
    
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items = []
        
    def addItem(self, item):
        self._items.append(item)
        
    def count(self):
        return len(self._items)
        
    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None
        
    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None
        
    def expandingDirections(self):
        return Qt.Orientation(0)  # Neither horizontal nor vertical
        
    def hasHeightForWidth(self):
        return True
        
    def heightForWidth(self, width):
        return self._doLayout(QRect(0, 0, width, 0), True)
        
    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._doLayout(rect, False)
        
    def sizeHint(self):
        return self.minimumSize()
        
    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        
        margin = self.contentsMargins()
        size += QSize(2 * margin.left(), 2 * margin.top())
        return size
        
    def _doLayout(self, rect, test_only=False):
        """Layout the items within the given rectangle"""
        margin = self.contentsMargins()
        x = rect.x() + margin.left()
        y = rect.y() + margin.top()
        line_height = 0
        spacing = self.spacing()
        
        for item in self._items:
            style = item.widget().style()
            layout_spacing = style.layoutSpacing(
                QSizePolicy.ControlType.PushButton,
                QSizePolicy.ControlType.PushButton,
                Qt.Orientation.Horizontal
            )
            space_x = spacing + layout_spacing
            space_y = spacing + layout_spacing
            
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x() + margin.left()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        
        return y + line_height - rect.y() + margin.bottom()