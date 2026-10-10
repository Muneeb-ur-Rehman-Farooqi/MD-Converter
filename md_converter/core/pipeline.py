"""Conversion pipeline that glues readers, transforms and writers together."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from md_converter.core.detect import detect_format, extension_for
from md_converter.core.errors import (
    ConversionError,
    CorruptFileError,
    FileLockedError,
    FileTooLargeError,
    OutputNotWritableError,
    UnsupportedFormatError,
)
from md_converter.core.models import (
    Chunk,
    ConversionRequest,
    ConversionResult,
    ConversionStatus,
    DocFormat,
    ProgressCallback,
)
from md_converter.core.transforms import math_hook

logger = logging.getLogger(__name__)

_GENERIC_ERROR_MESSAGE = (
    "Something unexpected went wrong with this file. "
    "Details were saved to the log."
)


class Reader(Protocol):
    """Reads a source file and yields chunks one at a time."""

    def read(self, path: Path) -> Iterator[Chunk]:
        """Yield chunks for the file at path."""
        ...


class Transform(Protocol):
    """Transforms a stream of chunks."""

    def apply(self, chunks: Iterable[Chunk]) -> Iterator[Chunk]:
        """Yield transformed chunks."""
        ...


class Writer(Protocol):
    """Writes a stream of chunks to an output file."""

    def write(
        self,
        chunks: Iterable[Chunk],
        output_path: Path,
        cancel: threading.Event | None = None,
    ) -> None:
        """Write chunks to output_path."""
        ...


def make_output_path(folder: Path, stem: str, extension: str) -> Path:
    """Return a non-existing path in folder for the given stem and extension.

    Existing files are never overwritten: the helper tries "<stem><extension>",
    "<stem> (1)<extension>", "<stem> (2)<extension>", and so on.
    """
    candidate = folder / f"{stem}{extension}"
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = folder / f"{stem} ({index}){extension}"
        if not candidate.exists():
            return candidate
        index += 1


def _tracked(
    chunks: Iterable[Chunk],
    progress: ProgressCallback | None,
    cancel: threading.Event | None,
    counter: list[int],
) -> Iterator[Chunk]:
    """Yield chunks, checking cancel, counting chunks and reporting progress."""
    for chunk in chunks:
        if cancel is not None and cancel.is_set():
            return
        counter[0] += 1
        yield chunk
        try:
            if progress is not None:
                progress(counter[0], None)
        except Exception:
            logger.exception("Progress callback raised; ignoring")


def _safe_unlink(path: Path | None) -> None:
    """Delete path if it exists, logging but otherwise swallowing errors."""
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not delete temporary file: %s", path)


class Pipeline:
    """Conversion pipeline built from injected readers, transforms and writers."""

    def __init__(
        self,
        readers: Mapping[DocFormat, Reader],
        writers: Mapping[DocFormat, Writer],
        transforms: Sequence[Transform] = (),
    ) -> None:
        """Store the injected readers, writers and transforms."""
        self._readers: dict[DocFormat, Reader] = dict(readers)
        self._writers: dict[DocFormat, Writer] = dict(writers)
        self._transforms: tuple[Transform, ...] = tuple(transforms)

    def convert(
        self,
        request: ConversionRequest,
        progress: ProgressCallback | None = None,
        cancel: threading.Event | None = None,
    ) -> ConversionResult:
        """Run one conversion; never raises for ordinary errors."""
        temp_path: Path | None = None
        try:
            source_format = detect_format(request.source)

            if source_format == request.target_format:
                return self._failed(
                    request,
                    UnsupportedFormatError(
                        "Converting a file to the same format is not supported yet."
                    ).user_message,
                )

            reader = self._readers.get(source_format)
            writer = self._writers.get(request.target_format)
            if reader is None or writer is None:
                return self._failed(
                    request,
                    UnsupportedFormatError(
                        "This conversion is not available yet."
                    ).user_message,
                )

            if request.output_dir is not None:
                folder = request.output_dir
            else:
                folder = request.source.parent
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise OutputNotWritableError(
                    f"The output folder could not be created: {exc}"
                ) from exc

            extension = extension_for(request.target_format)
            final_path = make_output_path(folder, request.source.stem, extension)
            temp_path = folder / (final_path.name + ".part")

            chunks: Iterable[Chunk] = reader.read(request.source)
            for transform in self._transforms:
                chunks = transform.apply(chunks)

            counter: list[int] = [0]
            tracked = _tracked(chunks, progress, cancel, counter)

            # Writers MUST NOT infer the format from the output extension.
            writer.write(tracked, temp_path, cancel)
            chunk_count = counter[0]

            if cancel is not None and cancel.is_set():
                _safe_unlink(temp_path)
                return ConversionResult(
                    source=request.source,
                    target_format=request.target_format,
                    status=ConversionStatus.CANCELLED,
                    chunks_processed=chunk_count,
                )

            if chunk_count == 0:
                _safe_unlink(temp_path)
                return self._failed(
                    request,
                    CorruptFileError(
                        "The file contains no readable content."
                    ).user_message,
                )

            os.replace(temp_path, final_path)
            temp_path = None
            return ConversionResult(
                source=request.source,
                target_format=request.target_format,
                status=ConversionStatus.SUCCESS,
                output_path=final_path,
                chunks_processed=chunk_count,
            )
        except ConversionError as exc:
            _safe_unlink(temp_path)
            return self._failed(request, exc.user_message)
        except PermissionError:
            _safe_unlink(temp_path)
            return self._failed(request, FileLockedError().user_message)
        except MemoryError:
            _safe_unlink(temp_path)
            return self._failed(request, FileTooLargeError().user_message)
        except Exception:
            logger.exception("Unexpected error during conversion")
            _safe_unlink(temp_path)
            return self._failed(request, _GENERIC_ERROR_MESSAGE)

    def _failed(self, request: ConversionRequest, message: str) -> ConversionResult:
        """Build a FAILED result for request with the given message."""
        return ConversionResult(
            source=request.source,
            target_format=request.target_format,
            status=ConversionStatus.FAILED,
            error_message=message,
        )


def build_default_pipeline() -> Pipeline:
    """Return the default pipeline.

    Real readers and writers are registered here as each feature (F1 to F5) is
    built. It is a function, not a module-level object, so importing
    pipeline.py has no side effects.
    """
    return Pipeline(readers={}, writers={}, transforms=(math_hook,))


def convert(
    request: ConversionRequest,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> ConversionResult:
    """Public entry point: run request through the default pipeline."""
    return build_default_pipeline().convert(request, progress, cancel)