# Stamp Color Update Plan

## Current Issue
The current color tinting implementation colors the entire stamp including the background, when we only want to color the actual stamp content (black pixels).

## Proposed Solution
Modify the color tinting logic to specifically replace black pixels with the selected color while preserving transparency. This is a better approach since stamps typically have black content that should be colored.

### Implementation Details

1. Update the color tinting logic in ImageCache.get_scaled_image():
```python
# Apply color to each pixel while preserving alpha
for item in data:
    # Get alpha value from original pixel
    alpha = item[3] if len(item) > 3 else 255
    if alpha > 0:  # Only process non-transparent pixels
        # Check if pixel is black or very dark
        is_black = item[0] < 30 and item[1] < 30 and item[2] < 30
        if is_black:
            # Replace black with selected color
            new_data.append((r, g, b, alpha))
        else:
            # Keep non-black pixels unchanged
            new_data.append(item)
    else:
        new_data.append((0, 0, 0, 0))  # Keep transparent pixels
```

### Key Changes
1. Remove luminance-based coloring
2. Add check for black/dark pixels
3. Replace only black pixels with the selected color
4. Keep non-black pixels unchanged
5. Preserve transparency

### Expected Result
- Only the black content of stamps will be colored
- White/light backgrounds will remain unchanged
- Transparency will be preserved
- The stamp's appearance will be more natural

## Testing Steps
1. Select a stamp with black content
2. Choose different colors
3. Verify only the black content changes color
4. Verify backgrounds remain unchanged
5. Verify transparency is preserved