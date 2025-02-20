"""
UI styling constants and color definitions for PySign
"""
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

# Color Scheme
PRIMARY_COLOR = "#2196F3"  # Blue - Main actions and highlights
SECONDARY_COLOR = "#757575"  # Gray - Secondary elements
ACCENT_COLOR = "#FF4081"  # Pink - Important actions like Sign
SUCCESS_COLOR = "#4CAF50"  # Green - Confirmation messages
WARNING_COLOR = "#FFC107"  # Amber - Warning messages
ERROR_COLOR = "#F44336"  # Red - Error messages

# Button Styles
SIGN_BUTTON_STYLE = """
    QToolButton[class="primary"] {
        background-color: """ + ACCENT_COLOR + """;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        font-weight: bold;
        min-width: 80px;
        margin: 0 5px;
    }
    QToolButton[class="primary"]:hover {
        background-color: #E91E63;
        transition: background-color 150ms;
    }
    QToolButton[class="primary"]:pressed {
        background-color: #C2185B;
    }
"""

TOOLBAR_STYLE = """
    QToolBar {
        background-color: white;
        border-bottom: 1px solid #E0E0E0;
        padding: 4px;
    }
    QToolButton {
        border: none;
        border-radius: 4px;
        padding: 4px;
        margin: 0 2px;
    }
    QToolButton:hover {
        background-color: #F5F5F5;
    }
    QToolButton:pressed {
        background-color: #E0E0E0;
    }
"""

# Drop Zone Styles
DROP_ZONE_STYLE = """
    QFrame#dragContainer {
        background-color: #F8F9FA;
        border: 2px dashed #DEE2E6;
        border-radius: 8px;
        padding: 16px;
        margin: 8px;
    }
    QFrame#dragContainer[dragActive="true"] {
        background-color: """ + PRIMARY_COLOR + """15;
        border-color: """ + PRIMARY_COLOR + """;
    }
"""

# Status Bar Style
STATUS_BAR_STYLE = """
    QStatusBar {
        background-color: #F8F9FA;
        border-top: 1px solid #DEE2E6;
        padding: 4px;
        color: """ + SECONDARY_COLOR + """;
    }
"""

# Animation Durations (in milliseconds)
HOVER_ANIMATION_DURATION = 150
FEEDBACK_ANIMATION_DURATION = 200

# Icon Sizes
TOOLBAR_ICON_SIZE = 24
LARGE_ICON_SIZE = 32