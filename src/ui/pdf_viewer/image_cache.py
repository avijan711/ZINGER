"""Handles caching and scaling of images"""

from PyQt6.QtGui import QImage
from PIL import Image
from io import BytesIO
from functools import lru_cache
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

# Constants
MAX_CACHE_SIZE = 100

class ImageCache:
    """Handles caching of scaled images with LRU cache"""
    
    def __init__(self, max_size: int = MAX_CACHE_SIZE):
        """Initialize the image cache
        
        Args:
            max_size: Maximum number of images to cache
        """
        self._cache: Dict[Tuple, QImage] = {}
        self._max_size = max_size
        
    def get_scaled_image(self, image_data: bytes, width: int, height: int, color: str = None) -> QImage:
        """Get a scaled and optionally colored version of the image, using cache if available
        
        Args:
            image_data: Raw image data bytes
            width: Target width
            height: Target height
            color: Optional hex color string (e.g., '#ff0000' for red)
            
        Returns:
            Scaled and colored QImage
        """
        logger.debug(f"get_scaled_image called with color: {color}")
        try:
            # Create cache key
            cache_key = (image_data, width, height, color)
            
            # Check cache first
            if cache_key in self._cache:
                logger.debug(f"Cache hit for key: {cache_key}")
                return self._cache[cache_key]
            logger.debug(f"Cache miss for key: {cache_key}")
            
            # Scale image using Pillow for better quality
            with Image.open(BytesIO(image_data)) as img:
                # Convert to RGBA if needed
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                # Resize with high quality
                img = img.resize(
                    (width, height),
                    Image.Resampling.LANCZOS
                )
                
                # Only apply color tint if a custom color is specified (not the default black)
                if color and color.lower() != '#000000':
                    logger.debug(f"Applying custom color tint: {color} to non-white pixels")
                    try:
                        # Convert hex color to RGB
                        r = int(color[1:3], 16)
                        g = int(color[3:5], 16)
                        b = int(color[5:7], 16)
                        logger.debug(f"RGB values: r={r}, g={g}, b={b}")
                        
                        # Get image data as array
                        data = img.getdata()
                        new_data = []
                        
                        # Apply color to each pixel while preserving alpha
                        for item in data:
                            # Get alpha value from original pixel
                            alpha = item[3] if len(item) > 3 else 255
                            if alpha > 0:  # Only process non-transparent pixels
                                # Check if pixel is not white (allowing for some variation)
                                is_colored = not (item[0] > 240 and item[1] > 240 and item[2] > 240)
                                if is_colored:
                                    # Replace non-white pixels with selected color
                                    # Preserve relative darkness by scaling the color
                                    darkness = 1.0 - (sum(item[:3]) / (3 * 255))  # 0.0 to 1.0
                                    new_r = int(r * (1.0 - darkness * 0.5))  # Scale color by darkness
                                    new_g = int(g * (1.0 - darkness * 0.5))
                                    new_b = int(b * (1.0 - darkness * 0.5))
                                    new_data.append((new_r, new_g, new_b, alpha))
                                else:
                                    # Keep white pixels unchanged
                                    new_data.append(item)
                            else:
                                new_data.append((0, 0, 0, 0))  # Keep transparent pixels
                        
                        # Create new image with colored data
                        img.putdata(new_data)
                        logger.debug("Custom color tint applied successfully")
                    except Exception as e:
                        logger.error(f"Error applying color tint: {e}")
                else:
                    logger.debug("Using default stamp appearance (no custom color)")
                
                # Convert to QImage
                data = img.tobytes("raw", "RGBA")
                qimg = QImage(
                    data,
                    img.width,
                    img.height,
                    QImage.Format.Format_RGBA8888
                )
                
                # Cache the result
                self._cache[cache_key] = qimg
                
                # Maintain cache size
                if len(self._cache) > self._max_size:
                    self._cache.pop(next(iter(self._cache)))
                
                return qimg
                
        except Exception as e:
            logger.error(f"Error scaling image: {e}")
            return QImage()
            
    def clear(self) -> None:
        """Clear the image cache"""
        logger.debug("Clearing image cache")
        cache_size = len(self._cache)
        self._cache.clear()
        logger.debug(f"Cleared {cache_size} items from cache")