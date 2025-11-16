"""
Script to download custom icons for the toolbar
"""
import os
import requests
from pathlib import Path

# Icon URLs
ICONS = {
    'cloud_share': 'https://cdn-icons-png.flaticon.com/512/3222/3222791.png',
    'zoom_in': 'https://static-00.iconduck.com/assets.00/zoom-in-icon-2048x2048-nbqt9au8.png',
    'zoom_out': 'https://cdn-icons-png.flaticon.com/512/159/159096.png',
    'outlook': 'https://banner2.cleanpng.com/20180217/wfw/av14ctq39.webp'
}

def download_icon(url: str, filename: str):
    """Download an icon from URL and save it to assets/icons directory"""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Ensure the assets/icons directory exists
        icons_dir = Path(__file__).parent.parent / 'assets' / 'icons'
        icons_dir.mkdir(parents=True, exist_ok=True)
        
        # Save the icon
        icon_path = icons_dir / f"{filename}.png"
        with open(icon_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"Successfully downloaded {filename} icon")
        return True
    except Exception as e:
        print(f"Error downloading {filename} icon: {e}")
        return False

def main():
    """Download all icons"""
    success = True
    for name, url in ICONS.items():
        if not download_icon(url, name):
            success = False
    
    if success:
        print("\nAll icons downloaded successfully!")
    else:
        print("\nSome icons failed to download. Please check the errors above.")

if __name__ == '__main__':
    main()