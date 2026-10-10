# MD Converter: Architecture

Status: proposed design, pre-build. Last updated: 2026-10-06.
Legend: CONFIRMED = decided by Muneeb. PROPOSED = recommendation. VERIFY = needs checking.
Everything below is PROPOSED unless marked otherwise.

---

## 1. Design principles

1. **Engine first, UI second.** All conversion logic lives in a core package that never imports UI code. The UI is a thin layer on top, so the engine can be tested from a plain script.
2. **Markdown is the hub.** Every conversion goes through Markdown. We need only two readers (PDF, DOCX) and two writers (PDF, DOCX) plus the OCR reader, instead of one converter per pair.
3. **Stream, do not hoard.** The machine has 4 GB of RAM. Process one page at a time and release memory as we go.
4. **One bad file never kills a batch.** Errors are caught per file and reported.
5. **Math is a hook, not a rewrite.** A single math-handling stage exists from day one. It passes symbols through at first and is replaced in Phase 5.

## 2. Conversion routes

All routes are built from the same four building blocks.

- PDF to MD: PDF reader.
- DOCX to MD: DOCX reader.
- MD to PDF: PDF writer.
- MD to DOCX: DOCX writer.
- PDF to DOCX: PDF reader, then DOCX writer.
- DOCX to PDF: DOCX reader, then PDF writer.
- Scanned PDF or image to MD: OCR reader.

The trade-off: converting PDF to DOCX through Markdown loses layout detail. This matches the scope, which says text only.

## 3. The pipeline (one conversion, step by step)

1. **Ingest:** receive a file path or a clipboard image.
2. **Detect:** identify the file type. For PDFs, check page by page whether a text layer exists. Pages without one go to OCR.
3. **Read:** the matching reader produces raw text and Markdown structure. The raw extracted text is also kept for the token baseline.
4. **Transform stages, in order:**
   - cleanup (fix broken lines, hyphenation, odd whitespace)
   - math hook (default: keep Unicode symbols, mark equation images with a placeholder)
   - AI optimizer (only when AI mode is on)
5. **Write:** the chosen writer produces the output file.
6. **Record:** save the result to history, calculate the token numbers, show the result in the UI.

## 4. Package layout

```
md_converter/
  core/
    pipeline.py          runs the steps, isolates errors per file
    detect.py            file type, text layer per page
    readers/
      pdf_reader.py
      docx_reader.py
      ocr_reader.py
    writers/
      pdf_writer.py
      docx_writer.py
    transforms/
      cleanup.py
      math_hook.py       passthrough now, real logic in Phase 5
      ai_optimizer.py
  services/
    ocr.py               one interface, engine can be swapped
    tokens.py            token counting and savings
    storage.py           SQLite history and settings
    library.py           local space for .md and .pdf files
    clipboard.py         image from clipboard
  ui/
    main_window.py
    drop_zone.py
    workers.py           background threads
    history_view.py
  app.py                 entry point
  config.py
tests/
  fixtures/              sample PDFs, DOCX files, expected outputs
docs/
  01-project-knowledge.md
  02-project-scope.md
  03-project-architecture.md
```

## 5. Components in detail

**Readers.** PDF reader uses PyMuPDF-based extraction (VERIFY license). DOCX reader uses MarkItDown or mammoth. OCR reader renders a page to an image and calls the OCR service.

**Writers.** PDF writer: Markdown to HTML, with KaTeX for math, printed to PDF by a headless Chromium (VERIFY that Edge on Windows 10 works; fallback `reportlab`). DOCX writer: `python-docx` with `htmldocx`, text only.

**OCR service.** One function, `recognize(image) -> text`. The engine behind it (RapidOCR or Tesseract) is chosen by a bake-off on Muneeb's own screenshots, then fixed.

**Token service.** Baseline is the raw extracted text; result is the final Markdown. Counted with `tiktoken` (VERIFY offline bundling). Always labeled as an estimate.

**AI optimizer.** Candidate rules, finalized when Phase 3 starts:
- remove repeated headers, footers and page numbers
- collapse extra whitespace and blank lines
- normalize heading levels
- drop decorative images
- keep tables compact

**Storage.** SQLite database in `%APPDATA%\MDConverter\`:
- `history`: id, source path, output path, action, timestamp, status, tokens before, tokens after
- `settings`: simple key and value pairs
The library (local space for .md and .pdf) is a folder, by default under the user's Documents, with its index in the same database.

**Math hook.** Interface: takes a block of content, returns a block. Phase 1 behavior: leave real Unicode symbols alone, replace equation images with a visible placeholder. Phase 5 replaces the implementation without touching the rest of the pipeline.

## 6. UI layer (PySide6 proposed)

- One main window with a drop zone, a file list, a conversion type selector, a result panel with the token meter, and a recent files panel.
- A background worker thread runs conversions and sends progress, result and error signals to the UI.
- Cancel button stops after the current page.
- Clipboard button runs OCR on the clipboard image.

Alternative: CustomTkinter with `tkinterdnd2` for drag-and-drop. Smaller, simpler, less polished. Decision pending.

## 7. Memory and performance plan (4 GB RAM)

- Open PDFs lazily and process one page at a time.
- Only one heavy conversion runs at a time; batch files are queued.
- Render pages for OCR at a limited resolution and free the image right after.
- Write output incrementally for large files.
- Test with a deliberately large PDF early in Phase 1.

## 8. Error handling

Handled per file, with a message the user can understand:
- password-protected PDF
- corrupt or truncated file
- file with no extractable text (offer OCR in Phase 3)
- file too large for available memory
- output folder not writable
- file locked by another program

Every error is also written to a log file in `%APPDATA%\MDConverter\logs\`.

## 9. Testing

- `pytest` with fixture files in `tests/fixtures/`.
- Golden files: expected Markdown for a few known inputs, compared automatically.
- A math symbol fixture for F7.
- A large-file fixture for the memory goal.
- OCR bake-off script that compares engines on the same images.

## 10. Packaging and release (Phase 4)

- PyInstaller in folder mode (not single-file), to keep startup fast.
- A Windows installer built with a standard installer tool (Inno Setup is the usual choice; VERIFY).
- A portable zip build as well.
- Version number defined in one place.
- GitHub Releases for downloads.
- Expect a SmartScreen warning for unsigned builds. Mention it in the README.

## 11. Licensing (open decision)

The license depends on the dependency check. If the PDF engine is AGPL, the project must be released under a compatible license. Decide before the first public commit.

## 12. How Phase 5 plugs in

- The math hook is the only place equation logic is added.
- Readers expose "math candidate" regions (text blocks with math fonts, or images flagged as likely equations) so the hook can work on them.
- The PDF writer already uses KaTeX, so LaTeX in Markdown renders.
- The DOCX reader and writer gain OMML and LaTeX conversion in the same hook-style way.

## 13. Build order

1. Phase 1 in this order: F1, F6, F7, F3, F2, F4, F5. Test each before moving on.
2. Phase 2: UI shell around the working engine.
3. Phase 3: OCR, then the token meter, then AI mode.
4. Phase 4: packaging and polish.
5. Phase 5: the math problem.
