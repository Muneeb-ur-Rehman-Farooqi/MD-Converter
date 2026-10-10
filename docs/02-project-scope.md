# MD Converter: Project Scope

Status: frozen on acceptance. Last updated: 2026-10-06.
Legend: CONFIRMED = decided by Muneeb. PROPOSED = recommendation. See the knowledge doc for the full legend.

---

## Scope rule

Anything not listed under a phase is out of scope. New ideas go to the parking lot (section 4) and are only reviewed after the current phase ships.

## 1. Phases

Easy work first. The math problem is last, as a separate problem.

### Phase 1: Core engine (no UI yet, testable from a script)

| ID | Feature | Done when |
|----|---------|-----------|
| F1 | PDF to MD (digital PDFs with a text layer) | A 300+ page PDF converts without crashing on 4 GB RAM, with headings, paragraphs, lists and tables kept sensibly |
| F2 | DOCX to MD | Headings, lists, tables and emphasis survive |
| F3 | MD to PDF | Output opens in any viewer, text selectable, readable layout |
| F4 | MD to DOCX (text only) | Opens in Word with headings and paragraphs correct |
| F5 | PDF to DOCX and DOCX to PDF (text only, routed through MD) | Both work with the same quality bar as F1 to F4 |
| F6 | Clean text extraction (neat plain text from any supported input) | Output has no broken lines or stray page artifacts |
| F7 | Math symbol baseline: Unicode math symbols that exist as real text (for example ∑, ∫, α, ≤) are preserved in every direction, and the PDF output uses a font that can show them | A test document with common symbols round-trips with no missing characters |

### Phase 2: App shell

| ID | Feature | Done when |
|----|---------|-----------|
| F8 | Clean, minimalistic UI | One main window, clear states (idle, working, done, error) |
| F9 | Drag and drop, plus a file picker | Dropping one or many supported files starts conversion |
| F10 | Batch conversion of multiple files or a folder | One bad file never stops the batch |
| F11 | Recent file activity and files worked on, stored locally | History survives restarts and shows source, result, time and status |
| F12 | Local space (library) for .md and .pdf files | User can see, open and re-convert stored files |
| F13 | Responsive during heavy work (background worker, progress, cancel) | The window never freezes |

### Phase 3: OCR and AI features

| ID | Feature | Done when |
|----|---------|-----------|
| F14 | English OCR for scanned PDFs and images | A scanned PDF becomes readable Markdown; scanned pages are detected automatically |
| F15 | Clipboard screenshots: OCR directly from an image on the clipboard | Screenshot, press a button, get the text |
| F16 | Token meter: tokens in raw extracted text vs final Markdown | Shows both numbers and the saving, labeled as an estimate |
| F17 | AI-optimized Markdown mode | Output trimmed for LLM use (rules in the architecture doc) and the meter shows the extra saving |

Note on OCR: Muneeb's notes say OCR will need its own working session. The engine is chosen by a bake-off on his own screenshots.

### Phase 4: Polish and release

| ID | Feature | Done when |
|----|---------|-----------|
| F18 | Packaging: Windows installer and portable build | Installs and runs on a clean Windows 10 machine without Python |
| F19 | Error handling and messages | Password-protected, corrupt, empty or huge files all produce a clear message |
| F20 | README, screenshots, license, GitHub release | A stranger can install and use it from the README alone |

### Phase 5: The Hard Problem (separate problem, built last)

Problem statement: recover mathematical equations from PDFs and Word files as LaTeX inside Markdown, and render LaTeX math in outputs, on a 4 GB, CPU-only machine.

This is a research-style problem. It is not part of the "must ship" promise for earlier phases. It plugs into a hook that already exists in the architecture, so the earlier phases do not need redesign.

Sub-problems, in order:

| ID | Sub-problem | Notes |
|----|-------------|-------|
| M1 | Build a test set: 20 to 30 real equations from Muneeb's own course PDFs, with the expected LaTeX | Run the select-and-paste test first. It tells us which equations are real text and which are images |
| M2 | Equations in the text layer: rebuild structure from font size, baseline and glyph position (superscripts, subscripts, big operators first; fractions later) | A known approach exists in open source; fractions and matrices are the hard part |
| M3 | Word equations: OMML to LaTeX, and LaTeX to OMML | Libraries exist for part of this; check coverage |
| M4 | Render LaTeX in MD to PDF output | HTML + KaTeX route |
| M5 | Equations stored as images: either a small CPU-friendly model or a clear placeholder strategy | Likely the hardest; decide after M1 to M4 |

Success is measured on the M1 test set: percentage of equations whose LaTeX is correct, and zero crashes.

## 2. Non-goals (not in this project)

- Non-English OCR (including Urdu) and handwriting.
- Formats beyond PDF, DOCX and MD (no PPTX, EPUB, XLSX).
- Mac and Linux.
- Cloud features, accounts, uploads.
- Pixel-perfect layout reproduction between formats.
- Editing PDFs or DOCX files.
- Any equation-image-to-LaTeX promise before Phase 5.

## 3. Constraints that shape every feature

- Windows 10, Intel i5 4th gen, 4 GB RAM, no dedicated GPU assumed.
- Fully offline.
- Public GitHub release: polish matters.

## 4. Parking lot (ideas not in scope, to review after a phase ships)

- Explorer right-click menu: "Convert to Markdown".
- Splitting large outputs into chunks by heading for context windows.
- Image extraction to a folder, or skipping images.
- Header, footer and page-number stripping beyond what F17 includes.
- Other OCR languages, Urdu in particular.
- PPTX and EPUB input.
- Folder watching (auto-convert new files).
- A Claude skill or plugin wrapper (note: a skill would run in Claude's cloud, not locally).
- Command-line mode for power users.
- Rebuilding fractions and matrices from PDF layout (belongs to M2, but kept here until M2 starts).

## 5. Scope change procedure

1. Write the idea in the parking lot with one line on why.
2. Finish the current phase.
3. At the phase boundary, decide: promote, keep parked, or drop.
4. A promoted idea gets an ID, a "done when" line, and a place in a phase before any code is written.
