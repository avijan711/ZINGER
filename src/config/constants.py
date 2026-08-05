import os
from pathlib import Path

# Version
APP_VERSION = "2.0.1"

# Application paths
APP_DIR = Path(os.path.expanduser("~")) / ".pysign"
STAMPS_DIR = APP_DIR / "stamps"
SIGNATURES_DIR = APP_DIR / "signatures"

# File patterns
SUPPORTED_IMAGE_FORMATS = "*.png *.jpg *.jpeg"
SUPPORTED_PDF_FORMATS = "*.pdf"
SUPPORTED_DOCUMENT_FORMATS = "*.pdf *.docx *.doc"

# UI Constants
WINDOW_MIN_WIDTH = 1024
WINDOW_MIN_HEIGHT = 768
GALLERY_WIDTH = 300
TOOLBAR_ICON_SIZE = 24
STAMP_THUMBNAIL_SIZE = 80

# Default categories
DEFAULT_STAMP_CATEGORIES = ["General", "Signatures", "Custom"]