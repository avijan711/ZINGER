# Stamp Color Debug Plan

## Issue
The stamp coloring is completely non-functional - no color changes are being applied regardless of the selected color.

## Investigation Steps

1. **Verify Color Selection and Storage**
   - Check if color is properly selected in StampGallery
   - Verify color is stored in StampManager
   - Add debug logging to track color value

2. **Check Drag and Drop Pipeline**
   - Verify color metadata is included in drag operation
   - Verify color is preserved in annotation content
   - Add debug logging for metadata transfer

3. **Analyze Image Cache Usage**
   - We have two ImageCache implementations:
     * src/ui/pdf_viewer/image_cache.py (main implementation)
     * src/ui/pdf_view.py (local implementation)
   - The local implementation might be overriding the main one
   - Need to ensure we're using the correct implementation

4. **Fix Implementation**
   a. Remove duplicate ImageCache class from pdf_view.py
   b. Import and use the main ImageCache implementation:
   ```python
   from .pdf_viewer.image_cache import ImageCache
   ```
   c. Update PDFViewport to use the imported ImageCache
   d. Add debug logging in the main ImageCache implementation

5. **Testing Steps**
   1. Select a stamp and change its color
   2. Check debug logs to verify:
      - Color selection is registered
      - Color is included in drag metadata
      - Color reaches the image cache
   3. Verify color is applied to stamp

## Root Cause
The local ImageCache implementation in pdf_view.py is likely overriding the main implementation that has the color tinting functionality. By removing the duplicate and using the main implementation, the color tinting should work as expected.