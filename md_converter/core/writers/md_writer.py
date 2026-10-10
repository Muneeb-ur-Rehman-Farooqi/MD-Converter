"""Markdown writer for the MD Converter pipeline."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from pathlib import Path

from md_converter.core.models import Chunk

logger = logging.getLogger(__name__)


def write(
    chunks: Iterable[Chunk],
    output_path: Path,
    cancel: threading.Event | None = None,
) -> None:
    """Stream chunks to output_path as a UTF-8 Markdown file.

    Chunks are written one at a time (never materialised). Empty or
    whitespace-only chunks are skipped. Non-empty chunks are separated by
    exactly one blank line and the file finishes with a single newline,
    even when the writer stops because of cancel. Nothing is inferred from
    the output extension.
    """
    written = 0
    # newline="\n" keeps LF line endings on Windows: without it, text mode
    # would translate every "\n" into "\r\n".
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            if cancel is not None and cancel.is_set():
                break
            text = chunk.markdown.strip()
            if not text:
                continue
            if written > 0:
                handle.write("\n\n")
            handle.write(text)
            written += 1
        if written > 0:
            handle.write("\n")