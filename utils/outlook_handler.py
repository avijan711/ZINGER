import struct
from pathlib import Path

def parse_outlook_descriptor(data):
    """Parse Outlook's specific file drop descriptor format."""
    try:
        if isinstance(data, bytes):
            # Outlook descriptor format starts with specific markers
            if len(data) > 16:
                # Skip header bytes and try to extract filename
                # Outlook uses UTF-16-LE encoding for the filename
                filename_start = data.find(b'\x00\x00\x00\x00', 16) + 4
                if filename_start > 4:
                    filename_bytes = data[filename_start:]
                    # Extract until we hit null bytes
                    filename_end = filename_bytes.find(b'\x00\x00')
                    if filename_end > 0:
                        filename = filename_bytes[:filename_end].decode('utf-16-le')
                        # Convert to regular Windows path
                        return str(Path(filename))
        return None
    except Exception:
        return None
