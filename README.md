# PySign - PDF Signing Application
Version 0.2

PySign is a powerful PDF signing application that allows users to digitally stamp and annotate PDF documents. Built with Python and PyQt6, it provides a modern, user-friendly interface for managing digital signatures and stamps.

## Features

- **PDF Document Handling**
  - Open and preview PDF files
  - Page navigation controls
  - Zoom and fit-to-window options
  - Display current page number and total pages

- **Digital Stamp Management**
  - Gallery view for available stamps
  - Import new stamps (PNG/JPG with transparency)
  - Delete/rename existing stamps
  - Custom stamp organization into categories

- **Stamping Features**
  - Drag & drop stamps onto PDF
  - Resize and rotate stamps
  - Customize stamp colors
  - Reset stamps to default color
  - Multi-stamp support
  - Undo/redo functionality

- **Document Signing**
  - Draw signature on canvas
  - Import signature image
  - Save signatures for reuse
  - Date stamp insertion

- **Sharing Capabilities**
  - Save modified PDF locally
  - Direct integration with Outlook
  - WhatsApp sharing support
  - Quick export options

## Requirements

- Python 3.11 or higher
- PyQt6
- PyMuPDF (fitz)
- Pillow
- Additional dependencies listed in requirements.txt

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/pysign.git
cd pysign
```

2. Create a virtual environment (optional but recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the application:
```bash
python src/main.py
```

2. Using the application:
   - Click "Open" to load a PDF document
   - Use the toolbar for navigation and zoom controls
   - Drag stamps from the gallery onto the PDF
   - Click "Signature" to open the signature pad
   - Save your work using the "Save" button

## Directory Structure

```
PySign/
├── src/
│   ├── main.py                 # Application entry point
│   ├── config/
│   │   ├── settings.py         # Application settings
│   │   └── constants.py        # UI constants, paths, etc.
│   ├── core/
│   │   ├── pdf_handler.py      # PDF operations
│   │   ├── stamp_manager.py    # Stamp CRUD operations
│   │   └── signature_store.py  # Signature management
│   └── ui/
│       ├── main_window.py      # Main application window
│       ├── pdf_view.py         # PDF viewing widget
│       ├── stamp_gallery.py    # Stamp gallery sidebar
│       └── dialogs/
│           └── signature_pad.py # Signature creation dialog
├── resources/
│   ├── stamps/                 # Default stamps
│   └── icons/                  # UI icons
└── requirements.txt
```

## Storage Locations

- Stamps are stored in: `~/.pysign/stamps/`
- Signatures are stored in: `~/.pysign/signatures/`
- Configuration files in: `~/.pysign/config/`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- PyQt6 for the GUI framework
- PyMuPDF for PDF handling
- Pillow for image processing