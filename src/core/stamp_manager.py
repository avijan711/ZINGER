import os
import json
import shutil
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal
import uuid

class StampManager(QObject):
    # Signals
    stamp_added = pyqtSignal(str, str)  # stamp_id, category
    stamp_removed = pyqtSignal(str)  # stamp_id
    stamp_renamed = pyqtSignal(str, str)  # stamp_id, new_name
    stamp_color_changed = pyqtSignal(str, str)  # stamp_id, new_color
    category_added = pyqtSignal(str)  # category
    category_removed = pyqtSignal(str)  # category

    def __init__(self, storage_path: str):
        super().__init__()
        self.storage_path = Path(storage_path)
        self.stamps_dir = self.storage_path / "stamps"
        self.metadata_file = self.storage_path / "stamps_metadata.json"
        self.stamps: Dict[str, Dict] = {}  # stamp_id -> stamp_info
        self.categories: Dict[str, List[str]] = {}  # category -> [stamp_ids]
        
        # Initialize storage
        self._init_storage()
        
    def _init_storage(self):
        """Initialize the stamp storage directory and metadata"""
        # Create directories if they don't exist
        self.stamps_dir.mkdir(parents=True, exist_ok=True)
        
        # Load or create metadata
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    data = json.load(f)
                    self.stamps = data.get('stamps', {})
                    self.categories = data.get('categories', {})
            except Exception as e:
                print(f"Error loading stamps metadata: {e}")
                self.stamps = {}
                self.categories = {}
        
        # Ensure "General" category exists
        if "General" not in self.categories:
            self.categories["General"] = []
            self.category_added.emit("General")

    def _save_metadata(self):
        """Save stamps metadata to file"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump({
                    'stamps': self.stamps,
                    'categories': self.categories
                }, f, indent=2)
        except Exception as e:
            print(f"Error saving stamps metadata: {e}")

    def import_stamp(self, path: str, name: str, category: str = "General") -> Optional[str]:
        """Import a stamp from an image file"""
        try:
            # Ensure category exists
            if category not in self.categories:
                self.add_category(category)

            # Generate unique ID
            stamp_id = str(uuid.uuid4())
            
            # Process and save image
            with Image.open(path) as img:
                # Convert to RGBA if needed
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                # Get original dimensions
                width, height = img.size
                
                # Save processed image
                stamp_path = self.stamps_dir / f"{stamp_id}.png"
                img.save(stamp_path, 'PNG')

            # Update metadata
            self.stamps[stamp_id] = {
                'name': name,
                'category': category,
                'file': str(stamp_path),
                'original_width': width,
                'original_height': height,
                'aspect_ratio': width / height,
                'color': '#000000'  # Default black color
            }
            self.categories[category].append(stamp_id)
            
            # Save changes
            self._save_metadata()
            
            # Emit signal
            self.stamp_added.emit(stamp_id, category)
            
            return stamp_id
        except Exception as e:
            print(f"Error importing stamp: {e}")
            return None

    def delete_stamp(self, stamp_id: str) -> bool:
        """Delete a stamp"""
        if stamp_id not in self.stamps:
            return False

        try:
            # Get stamp info
            stamp_info = self.stamps[stamp_id]
            category = stamp_info['category']
            
            # Remove stamp file
            stamp_path = Path(stamp_info['file'])
            if stamp_path.exists():
                stamp_path.unlink()
            
            # Update metadata
            self.categories[category].remove(stamp_id)
            del self.stamps[stamp_id]
            
            # Save changes
            self._save_metadata()
            
            # Emit signal
            self.stamp_removed.emit(stamp_id)
            
            return True
        except Exception as e:
            print(f"Error deleting stamp: {e}")
            return False

    def rename_stamp(self, stamp_id: str, new_name: str) -> bool:
        """Rename a stamp"""
        if stamp_id not in self.stamps:
            return False

        try:
            # Update metadata
            self.stamps[stamp_id]['name'] = new_name
            
            # Save changes
            self._save_metadata()
            
            # Emit signal
            self.stamp_renamed.emit(stamp_id, new_name)
            
            return True
        except Exception as e:
            print(f"Error renaming stamp: {e}")
            return False

    def update_stamp_color(self, stamp_id: str, color: str) -> bool:
        """Update a stamp's color"""
        if stamp_id not in self.stamps:
            return False

        try:
            # Update metadata
            self.stamps[stamp_id]['color'] = color
            
            # Save changes
            self._save_metadata()
            
            # Emit signal
            self.stamp_color_changed.emit(stamp_id, color)
            
            return True
        except Exception as e:
            print(f"Error updating stamp color: {e}")
            return False

    def add_category(self, category: str) -> bool:
        """Add a new category"""
        if category in self.categories:
            return False

        try:
            self.categories[category] = []
            self._save_metadata()
            self.category_added.emit(category)
            return True
        except Exception as e:
            print(f"Error adding category: {e}")
            return False

    def remove_category(self, category: str) -> bool:
        """Remove a category and optionally move its stamps"""
        if category not in self.categories or category == "General":
            return False

        try:
            # Move stamps to General category
            stamps_to_move = self.categories[category].copy()
            for stamp_id in stamps_to_move:
                if stamp_id in self.stamps:
                    self.stamps[stamp_id]['category'] = "General"
                    self.categories["General"].append(stamp_id)
            
            # Remove category
            del self.categories[category]
            
            # Save changes
            self._save_metadata()
            
            # Emit signal
            self.category_removed.emit(category)
            
            return True
        except Exception as e:
            print(f"Error removing category: {e}")
            return False

    def get_stamp_data(self, stamp_id: str) -> Optional[Tuple[bytes, str, Dict]]:
        """Get stamp image data, name, and metadata"""
        if stamp_id not in self.stamps:
            return None

        try:
            stamp_info = self.stamps[stamp_id]
            with open(stamp_info['file'], 'rb') as f:
                return f.read(), stamp_info['name'], {
                    'original_width': stamp_info.get('original_width', 100),
                    'original_height': stamp_info.get('original_height', 100),
                    'aspect_ratio': stamp_info.get('aspect_ratio', 1.0),
                    'color': stamp_info.get('color', '#000000')
                }
        except Exception as e:
            print(f"Error reading stamp data: {e}")
            return None

    def get_stamps_by_category(self, category: str) -> List[Dict]:
        """Get all stamps in a category"""
        if category not in self.categories:
            return []

        stamps = []
        for stamp_id in self.categories[category]:
            if stamp_id in self.stamps:
                stamp_info = self.stamps[stamp_id].copy()
                stamp_info['id'] = stamp_id
                stamps.append(stamp_info)
        
        return stamps

    def get_categories(self) -> List[str]:
        """Get all categories"""
        return list(self.categories.keys())