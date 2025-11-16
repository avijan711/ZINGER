"""Handles drag and drop operations for PDF files"""

from PyQt6.QtCore import Qt, QTemporaryFile
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# MIME types for PDF files
PDF_MIME_TYPES = [
    "application/pdf",
    "application/x-pdf",
    "application/acrobat",
    "application/vnd.pdf",
    "text/pdf",
    "text/x-pdf",
    "application/x-acrobat",
    "application/vnd.adobe.pdf",
    "application/vnd.adobe.acrobat",
    "application/force-download",
]

class DragDropHandler:
    """Handles drag and drop operations for PDF files"""
    
    def __init__(self, pdf_handler):
        self.pdf_handler = pdf_handler
        
    def handle_drag_enter(self, event: QDragEnterEvent) -> None:
        """Handle drag enter events"""
        mime_data = event.mimeData()
        
        # Handle Outlook attachments
        if self._check_outlook_attachment(mime_data):
            event.acceptProposedAction()
            return
        
        # Handle URLs
        if mime_data.hasUrls():
            for url in mime_data.urls():
                if url.isLocalFile() and url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction()
                    return
            
        # Handle PDF MIME types
        for mime_type in PDF_MIME_TYPES:
            if mime_data.hasFormat(mime_type):
                event.acceptProposedAction()
                return
                
        event.ignore()
        
    def handle_drop(self, event: QDropEvent) -> bool:
        """Handle drop events"""
        try:
            mime_data = event.mimeData()
            
            # Handle Outlook attachments
            outlook_data = self._get_outlook_data(mime_data)
            if outlook_data:
                filename, file_contents = outlook_data
                if filename.lower().endswith('.pdf'):
                    if self._save_and_open_temp_file(file_contents):
                        event.acceptProposedAction()
                        return True
            
            # Handle file drops
            if mime_data.hasUrls():
                for url in mime_data.urls():
                    if url.isLocalFile():
                        file_path = url.toLocalFile()
                        if file_path.lower().endswith('.pdf'):
                            if self.pdf_handler.open_document(file_path):
                                event.acceptProposedAction()
                                return True
            
            # Handle raw PDF data
            for mime_type in PDF_MIME_TYPES:
                if mime_data.hasFormat(mime_type):
                    data = mime_data.data(mime_type)
                    if data and self._save_and_open_temp_file(data):
                        event.acceptProposedAction()
                        return True
            
            event.ignore()
            return False
            
        except Exception as e:
            logger.error(f"Error handling drop event: {e}")
            event.ignore()
            return False
            
    def _check_outlook_attachment(self, mime_data) -> bool:
        """Check if mime data contains a valid Outlook PDF attachment"""
        if not mime_data.hasFormat("application/x-qt-windows-mime;value=\"FileGroupDescriptorW\""):
            return False
            
        try:
            # Get raw bytes from QByteArray
            descriptor_data = mime_data.data("application/x-qt-windows-mime;value=\"FileGroupDescriptorW\"").data()
            # Skip first 76 bytes of descriptor to get to filename
            filename_bytes = descriptor_data[76:]
            # Convert bytes to string, stopping at first null character
            filename = ""
            for i in range(0, len(filename_bytes), 2):
                if filename_bytes[i:i+2] == b'\x00\x00':
                    break
                if i+1 < len(filename_bytes):
                    char_bytes = bytes([filename_bytes[i], filename_bytes[i+1]])
                    try:
                        filename += char_bytes.decode('utf-16-le')
                    except:
                        break
            return filename.lower().endswith('.pdf')
        except Exception as e:
            logger.error(f"Error checking Outlook attachment: {e}")
            return False
            
    def _get_outlook_data(self, mime_data) -> Optional[Tuple[str, bytes]]:
        """Get filename and contents from Outlook attachment"""
        try:
            if not mime_data.hasFormat("application/x-qt-windows-mime;value=\"FileGroupDescriptorW\""):
                return None
                
            # Get raw bytes from QByteArray objects
            descriptor_data = mime_data.data("application/x-qt-windows-mime;value=\"FileGroupDescriptorW\"").data()
            file_contents = mime_data.data("application/x-qt-windows-mime;value=\"FileContents\"").data()
            
            if not descriptor_data or not file_contents:
                return None
                
            # Extract filename from descriptor
            filename_bytes = descriptor_data[76:]
            filename = ""
            for i in range(0, len(filename_bytes), 2):
                if filename_bytes[i:i+2] == b'\x00\x00':
                    break
                if i+1 < len(filename_bytes):
                    char_bytes = bytes([filename_bytes[i], filename_bytes[i+1]])
                    try:
                        filename += char_bytes.decode('utf-16-le')
                    except:
                        break
                        
            return filename, file_contents
            
        except Exception as e:
            logger.error(f"Error getting Outlook data: {e}")
            return None
            
    def _save_and_open_temp_file(self, data: bytes) -> bool:
        """Save data to temporary file and open it"""
        try:
            temp_file = QTemporaryFile()
            if temp_file.open():
                temp_file.write(data)
                temp_file.close()
                return self.pdf_handler.open_document(temp_file.fileName())
        except Exception as e:
            logger.error(f"Error saving temporary file: {e}")
            return False