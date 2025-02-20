# Stamp Color Fix Plan

## Issue
The stamp coloring functionality is broken because the color value stored in the annotation's content is not being passed to the image cache's color tinting system during rendering.

## Current Flow
1. Color selection works in StampGallery
2. Color is stored in StampManager
3. Color is included in drag-drop metadata
4. Color is stored in annotation content
5. ❌ Color is not passed to image cache during rendering

## Fix Plan

### 1. Update PDFView's Render Method
Modify the `_render_annotation` method in PDFView to pass the color from annotation content:

```python
def _render_annotation(self, painter: QPainter, annotation: Annotation) -> None:
    if annotation.type == "stamp":
        # Get color from annotation content
        color = annotation.content.get("color")
        img = self.image_cache.get_scaled_image(
            annotation.content["image_data"],
            max(1, int(viewport_rect.width())),
            max(1, int(viewport_rect.height())),
            color  # Pass color to image cache
        )
```

### 2. Add Debug Logging
Add logging statements to track color through the pipeline:
- Log when color is retrieved from annotation content
- Log when color is passed to image cache
- Log when color tinting is applied

### 3. Testing Steps
1. Select a stamp and change its color
2. Verify color is stored in metadata
3. Drag stamp onto PDF
4. Verify color is stored in annotation content
5. Verify color is passed to image cache
6. Verify color tinting is applied to stamp

## Expected Result
After implementing these changes, stamps should properly display their selected colors when placed on the PDF.