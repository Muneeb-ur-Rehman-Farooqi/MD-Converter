"""Core data models and engine contract for MD Converter.

Engine contract:
    reader:    read(path: Path) -> Iterator[Chunk]
    transform: apply(chunks: Iterable[Chunk]) -> Iterator[Chunk]
        A transform may keep a small window of recent chunks, because fixes such as
        hyphenation and repeated headers span pages, but must never hold the whole
        document.
    writer:    write(
                   chunks: Iterable[Chunk],
                   output_path: Path,
                   cancel: threading.Event | None = None,
               ) -> None
    pipeline:  convert(request, progress=None, cancel=None) -> ConversionResult
        It never raises: every error becomes a FAILED result.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DocFormat(str, Enum):
    """Supported document formats."""

    PDF = "pdf"
    DOCX = "docx"
    MD = "md"


class ConversionStatus(str, Enum):
    """Outcome states for one conversion request."""

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Chunk:
    """One streamed page or section of extracted text and Markdown."""

    index: int
    markdown: str
    raw_text: str = ""


@dataclass
class ConversionRequest:
    """User request to convert one source file."""

    source: Path
    target_format: DocFormat
    output_dir: Path | None = None
    ai_mode: bool = False


@dataclass
class ConversionResult:
    """Result returned by the pipeline for one conversion request."""

    source: Path
    target_format: DocFormat
    status: ConversionStatus
    output_path: Path | None = None
    error_message: str = ""
    chunks_processed: int = 0
    tokens_before: int | None = None
    tokens_after: int | None = None


ProgressCallback = Callable[[int, int | None], None]