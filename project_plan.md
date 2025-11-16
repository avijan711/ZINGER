# Stamp Color Reset Feature Implementation Plan

## Overview
Add a "Reset Color" option to the context menu when right-clicking a colored stamp annotation in a PDF document.

## Implementation Steps

1. Context Menu Enhancement
   - Modify PDFViewport.contextMenuEvent to identify stamp annotations
   - Add conditional logic to show "Reset Color" option only for stamps
   - Place the option in a logical position in the menu (before or after "Remove")

2. Reset Color Functionality
   - Add _reset_stamp_color method to PDFViewport class
   - Method should:
     * Set color back to "#000000" (default black)
     * Clear the image cache to force redraw
     * Update the display to show changes

3. Validation and Checks
   - Verify annotation is a stamp type
   - Check if annotation has a color set
   - Ensure proper error handling

4. Cache Management
   - Clear ImageCache when color is reset
   - Force redraw of affected annotations
   - Maintain proper state consistency

## Technical Details

### Context Menu Changes
```python
if clicked_annotation and clicked_annotation.type == "stamp":
    menu = QMenu(self)
    
    # Add reset color option
    if "color" in clicked_annotation.content:
        reset_color_action = menu.addAction("Reset to Default Color")
        reset_color_action.triggered.connect(
            lambda: self._reset_stamp_color(clicked_annotation)
        )
    
    # Existing remove action
    remove_action = menu.addAction("Remove")
    remove_action.triggered.connect(
        lambda: self._remove_annotation(clicked_annotation)
    )
```

### Reset Color Method
```python
def _reset_stamp_color(self, annotation: Annotation) -> None:
    """Reset a stamp annotation's color to default"""
    try:
        if "color" in annotation.content:
            # Update to default color
            annotation.content["color"] = "#000000"
            # Clear image cache to force redraw
            self.image_cache.clear()
            # Update display
            self.update()
    except Exception as e:
        logger.error(f"Error resetting stamp color: {e}")
```

## Testing Plan

1. Basic Functionality
   - Right-click on a colored stamp shows "Reset Color" option
   - Right-click on non-stamp annotations doesn't show the option
   - Option only appears when color is set

2. Color Reset
   - Verify stamp returns to default black color
   - Check that white/transparent areas remain unchanged
   - Ensure proper visual update after reset

3. Edge Cases
   - Multiple stamps with different colors
   - Stamps without color property
   - Rapid color changes and resets

## Implementation Order

1. Add _reset_stamp_color method
2. Modify context menu logic
3. Add cache clearing
4. Test and verify functionality