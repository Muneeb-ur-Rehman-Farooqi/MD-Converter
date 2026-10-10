"""Detect the document format of a file and verify that its content matches."""

from __future__ import annotations

import zipfile
from pathlib import Path

from md_converter.core.errors import (
    CorruptFileError,
    FileLockedError,
    UnsupportedFormatError,
)
from md_converter.core.models import DocFormat

_EXTENSIONS: dict[DocFormat, str] = {
    DocFormat.PDF: ".pdf",
    DocFormat.DOCX: ".docx",
    DocFormat.MD: ".md",
}


def extension_for(fmt: DocFormat) -> str:
    """Return the canonical file extension for the given DocFormat."""
    return _EXTENSIONS[fmt]


def detect_format(path: Path) -> DocFormat:
    """Return the DocFormat for path, checking both extension and content.

    Raises UnsupportedFormatError for unknown extensions, CorruptFileError when
    the content does not match the claimed extension, and FileLockedError when
    the file cannot be opened because it is in use.
    """
    try:
        is_file = path.is_file()
    except PermissionError as exc:
        raise FileLockedError() from exc
    if not is_file:
        raise CorruptFileError(f"File could not be found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        fmt = DocFormat.PDF
    elif suffix == ".docx":
        fmt = DocFormat.DOCX
    elif suffix in (".md", ".markdown"):
        fmt = DocFormat.MD
    else:
        raise UnsupportedFormatError(
            f"Unsupported file extension '{path.suffix}'. "
            f"Supported extensions: .pdf, .docx, .md, .markdown."
        )

    try:
        if fmt is DocFormat.PDF:
            with path.open("rb") as handle:
                head = handle.read(1024)
            if b"%PDF-" not in head:
                raise CorruptFileError(
                    "This file is damaged or is not really a PDF file."
                )
        elif fmt is DocFormat.DOCX:
            # Password-protected DOCX files are not plain zip files; they will
            # simply fail the checks below. Proper detection is a later task.
            if not zipfile.is_zipfile(path):
                raise CorruptFileError(
                    "This file is damaged or is not really a DOCX file."
                )
            with zipfile.ZipFile(path) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise CorruptFileError(
                        "This file is damaged or is not really a DOCX file."
                    )
        elif fmt is DocFormat.MD:
            with path.open("rb") as handle:
                head = handle.read(8192)
            if b"\x00" in head:
                raise CorruptFileError(
                    "This file is damaged or is not really a Markdown file."
                )
    except PermissionError as exc:
        raise FileLockedError() from exc
    except zipfile.BadZipFile as exc:
        raise CorruptFileError(
            "This file is damaged and cannot be read as a DOCX file."
        ) from exc

    return fmt