# MD Converter: Progress and Handoff

Status: environment ready, Prompt 1 skeleton built and passing (22 tests green), no pipeline or converter code yet. Last updated: 2026-10-10.
Owner: Muneeb. Companion docs: 01-project-knowledge.md, 02-project-scope.md, 03-project-architecture.md.
Where this doc and the older three disagree, THIS doc is newer and wins. Section 4 lists exactly what changed.

Legend: CONFIRMED = Muneeb decided or did it. PROPOSED = Claude's recommendation, not yet acted on. VERIFY = still unchecked.

---

## 1. How we work (rules for the next chat)

Roles:
- Claude = senior developer and teacher. Discusses architecture, explains concepts, writes prompts, reviews output.
- DeepSeek (or Gemini) = junior developer. Writes the code from Claude's prompts.
- Muneeb = architect-in-training and the person who runs everything. He is weak at hand-editing code.

Rules for every DeepSeek prompt:
1. Full-file rewrites only. No diffs, snippets, "..." or "rest unchanged".
2. State the exact file path for every file.
3. DeepSeek must print a LOGIC CHECK (problems it sees in the brief) before any code.
4. Include the real environment: Windows 10, PowerShell 5.1, Python 3.13.16, exact pinned library versions.
5. Never let any model guess a library version or API from memory. Versions come from a real `pip` run on Muneeb's machine.
6. DeepSeek may not add, upgrade or replace a library. If it thinks one is needed, it stops and asks.
7. One small feature per prompt, tested before the next ("test each before moving on").

Rules for Claude:
- Check every library against live sources (PyPI, official docs, real search) before it goes into a prompt, and say clearly what could not be verified. Training knowledge of library versions is stale.
- Answer every question in project terms: "Windows does X because Y, and in your project that's Z."
- Teach the Windows and Python application model as we go. The goal is understanding how Windows apps work, how Python builds them, how shipping works, and (later) how AI models tokenize and chunk text. Writing code is not the goal.
- Tone: friendly, casual, match Muneeb's energy, encourage questions. Prefers plain-text explanations over diagrams. He is on Android-app experience (two vibe-coded projects), so Android comparisons land well.
- Any new idea goes to the parking lot (see 02-project-scope.md), not into the current phase.

---

## 2. Environment (CONFIRMED, as of 2026-10-10)

- Windows 10, Intel i5 4th gen, 4 GB RAM, no dedicated GPU assumed. Everything offline.
- Shell: Windows PowerShell 5.1 (the blue one). Not PowerShell 7.
- Python 3.13.16, 64-bit, is the default. Python 3.11.3 is still installed beside it (safe to leave). `py -0p` lists both. Use `py -3.13` to pick one explicitly.
- Project root: C:\Dev\md_converter
- Virtual environment: C:\Dev\md_converter\.venv, built with `py -3.13 -m venv .venv`. (The first venv was 3.11 and was deleted and rebuilt, because a venv is tied to the Python that created it.)
- PowerShell ExecutionPolicy: RemoteSigned for CurrentUser (needed so `.venv\Scripts\Activate.ps1` runs).

Start of every work session:

    cd C:\Dev\md_converter
    .venv\Scripts\Activate.ps1

Activation lasts only for that one PowerShell window. Closing the window ends it. The prompt must start with `(.venv)`. Use `python -m pip ...` instead of bare `pip`, so the pip of the exact Python in use runs.

---

## 3. Library stack

### 3.1 Installed now (CONFIRMED), pinned in requirements.txt

Direct libraries:

| Library | Version | Used for |
|---|---|---|
| pymupdf | 1.28.2 | PDF reading (our own reader, F1) |
| python-docx | 1.2.0 | DOCX reading and writing |
| mammoth | 1.13.0 | DOCX to HTML (then to Markdown) |
| markdownify | 1.2.3 | HTML to Markdown |
| markdown-it-py | 4.2.0 | Markdown parser for the writers |
| pytest | 9.1.1 | tests |

Full pinned file (the transitive packages):

    beautifulsoup4==4.15.0
    cobble==0.1.4
    colorama==0.4.6
    iniconfig==2.3.1
    lxml==6.1.3
    mammoth==1.13.0
    markdown-it-py==4.2.0
    markdownify==1.2.3
    mdurl==0.1.2
    packaging==26.3
    pluggy==1.6.0
    Pygments==2.21.0
    pymupdf==1.28.2
    pytest==9.1.1
    python-docx==1.2.0
    six==1.17.0
    soupsieve==2.10
    typing_extensions==4.16.0

### 3.2 Install later, when the phase needs it

Results of a `pip install --dry-run` on this exact Python on 2026-10-09. They show every one of these has a Windows 64-bit build for Python 3.13. Re-run the dry-run before the real install, because versions move.

| Phase | Library | Version pip picked | Notes |
|---|---|---|---|
| 2 (UI) | PySide6-Essentials | 6.12.0 (+ shiboken6 6.12.0) | Only two packages. Do NOT install plain `PySide6`: it pulls in PySide6_WebEngine (embedded Chromium), which our 4 GB budget excludes. |
| 3 (OCR) | rapidocr | 3.10.0 | Pulls opencv-python-headless, numpy, pillow, shapely, pyclipper, omegaconf and others. |
| 3 (OCR) | onnxruntime | 1.31.0 | Install it explicitly: rapidocr 2.0.6 and later no longer install it for you. The old package `rapidocr_onnxruntime` is being retired. Models trained on old data will write the old name. Forbid it in prompts. |
| 3 (tokens) | tiktoken | 0.14.0 | VERIFY offline bundling of its encoding file. |
| 4 (release) | pyinstaller | 6.22.3 | Works with Python 3.8 to 3.15 per its docs. |
| fallback | reportlab | 5.0.1 | Only if the Edge-based PDF route fails (F3). |

### 3.3 Libraries we looked at and dropped (and why)

- pymupdf4llm. It auto-installs `pymupdf-layout`. Package-index data (depscope, April 2026 snapshot) lists pymupdf-layout as dual-licensed Polyform Noncommercial or Artifex commercial, which is not AGPL. One Gentoo packaging page tags it AGPL-3, so sources conflict, and the official license file was never opened. Treat it as noncommercial until proven otherwise. It also needs onnxruntime, which is heavy for 4 GB. Instead we write our own PDF reader on plain PyMuPDF (AGPL, accepted): headings from font size, tables from PyMuPDF's built-in table finder. That is the same machinery Phase 5 (equations) needs.
- markitdown. Dry-run showed it pulls magika, onnxruntime (resolved to 1.20.1, which would clash with RapidOCR's 1.31.0), sympy, beautifulsoup4 and requests. Too heavy and it creates a version conflict. Replaced by mammoth + markdownify.
- htmldocx. Version 0.0.6, last release August 2021, maintenance score zero. It works but is frozen. Replaced by python-docx driven directly by markdown-it-py.

### 3.4 Project license (CONFIRMED): AGPL-3.0

PyMuPDF is AGPL or commercial. We accept AGPL, so the project is released under AGPL-3.0. Before the first public commit: drop in the official AGPL-3.0 text from gnu.org. Never let an AI type a license from memory. Read PyMuPDF's current official licensing page once more at that time.

---

## 4. Architecture: what changed since 03-project-architecture.md

Everything in 03 still stands except:

1. Transforms are stream-to-stream, not per-chunk. Fixes like re-joining hyphenated words across a page break, or removing headers repeated on every page, need to see more than one page. A transform may keep a small window of recent chunks, never the whole document.
2. New files added to the layout: core/models.py (shared data types), core/errors.py (our error classes from section 8 of 03), core/readers/md_reader.py (so Markdown input follows the same reader to transforms to writer shape).
3. PDF reader is our own code on PyMuPDF (no pymupdf4llm). DOCX reader is mammoth + markdownify (no MarkItDown). DOCX writer is python-docx + markdown-it-py (no htmldocx). See 3.3.
4. No import side effects. Importing a module must never create folders, open files or configure logging. Folders and logging start only when a function is called on purpose.
5. Documents folder: the library default uses `Path.home()/"Documents"/"MDConverter"` for now. TODO(F12): Windows can redirect Documents (for example to OneDrive), so resolve it with the Known Folder API when the library feature is built.
6. Cancel and progress are plain Python callables and a `threading.Event`. No Qt in the engine.

### The engine contract (lives in core/models.py)

    DocFormat (str Enum): PDF="pdf", DOCX="docx", MD="md"
    ConversionStatus (str Enum): SUCCESS, FAILED, CANCELLED
    Chunk (frozen dataclass): index:int (1-based page/section), markdown:str, raw_text:str=""
    ConversionRequest: source:Path, target_format:DocFormat, output_dir:Path|None=None, ai_mode:bool=False
    ConversionResult: source, target_format, status, output_path=None, error_message="",
                      chunks_processed=0, tokens_before=None, tokens_after=None
    ProgressCallback = Callable[[int, int | None], None]

    reader:    read(path: Path) -> Iterator[Chunk]
    transform: apply(chunks: Iterable[Chunk]) -> Iterator[Chunk]
    writer:    write(chunks: Iterable[Chunk], output_path: Path, cancel: threading.Event | None = None) -> None
    pipeline:  convert(request, progress=None, cancel=None) -> ConversionResult
               Never raises. Every error becomes a FAILED result with a human-friendly message.

Error classes (core/errors.py): ConversionError (base, has .user_message) with PasswordProtectedError, CorruptFileError, NoTextLayerError, FileTooLargeError, OutputNotWritableError, FileLockedError, UnsupportedFormatError.

### Remaining decisions carried over from 01/02/03 (unchanged)

- OCR: English only. Engine chosen by a bake-off on Muneeb's own screenshots (RapidOCR first candidate, Tesseract the alternative).
- MD to PDF: HTML + KaTeX printed by headless Edge/Chromium. VERIFY that Edge on Windows 10 works for this. Fallback: reportlab.
- Token meter baseline: raw extracted text vs final Markdown, labeled an estimate.
- History in SQLite under %APPDATA%\MDConverter\. Packaging: PyInstaller folder mode + Inno Setup installer + portable zip. GitHub Releases. Unsigned builds will show SmartScreen warnings.
- Build order for Phase 1: F1, F6, F7, F3, F2, F4, F5. Then Phase 2 UI, Phase 3 OCR/tokens/AI mode, Phase 4 packaging, Phase 5 the math problem. Scope stays frozen.

---

## 5. What we have done

1. Read the three planning docs and agreed the working method.
2. Lesson Zero (see 7): how a Windows process, threads, the event loop and file locations work.
3. Environment: found Python 3.11.3, fixed ExecutionPolicy, built the venv, upgraded to Python 3.13.16 side by side, rebuilt the venv on 3.13.
4. Library research with live searches plus real `pip install --dry-run` runs on this machine. Dropped three libraries (3.3), chose PySide6-Essentials.
5. Installed the Phase 1 libraries and saved pinned versions to requirements.txt.
6. Designed the engine contracts (section 4).
7. Wrote Prompt 1 for DeepSeek (Appendix A) and the PowerShell command that creates the whole empty folder tree (Appendix B).

Prompt 1 result (DONE): DeepSeek's LOGIC CHECK found nothing blocking (it doubted the "unusual" patch version 3.13.16, which is real, and chose 1_048_576 bytes for the 1 MB log limit). All 9 files were pasted into the tree. With the venv active, `python -m pytest` reports 22 passed in 1.07s (Python 3.13.16, pytest 9.1.1, pluggy 1.6.0, configfile pytest.ini), and `python -m md_converter.app` prints "MD Converter 0.1.0 - the interface arrives in Phase 2." Gotcha hit on the way: running pytest in a fresh window without activating the venv uses the old system Python 3.11 and fails with "No module named pytest".

Not done yet: detect.py, pipeline.py, every reader, writer and transform other than math_hook, and everything in services/ and ui/. Those files exist but are empty.

---

## 6. Next steps

1. DONE: tree created, Prompt 1 run, 22 tests pass. (Appendices A and B are kept for the record. Do not re-run them: the files now have content.)
2. Prompt 2: core/detect.py (file type by extension plus magic bytes: PDF starts with `%PDF-`, DOCX is a zip containing `word/document.xml`) and core/pipeline.py (routing, per-file error isolation, cancel, progress), tested with fake readers and writers. Pipeline backbone first, real readers after.
3. Then feature prompts in order: F1 (PDF to MD, plus a deliberately large PDF early for the 4 GB memory goal), F6, F7, F3, F2, F4, F5. One feature per prompt, tested each time.
4. Housekeeping: update 03-project-architecture.md with section 4 of this doc, save the docs into C:\Dev\md_converter\docs\, set up git, add the official AGPL text.
5. Still open VERIFY: tiktoken offline bundling (Phase 3); Edge headless PDF printing on Windows 10 (F3); Known Folder API for Documents (F12); the select-and-paste equation test on a real course PDF (feeds M1).

---

## 7. Teaching ledger

Covered so far:
- What an .exe is (PE file), what happens at launch, DLLs and the Win32 API at an intro level.
- Process vs thread. Threads share their process's memory (so race conditions exist); processes are walled off. Many python.exe processes can run at once.
- The event loop and message queue. Why windows freeze: the UI thread is busy, and Windows marks the window "Not Responding" because that thread stopped picking up messages. Fix: a worker thread, reporting back by signals. Confirmed with two experiments.
- The GIL: threads buy responsiveness, not speed.
- Process lifecycle (the meaning of "Windows cycle" in the original notes): create, load, run, exit by clean exit code or crash. A crash can leave a half-written file, which is why we log and isolate errors per file.
- Where files live: Program Files (read-only for normal users), %APPDATA% (settings, history, logs), Documents (user files). Windows has no per-app sandbox like Android; any program can read your user folder.
- Classic desktop apps (our kind) have no OS-managed lifecycle like Android's. Modern Store apps can be suspended by Windows (Task Manager showed Settings as Suspended).
- Why PyInstaller and an installer are two separate layers (self-contained app folder, then polite installation).
- venv: version isolation, not "file organization". Python loads a library when it hits the `import`, not all at once.
- PowerShell: `where` is an alias, use `where.exe`. ExecutionPolicy. Activation lives per window. `>` writes UTF-16 in PowerShell 5.1, so use `Out-File -Encoding ascii` for requirements.txt.
- py launcher and side-by-side Pythons. Wheel filenames: `cp313` (CPython 3.13), `win_amd64` (Windows 64-bit, Intel too), `py3-none-any` (pure Python), `cp310-abi3` (stable ABI, works on 3.10 and newer). `pip --dry-run` as a truth test.
- Licenses in practice: AGPL, dual licensing, Polyform Noncommercial. Why import side effects are bad.

- Forgetting to activate the venv in a new window: a bare `python` then finds the old 3.11 on PATH, so pytest "is missing". pytest output shows `platform win32` even on 64-bit Windows (a historical Windows API name).

Offered but not asked yet: what a DLL really is; why Windows needs a message queue; why 4 GB RAM matters so much; why Program Files isn't writable.
Coming: Known Folders and OneDrive redirection, file locks and long paths, high-DPI blur, SmartScreen, PyInstaller folder vs one-file mode, Qt signals and threads in practice, then tokens and chunking in Phase 3.

Corrections Claude made along the way (so the new chat does not repeat them):
- `where` in PowerShell is not `where.exe`.
- "Windows has no app lifecycle" is true only for classic Win32 apps.
- Versions found by search were one step stale compared with what pip resolved (PySide6 6.11 vs 6.12.0, RapidOCR 2.x vs 3.10.0). Always trust the real pip output.
- A dry-run is cheap: pip fetches only small metadata files.

---

## Appendix A: Prompt 1 for DeepSeek (skeleton, contracts, config)

Paste the block below into DeepSeek. Then paste only the file CONTENTS (not the `FILE:` header lines) into the matching files in VS Code.

```text
ROLE
You are the junior developer on a Windows desktop project called MD Converter. I am the architect. You write code; you do not make architecture decisions. If anything in this brief looks wrong or contradictory, say so BEFORE writing code.

PROJECT
MD Converter is a Windows-only, fully offline tool that converts between PDF, DOCX and Markdown to prepare documents for LLMs. Engine first, UI second: nothing under md_converter/core may ever import UI code. Markdown is the hub format: every conversion is reader -> transforms -> writer, streaming one chunk (one page or section) at a time, because the target machine has only 4 GB RAM. One bad file must never crash a batch.

ENVIRONMENT (fixed)
- Windows 10, PowerShell 5.1, Python 3.13.16 (64-bit). Project root: C:\Dev\md_converter. Virtual environment: .venv (already active).
- Installed libraries, exact versions: pymupdf==1.28.2, python-docx==1.2.0, mammoth==1.13.0, markdownify==1.2.3, markdown-it-py==4.2.0, pytest==9.1.1 (plus their dependencies, see requirements.txt).
- THIS TASK USES ONLY THE PYTHON STANDARD LIBRARY AND PYTEST. Do not add, upgrade or replace any library. If you think one is needed, stop and ask me. Never guess a version number or an API from memory of older releases.

OUTPUT RULES (strict)
1. FULL FILES ONLY. For each file print a header line exactly like "FILE: md_converter\core\models.py" followed by the COMPLETE file contents in one code block. Never output diffs, partial snippets, "...", or "rest unchanged".
2. Write ONLY the 9 files listed below. All other files already exist as empty placeholders; do not create or mention them.
3. Before any code, print a section called LOGIC CHECK listing every contradiction, risk or missing detail you see in this brief. If none, write "none found". Only stop and ask if the problem blocks the work; otherwise note it and continue.
4. After the files, print a section called RUN IT with the exact commands to run from C:\Dev\md_converter (python -m pytest, and python -m md_converter.app) and the output I should expect.
5. Style: Python 3.13 syntax, type hints on every function, pathlib.Path for all paths, a short plain-English docstring on every module, class and function, no print() except in app.py, the standard logging module elsewhere. NO IMPORT SIDE EFFECTS: importing a module must never create folders, open files or configure logging.

FILES TO WRITE

1. md_converter\__init__.py
   Defines __version__ = "0.1.0". This is the one place the version number lives.

2. md_converter\core\models.py (standard library only)
   - DocFormat (str Enum): PDF="pdf", DOCX="docx", MD="md".
   - ConversionStatus (str Enum): SUCCESS="success", FAILED="failed", CANCELLED="cancelled".
   - Chunk (frozen dataclass): index: int (1-based page or section number); markdown: str; raw_text: str = "" (untouched extracted text, used later for the token baseline).
   - ConversionRequest (dataclass): source: Path; target_format: DocFormat; output_dir: Path | None = None (None means same folder as the source); ai_mode: bool = False.
   - ConversionResult (dataclass): source: Path; target_format: DocFormat; status: ConversionStatus; output_path: Path | None = None; error_message: str = "" (human-friendly text shown in the UI); chunks_processed: int = 0; tokens_before: int | None = None; tokens_after: int | None = None.
   - Type alias ProgressCallback = Callable[[int, int | None], None] (chunks done, total chunks or None if unknown).
   - A module docstring stating the engine contract that all later modules must follow:
       reader:    read(path: Path) -> Iterator[Chunk]
       transform: apply(chunks: Iterable[Chunk]) -> Iterator[Chunk]. A transform may keep a small window of recent chunks, because fixes such as hyphenation and repeated headers span pages, but must never hold the whole document.
       writer:    write(chunks: Iterable[Chunk], output_path: Path, cancel: threading.Event | None = None) -> None
       pipeline:  convert(request, progress=None, cancel=None) -> ConversionResult. It never raises: every error becomes a FAILED result.

3. md_converter\core\errors.py
   - ConversionError(Exception): constructor takes user_message: str, stores it as .user_message, and str(error) returns it.
   - Subclasses, each with its own default plain-English message that says what happened and what the user can do, and a constructor __init__(self, message: str | None = None) that uses the default when message is None: PasswordProtectedError, CorruptFileError, NoTextLayerError (default message must say scanned files need OCR, which is not available yet), FileTooLargeError, OutputNotWritableError, FileLockedError, UnsupportedFormatError.

4. md_converter\config.py (standard library only)
   - APP_NAME = "MDConverter".
   - get_app_data_dir() -> Path: <APPDATA>\MDConverter. Read the APPDATA environment variable at CALL time, never at import time. If it is missing, fall back to Path.home() / "AppData" / "Roaming".
   - get_logs_dir() -> Path (a "logs" folder inside the app data dir), get_db_path() -> Path ("history.db" inside the app data dir), get_default_library_dir() -> Path (Path.home() / "Documents" / "MDConverter"; add the comment: TODO(F12): Windows can redirect Documents, e.g. to OneDrive; resolve it properly with the Known Folder API when the library feature is built).
   - ensure_app_dirs() -> None: creates the app data dir and the logs dir (parents=True, exist_ok=True). It does NOT create the library dir.
   - setup_logging() -> None: configures the logger named "md_converter" at INFO level with a RotatingFileHandler (max 1 MB, 3 backups, utf-8) writing to <logs dir>\md_converter.log, with timestamp, level, logger name and message in each line. Calls ensure_app_dirs(). Calling it twice must NOT add duplicate handlers.

5. md_converter\app.py
   main() -> int prints "MD Converter <version> - the interface arrives in Phase 2." and returns 0. Bottom of file: if __name__ == "__main__": raise SystemExit(main()).

6. md_converter\core\transforms\math_hook.py
   Phase 1 behaviour is a passthrough. process_block(markdown: str) -> str returns its input unchanged. apply(chunks: Iterable[Chunk]) -> Iterator[Chunk] yields every chunk with markdown = process_block(chunk.markdown) (use dataclasses.replace). Docstring: Phase 5 will replace process_block only, nothing else in the pipeline changes.

7. tests\test_smoke.py (pytest, standard library only; each test small and named for what it proves)
   - the version is a non-empty string
   - Chunk is frozen (assigning to a field raises dataclasses.FrozenInstanceError)
   - ConversionRequest defaults: output_dir is None, ai_mode is False
   - every error class subclasses ConversionError, has a non-empty user_message, str(e) equals user_message, and a custom message overrides the default
   - config, using monkeypatch.setenv("APPDATA", str(tmp_path)): get_app_data_dir() equals tmp_path / "MDConverter"; nothing exists on disk until ensure_app_dirs() is called; afterwards the app data dir and logs dir exist
   - setup_logging() called twice leaves the logger's handler count unchanged after the second call, and writing one log message creates the log file. IMPORTANT: at the end of the test close and remove every handler you added, because on Windows an open log file blocks cleanup of the temp folder.
   - math_hook: process_block returns the identical string; apply returns equal chunks, using a test string with Unicode math symbols such as "∑ ∫ α ≤"
   - app.main() returns 0 and prints text containing the version (use capsys)

8. pytest.ini
   A [pytest] section with testpaths = tests and pythonpath = . (so tests can import md_converter from the project root).

9. .gitignore
   Standard Python and Windows entries plus: .venv/, __pycache__/, *.pyc, .pytest_cache/, build/, dist/, *.egg-info/, *.log, .vscode/, Thumbs.db, desktop.ini.
```

Why `pytest.ini` has `pythonpath = .`: Python only searches certain folders for imports. Without that line, `import md_converter` inside a test can fail with "No module named md_converter". The line adds the project root to the search list.

## Appendix B: create the empty tree (run from C:\Dev\md_converter, venv active)

    $files = @(
     "md_converter\__init__.py", "md_converter\app.py", "md_converter\config.py",
     "md_converter\core\__init__.py", "md_converter\core\models.py", "md_converter\core\errors.py",
     "md_converter\core\detect.py", "md_converter\core\pipeline.py",
     "md_converter\core\readers\__init__.py", "md_converter\core\readers\pdf_reader.py",
     "md_converter\core\readers\docx_reader.py", "md_converter\core\readers\md_reader.py",
     "md_converter\core\readers\ocr_reader.py",
     "md_converter\core\writers\__init__.py", "md_converter\core\writers\pdf_writer.py",
     "md_converter\core\writers\docx_writer.py",
     "md_converter\core\transforms\__init__.py", "md_converter\core\transforms\cleanup.py",
     "md_converter\core\transforms\math_hook.py", "md_converter\core\transforms\ai_optimizer.py",
     "md_converter\services\__init__.py", "md_converter\services\ocr.py",
     "md_converter\services\tokens.py", "md_converter\services\storage.py",
     "md_converter\services\library.py", "md_converter\services\clipboard.py",
     "md_converter\ui\__init__.py", "md_converter\ui\main_window.py",
     "md_converter\ui\drop_zone.py", "md_converter\ui\workers.py", "md_converter\ui\history_view.py",
     "tests\test_smoke.py", "pytest.ini", ".gitignore"
    )
    $files | ForEach-Object { New-Item -ItemType File -Force -Path $_ | Out-Null }
    New-Item -ItemType Directory -Force -Path tests\fixtures, docs | Out-Null

Only 9 of these files get content from Prompt 1: md_converter\__init__.py, config.py, app.py, core\models.py, core\errors.py, core\transforms\math_hook.py, tests\test_smoke.py, pytest.ini, .gitignore. The rest stay empty placeholders until their own feature prompt.
