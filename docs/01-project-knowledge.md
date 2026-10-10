# MD Converter: Project Knowledge

Status: planning complete, build not started. Last updated: 2026-10-06.
Owner: Muneeb.

Legend used across all three docs:
- **CONFIRMED** = Muneeb decided it.
- **PROPOSED** = Claude's recommendation, not yet confirmed.
- **VERIFY** = a claim from research that must be checked before relying on it.

---

## 1. What this project is

A Windows-only, fully local desktop tool that converts between PDF, DOCX and Markdown, built to prepare documents for LLMs. No uploads, no file-size limits, no internet needed. It will be published on GitHub as a polished open-source product.

## 2. Why it exists

- Free online converters reject large PDFs.
- Markdown is compact, structured text, so an LLM spends far fewer tokens on it than on raw PDF content.
- A local tool removes the size limit and keeps course material private.

## 3. Goals

Product goals:
- Convert PDF, DOCX and Markdown between each other (see scope doc for the exact list).
- Show how many tokens a conversion saves.
- Offer an AI-optimized Markdown mode.
- Ship as a normal Windows installer with a clean, minimal UI.

Learning goals (from Muneeb's notes):
- Learn Windows architecture and the software architecture that matters for Windows apps.
- Learn the development lifecycle concepts and apply them throughout. (The notes say "Windows cycle"; meaning to be clarified. Probably the software development lifecycle.)
- Whenever a question comes up mid-project, answer it in project terms. Example: "Windows software needs file X because of Y, and here it is Z in your project."
- Practice planning first: lock scope, research the stack, write the design, then build.
- Treat the math problem as a real problem-solving exercise at the end.

## 4. Constraints

- OS: Windows 10 (CONFIRMED).
- CPU: Intel i5, 4th generation (CONFIRMED).
- RAM: 4 GB (CONFIRMED).
- No dedicated GPU assumed.
- Everything runs offline.
- OCR language: English only (CONFIRMED).
- Audience: public GitHub release, so it needs polish: clear errors, an installer, a README (CONFIRMED).

These constraints rule out heavy ML document tools and web-engine-based UI frameworks (see section 6).

## 5. Key concepts (glossary)

- **Text layer:** real, selectable text inside a PDF. If you can select and copy text, the layer exists. Extraction from it is fast and accurate.
- **Scanned PDF:** pages stored as images with no text layer. Needs OCR.
- **OCR:** optical character recognition, turning an image of text into text.
- **Token:** the unit an LLM counts. Fewer tokens for the same content means cheaper and more fits in the context window. Counts differ per model, so any counter here is an approximation.
- **Markdown (MD):** plain-text format with light structure (headings, lists, tables). The hub format of this project.
- **LaTeX / KaTeX:** a notation for math (`$x^2$`) and a fast renderer for it.
- **OMML:** the format Word uses internally for equations.
- **PyInstaller:** packs a Python app and its libraries into an .exe so users do not need Python.
- **Worker thread:** a background thread that does heavy work so the window never freezes.

## 6. Research findings (researched 2026-10-06)

PDF to Markdown:
- PyMuPDF-based extraction (`pymupdf4llm`) runs on CPU with no ML models and is fast on digital PDFs.
- MarkItDown (Microsoft, MIT) is fast and shallow. It keeps math as Unicode symbols and skips equations stored as images.
- Docling (IBM, MIT) works on CPU but is much slower in one comparison (41 s vs 0.6 s for MarkItDown).
- Marker is accurate but GPU-oriented. Its CPU mode took minutes per document, its CPU-only no-OCR mode skips equations and scanned pages, and its best install is around 2 GB with PyTorch. Too heavy for this machine.
- License VERIFY: a third-party README says PyMuPDF and `pymupdf4llm` are AGPL v3, and newer `pymupdf4llm` versions also install a layout package under a noncommercial license. Check the official licensing before committing.

DOCX:
- MarkItDown wraps `mammoth` and friends for DOCX to MD.
- Word equations (OMML) can be converted to LaTeX by dedicated tools such as `eqword2llm`.
- `python-docx` plus `htmldocx` can write DOCX and one project shows native Word equations from LaTeX are possible.

Markdown to PDF:
- Pandoc needs a LaTeX engine or an alternative engine and is a large external install. Not preferred.
- HTML + KaTeX printed by headless Chromium is a proven approach. VERIFY: Microsoft Edge (Chromium) on Windows 10 can fill this role without bundling a browser.
- Fallback: pure-Python `reportlab`, with math embedded as images.

OCR (English, CPU):
- Tesseract: about 10 MB, roughly 0.8 to 1 s per page, needs its binary bundled.
- RapidOCR: about 50 to 80 MB, 0.5 to 1 s per page, pip-installable, uses ONNX Runtime.
- EasyOCR and PaddleOCR depend on heavy frameworks and are slower on CPU. Out.
- Benchmarks disagree on accuracy, so decide with a bake-off on Muneeb's own screenshots.

UI:
- CustomTkinter: small executables (roughly 5 to 10 MB for simple apps), drag-and-drop via `tkinterdnd2`.
- PySide6 (Qt Widgets): roughly 30 to 50 MB for a simple app and more in an installer, but built-in drag-and-drop, clipboard images and a more polished look.
- Avoid Electron and Qt WebEngine on 4 GB RAM.

Other:
- Recent files: Python's built-in `sqlite3`.
- Token counting: `tiktoken`. VERIFY: it downloads its encoding file on first use, so it must be bundled for offline use.

## 7. Decisions log

CONFIRMED by Muneeb:
1. Windows-only.
2. Input and output: PDF, DOCX and Markdown (DOCX works in both directions; DOCX output is text only).
3. English-only OCR.
4. Token meter baseline: raw text extracted from the source vs the final cleaned Markdown.
5. Public GitHub release, polished.
6. Scope is frozen once the scope doc is accepted. New ideas go in the parking lot.
7. The math problem is separate and comes last.

PROPOSED, awaiting confirmation:
1. Python for all logic.
2. Markdown as the hub format (all conversions route through it).
3. PySide6 for the UI (alternative: CustomTkinter).
4. RapidOCR as the first OCR candidate, Tesseract as the alternative.
5. HTML + KaTeX via Edge/Chromium for MD to PDF.
6. SQLite for history.
7. License choice, after the AGPL check.

## 8. Open questions

1. PySide6 or CustomTkinter?
2. Is AGPL acceptable for the project license?
3. Run the select-and-paste test on an equation in a course PDF. Symbols appear in Notepad: the equation is real text. Garbage or nothing: it is an image.
4. What does "Windows cycle" in the notes mean?
5. Verify the items marked VERIFY above.

## 9. Windows concepts this project will touch

Short list, to be expanded as the project teaches them:
- `%APPDATA%` and `Documents`: where an app should store settings, history and user files.
- Bundled runtimes: why an installed app needs the Visual C++ runtime or why PyInstaller packs its own copy of Python.
- Unsigned executables: Windows SmartScreen warns users about unsigned downloads. Expect this on GitHub releases. VERIFY details later.
- High-DPI scaling: why UIs look blurry on some screens.
- File locks and long paths: why a file can fail to open or save.

## 10. Working method

- Order of work: scope, research, design, build.
- Parking lot: any new idea mid-build goes in the parking lot and is not touched until the current phase ships.
- Hybrid workflow with Gemini: Claude plans and writes the prompt and instructions, Gemini writes the code. Rules from the notes: full-file rewrites only, always state the file path, and propose any logic problem found before writing the code. (More instructions on tone and the hybrid approach are coming from Muneeb and will be added here.)
