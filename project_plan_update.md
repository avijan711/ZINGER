# PDF View Implementation Update

## Current Issues
1. Improper size policy handling in scroll area
2. QLabel limitations for custom painting and resizing
3. Incorrect coordinate transformations during resize

## Proposed Solution

### 1. Architecture Changes
```python
PDFView (QScrollArea)
  └─ PDFViewport (QWidget)  # Replace QLabel
      └─ Stamps (managed internally)
```

### 2. Implementation Changes

#### PDFViewport Class
- Inherit from QWidget
- Set proper size policies:
  ```python
  setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
  ```
- Implement resizeEvent to maintain stamp positions
- Use viewport coordinates for all interactions
- Cache scaled images for better performance
- Handle coordinate transformations properly

#### Size Handling
- Track viewport size changes
- Scale stamps relative to viewport
- Maintain positions during resize
- Implement proper coordinate mapping

#### Stamp Resizing
- Use relative coordinates for stamp positions (0.0 to 1.0)
- Scale absolute sizes based on viewport dimensions
- Maintain aspect ratios during resize
- Cache scaled images at different sizes

### 3. Technical Approach

1. **Coordinate System**
```python
class PDFViewport(QWidget):
    def __init__(self):
        self.setMinimumSize(QSize(100, 100))
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )
```

2. **Stamp Positioning**
```python
class StampPosition:
    def __init__(self):
        self.relative_x = 0.0  # 0.0 to 1.0
        self.relative_y = 0.0  # 0.0 to 1.0
        self.relative_width = 0.0  # relative to viewport width
        self.relative_height = 0.0  # relative to viewport height
```

3. **Resize Handling**
```python
def resizeEvent(self, event):
    old_size = event.oldSize()
    new_size = event.size()
    self.updateStampPositions(old_size, new_size)
```

4. **Coordinate Transformation**
```python
def viewportToRelative(self, point):
    return QPointF(
        point.x() / self.width(),
        point.y() / self.height()
    )

def relativeToViewport(self, point):
    return QPointF(
        point.x() * self.width(),
        point.y() * self.height()
    )
```

### 4. Benefits
1. Better scale handling
2. Proper coordinate transformations
3. Improved resize behavior
4. Better performance with caching
5. Maintainable stamp positions

### 5. Implementation Steps
1. Replace QLabel with QWidget
2. Implement proper size policies
3. Add coordinate transformation system
4. Update stamp handling
5. Implement caching system
6. Add resize event handling

This new approach should resolve the resizing issues while improving overall performance and maintainability.