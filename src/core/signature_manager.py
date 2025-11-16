import os
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import json
from PyQt6.QtCore import QObject, pyqtSignal
from io import BytesIO
import uuid

class SignatureManager(QObject):
    # Signals
    signature_added = pyqtSignal(str)  # signature_id
    signature_removed = pyqtSignal(str)  # signature_id
    signature_renamed = pyqtSignal(str, str)  # signature_id, new_name

    def __init__(self, storage_path: str):
        super().__init__()
        self.storage_path = Path(storage_path)
        self.signatures_dir = self.storage_path / "signatures"
        self.metadata_file = self.storage_path / "signatures_metadata.json"
        self.signatures: Dict[str, Dict] = {}
        
        # Initialize storage
        self._init_storage()

    def _init_storage(self):
        """Initialize signature storage"""
        # Create directories if they don't exist
        self.signatures_dir.mkdir(parents=True, exist_ok=True)
        
        # Load or create metadata
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    self.signatures = json.load(f)
            except Exception as e:
                print(f"Error loading signatures metadata: {e}")
                self.signatures = {}
        else:
            self.signatures = {}

    def _save_metadata(self):
        """Save signatures metadata"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.signatures, f, indent=2)
        except Exception as e:
            print(f"Error saving signatures metadata: {e}")

    def save_signature(self, image_data: bytes, name: str) -> Optional[str]:
        """Save a new signature"""
        try:
            # Generate unique ID
            signature_id = str(uuid.uuid4())
            
            # Save signature image
            signature_path = self.signatures_dir / f"{signature_id}.png"
            
            # Convert bytes to PIL Image and save
            with Image.open(BytesIO(image_data)) as img:
                img.save(signature_path, 'PNG')
            
            # Update metadata
            self.signatures[signature_id] = {
                'name': name,
                'file': str(signature_path),
                'created': datetime.now().isoformat()
            }
            
            # Save metadata
            self._save_metadata()
            
            # Emit signal
            self.signature_added.emit(signature_id)
            
            return signature_id
        except Exception as e:
            print(f"Error saving signature: {e}")
            return None

    def delete_signature(self, signature_id: str) -> bool:
        """Delete a signature"""
        if signature_id not in self.signatures:
            return False

        try:
            # Get signature info
            signature_info = self.signatures[signature_id]
            
            # Remove signature file
            signature_path = Path(signature_info['file'])
            if signature_path.exists():
                signature_path.unlink()
            
            # Update metadata
            del self.signatures[signature_id]
            
            # Save metadata
            self._save_metadata()
            
            # Emit signal
            self.signature_removed.emit(signature_id)
            
            return True
        except Exception as e:
            print(f"Error deleting signature: {e}")
            return False

    def rename_signature(self, signature_id: str, new_name: str) -> bool:
        """Rename a signature"""
        if signature_id not in self.signatures:
            return False

        try:
            # Update metadata
            self.signatures[signature_id]['name'] = new_name
            
            # Save metadata
            self._save_metadata()
            
            # Emit signal
            self.signature_renamed.emit(signature_id, new_name)
            
            return True
        except Exception as e:
            print(f"Error renaming signature: {e}")
            return False

    def get_signature_data(self, signature_id: str) -> Optional[Tuple[bytes, str]]:
        """Get signature image data and name"""
        if signature_id not in self.signatures:
            return None

        try:
            signature_info = self.signatures[signature_id]
            with open(signature_info['file'], 'rb') as f:
                return f.read(), signature_info['name']
        except Exception as e:
            print(f"Error reading signature data: {e}")
            return None

    def get_all_signatures(self) -> List[Dict]:
        """Get all signatures"""
        signatures = []
        for signature_id, info in self.signatures.items():
            signature_info = info.copy()
            signature_info['id'] = signature_id
            signatures.append(signature_info)
        return signatures

    def create_date_stamp(self, date: datetime = None) -> bytes:
        """Create a date stamp image"""
        try:
            if date is None:
                date = datetime.now()
            
            # Create image with transparent background
            img = Image.new('RGBA', (200, 50), (255, 255, 255, 0))
            draw = ImageDraw.Draw(img)
            
            # Add date text
            date_str = date.strftime("%Y-%m-%d")
            draw.text((10, 10), date_str, fill=(0, 0, 0, 255))
            
            # Convert to bytes
            img_bytes = BytesIO()
            img.save(img_bytes, format='PNG')
            return img_bytes.getvalue()
        except Exception as e:
            print(f"Error creating date stamp: {e}")
            return None

    def import_signature(self, path: str, name: str) -> Optional[str]:
        """Import a signature from an image file"""
        try:
            with open(path, 'rb') as f:
                image_data = f.read()
            return self.save_signature(image_data, name)
        except Exception as e:
            print(f"Error importing signature: {e}")
            return None