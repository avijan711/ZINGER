class PDFView(QGraphicsView):
    # ...existing code...

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or \
           event.mimeData().hasFormat('application/x-qt-windows-mime;value="FileGroupDescriptor"'):
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime_data = event.mimeData()
        file_path = None
        
        # Try Outlook drop first
        if mime_data.hasFormat('application/x-qt-windows-mime;value="FileGroupDescriptor"'):
            descriptor = mime_data.data('application/x-qt-windows-mime;value="FileGroupDescriptor"')
            from utils.outlook_handler import parse_outlook_descriptor
            file_path = parse_outlook_descriptor(descriptor)
            
        # If not Outlook or Outlook parsing failed, try regular drop
        if not file_path and mime_data.hasUrls():
            url = mime_data.urls()[0]
            file_path = url.toLocalFile()
            
        # Process the file if we got a valid path
        if file_path and Path(file_path).exists() and file_path.lower().endswith('.pdf'):
            self.load_pdf(file_path)
            event.acceptProposedAction()
        else:
            event.ignore()

    # ...existing code...
