# MS Word Support — Design

**Date:** 2026-08-05
**Status:** Approved
**Branch:** feature/stamp-editing (or a new feature branch off it)

## Goal

Let users open, view, stamp/sign, save, and share Microsoft Word documents
(`.docx`, `.doc`) in PySign, in addition to PDFs.

## Decisions

- **Output:** signing a Word document produces **both** a signed PDF and a
  signed `.docx` copy (e.g. `contract_signed.pdf` + `contract_signed.docx`),
  written next to the original file.
- **Dependency:** Microsoft Word must be installed on the user's machine.
  Conversion and write-back use Word COM automation via pywin32 (already a
  dependency; same pattern as the existing Outlook sharing). If Word is
  missing, opening a Word file shows a clear error. No LibreOffice or
  pure-Python fallback.
- **Sharing:** "Share via Email" (Outlook) attaches **both** files.
  "Share Online" (WhatsApp) sends only the signed PDF (single-file flow).
- **Architecture:** a self-contained conversion layer in front of the
  existing, untouched PDF pipeline. No polymorphic document-handler
  refactor, no live Word session.

## User flow

1. User opens a `.docx`/`.doc` via the file dialog, drag-and-drop of a local
   file, or an Outlook attachment drop.
2. PySign converts it to a temporary PDF using the installed Word (COM),
   showing a wait cursor and status message during conversion (~1–3 s,
   synchronous).
3. The existing viewer/stamp/signature/sketch pipeline operates on that PDF
   unchanged.
4. On **Sign** (or Save), PySign writes:
   - `<name>_signed.pdf` — via the existing fitz save pipeline (exactly what
     the user saw on screen; the authoritative signed artifact), and
   - `<name>_signed.docx` — a copy of the original Word document with the
     same signature images placed at the same page positions.
5. Share via email attaches both files; WhatsApp and the drag-out source use
   the PDF.

## Components

### New: `src/core/word_document.py`

Self-contained Word COM wrapper. No Qt imports. Each operation creates its
own hidden Word instance (`Visible = False`, `DisplayAlerts = 0`) and quits
it in a `finally` block — no long-lived Word process.

- `is_word_available() -> bool` — whether `Word.Application` can be created
  (`win32com.client.Dispatch` succeeds).
- `convert_to_pdf(word_path: str, out_pdf_path: str) -> bool` — opens the
  document read-only and calls `ExportAsFixedFormat(..., wdExportFormatPDF)`.
  Because Word itself performs the layout, the exported PDF's pages and
  coordinates match the document 1:1 — both use points (1/72") with the
  origin at the top-left of the page. This is what makes exact write-back
  placement possible.
- `write_signatures_to_docx(word_path: str, out_docx_path: str, placements) -> bool`
  — `placements` is a list of `(page_number, x, y, width, height, png_bytes)`
  in PDF points. For each placement: navigate to the page with
  `Selection.GoTo(wdGoToPage, wdGoToAbsolute, page)` to obtain an anchor
  range on that page, write the PNG bytes to a temp file, then
  `Shapes.AddPicture(...)` as a floating shape with
  `RelativeHorizontalPosition`/`RelativeVerticalPosition` set to **page** and
  `Left/Top/Width/Height` from the placement. Wrap text = in front of text.
  Output is always saved as `.docx` (including for `.doc` input, avoiding
  compatibility-mode save prompts).
- COM threading: call `pythoncom.CoInitialize()`/`CoUninitialize()` around
  operations (operations run on the UI thread today, but this keeps the
  module safe if that changes).

### Changed: `src/core/pdf_handler.py`

Minimal, additive changes:

- `open_document(path)` detects `.docx`/`.doc` by extension. For Word files:
  convert to a temp PDF (in the system temp dir), open that with fitz, and
  store `self.source_word_path`. For PDFs, behavior is unchanged and
  `source_word_path` is `None`. Stale temp PDFs are removed on
  `close_document()` and on opening a new document.
- Extract the existing per-annotation logic in `save_document()` (bake
  rotation/opacity into a PNG, expand the rect to the rotated bounding box)
  into a helper that returns the final `(page, rect, png_bytes)` per
  annotation. Both the PDF save and the docx write-back consume this helper,
  guaranteeing identical images and positions in both outputs.
- `save_document(path)` — after the PDF saves successfully, if
  `source_word_path` is set, compute placements via the helper and call
  `write_signatures_to_docx(source_word_path, <pdf_path with .docx ext>, placements)`.
  Write-back failure is **non-fatal**: the PDF is the authoritative artifact;
  the failure is reported so the UI can show a warning rather than an error.
  Expose the produced paths (e.g. `self.last_saved_paths: list[str]`) so the
  UI and sharing can reference them.
- `get_signed_path()` — for Word-originated documents, derive the path from
  `source_word_path` (original folder + original base name + `_signed.pdf`)
  instead of the temp PDF's name.

### Changed: UI

- `src/config/constants.py`: add
  `SUPPORTED_DOCUMENT_FORMATS = "*.pdf *.docx *.doc"`; the open dialog uses
  it ("Documents (*.pdf *.docx *.doc)"). Save dialogs keep PDF naming (the
  docx copy is derived automatically).
- `src/ui/main_window.py` (`open_document`): wait cursor + status-bar
  message while a Word file converts. Error dialogs:
  - Word not installed → "Microsoft Word is required to open Word documents."
  - Conversion failure → clear error message.
  - Write-back failure on save → warning that the signed PDF was saved but
    the Word copy could not be written.
  `sign_document`'s status message lists both output files; the PDF drag-out
  source (`PDFDragSource`) continues to receive the signed PDF.
- `src/ui/pdf_viewer/drag_drop_handler.py`: accept `.docx`/`.doc` in the
  local-file and Outlook-attachment checks (extend the existing extension
  checks; same code paths — the handler already routes everything through
  `pdf_handler.open_document`, which now dispatches by extension). Outlook
  attachment temp files must preserve the original extension so dispatch
  works.

### Changed: `src/core/share_manager.py`

- `share_via_email(file_paths, subject, body)` accepts a list of attachment
  paths (a single `Attachments.Add` call per file). Callers pass both signed
  files for Word-originated documents, one for PDFs.
- `share_via_whatsapp` unchanged (single file — the signed PDF).

## Error handling summary

| Failure | Behavior |
| --- | --- |
| Word not installed | Error dialog on open; PDF-only functionality unaffected |
| Conversion fails (corrupt/protected doc) | Error dialog; nothing opens |
| Docx write-back fails | Warning; signed PDF is still saved and shareable |
| Temp PDF cleanup fails | Logged, ignored (temp dir) |

## Testing

Word COM cannot run in WSL/CI, so the split is:

- **pytest (mocked COM):** extension routing in `open_document`, placement
  computation from annotations (including rotation/opacity baking parity
  with the PDF save), `get_signed_path` for Word-originated docs, docx
  write-back invocation and non-fatal failure handling, temp-file cleanup,
  multi-attachment `share_via_email` argument handling.
- **Manual on Windows:** actual conversion fidelity, floating-image
  placement accuracy in the signed docx, `.doc` legacy input, Outlook
  attachment drop of a Word file. Same manual-verification status as the
  existing Outlook/WhatsApp integrations.

## Out of scope (YAGNI)

- LibreOffice or pure-Python conversion fallback.
- Editing Word text inside PySign.
- Keeping a live Word session open for the document.
- Writing sketch-overlay strokes back as vector shapes (they are baked into
  the stamp images already).
- Other Office formats (.rtf, .odt, .xlsx, …).
