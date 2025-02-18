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
        
    @lru_cache(maxsize=MAX_CACHE_SIZE)
    def get_scaled_image(self, image_data: bytes, width: int, height: int) -> QImage:
        """Get a scaled version of the image, using cache if available
        
        Args:
            image_data: Raw image data bytes
            width: Target width
            height: Target height
            
        Returns:
            Scaled QImage
        """
        try:
            # Create cache key
            cache_key = (image_data, width, height)
            
            # Check cache first
            if cache_key in self._cache:
                return self._cache[cache_key]
            
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
        self._cache.clear()
        self.get_scaled_image.cache_clear()