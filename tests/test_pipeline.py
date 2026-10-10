"""Tests for md_converter.core.pipeline."""

from __future__ import annotations

import threading
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import replace
from pathlib import Path

from md_converter.core.errors import FileLockedError
from md_converter.core.models import (
    Chunk,
    ConversionRequest,
    ConversionStatus,
    DocFormat,
)
from md_converter.core.pipeline import Pipeline
from md_converter.core.pipeline import convert as default_convert


def _make_pdf(path: Path) -> Path:
    """Write a minimal real-looking PDF file."""
    path.write_bytes(b"%PDF-1.4\n%fake\n")
    return path


def _make_docx(path: Path) -> Path:
    """Write a minimal real-looking DOCX file."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
    return path


class FakeReader:
    """Reader that yields a fixed number of chunks.

    Optionally sets a cancel event after a chosen 1-based chunk index.
    """

    def __init__(
        self,
        count: int = 3,
        cancel_event: threading.Event | None = None,
        cancel_after: int | None = None,
    ) -> None:
        self._count = count
        self._cancel_event = cancel_event
        self._cancel_after = cancel_after

    def read(self, path: Path) -> Iterator[Chunk]:
        for index in range(self._count):
            yield Chunk(index=index + 1, markdown=f"chunk {index + 1}")
            if (
                self._cancel_event is not None
                and self._cancel_after is not None
                and index + 1 >= self._cancel_after
            ):
                self._cancel_event.set()


class FakeWriter:
    """Writer that joins the Markdown of all chunks into the output file."""

    def write(
        self,
        chunks: Iterable[Chunk],
        output_path: Path,
        cancel: threading.Event | None = None,
    ) -> None:
        with output_path.open("w", encoding="utf-8") as handle:
            handle.write("\n".join(chunk.markdown for chunk in chunks))


class FakeTransform:
    """Transform that prepends a fixed prefix to every chunk's Markdown."""

    def __init__(self, prefix: str = "") -> None:
        self._prefix = prefix

    def apply(self, chunks: Iterable[Chunk]) -> Iterator[Chunk]:
        for chunk in chunks:
            yield replace(chunk, markdown=self._prefix + chunk.markdown)


class ExplodingReader:
    """Reader that yields one chunk then raises a RuntimeError."""

    def read(self, path: Path) -> Iterator[Chunk]:
        yield Chunk(index=1, markdown="first")
        raise RuntimeError("boom")


class EmptyReader:
    """Reader that yields nothing."""

    def read(self, path: Path) -> Iterator[Chunk]:
        return
        yield  # pragma: no cover


class PermissionDeniedWriter:
    """Writer that raises PermissionError immediately."""

    def write(
        self,
        chunks: Iterable[Chunk],
        output_path: Path,
        cancel: threading.Event | None = None,
    ) -> None:
        raise PermissionError("no access")


def test_success_path_pdf_to_md(tmp_path: Path) -> None:
    """Prove a simple PDF -> MD conversion succeeds end to end."""
    source = _make_pdf(tmp_path / "report.pdf")
    pipeline = Pipeline(
        {DocFormat.PDF: FakeReader(3)},
        {DocFormat.MD: FakeWriter()},
    )
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.SUCCESS
    assert result.output_path == tmp_path / "report.md"
    assert result.output_path is not None
    assert result.output_path.exists()
    assert result.output_path.read_text(encoding="utf-8") == (
        "chunk 1\nchunk 2\nchunk 3"
    )
    assert result.chunks_processed == 3
    assert not (tmp_path / "report.md.part").exists()


def test_transforms_are_applied_in_order(tmp_path: Path) -> None:
    """Prove transforms are applied in the order they are given."""
    source = _make_pdf(tmp_path / "report.pdf")
    pipeline = Pipeline(
        {DocFormat.PDF: FakeReader(1)},
        {DocFormat.MD: FakeWriter()},
        (FakeTransform("X-"), FakeTransform("Y-")),
    )
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.SUCCESS
    assert result.output_path is not None
    assert result.output_path.read_text(encoding="utf-8").startswith("Y-X-")


def test_output_dir_is_honoured_and_created(tmp_path: Path) -> None:
    """Prove output_dir is used and created when missing."""
    source = _make_pdf(tmp_path / "report.pdf")
    out_dir = tmp_path / "nested" / "out"
    pipeline = Pipeline(
        {DocFormat.PDF: FakeReader(1)},
        {DocFormat.MD: FakeWriter()},
    )
    result = pipeline.convert(
        ConversionRequest(
            source=source,
            target_format=DocFormat.MD,
            output_dir=out_dir,
        )
    )
    assert result.status is ConversionStatus.SUCCESS
    assert out_dir.is_dir()
    assert result.output_path == out_dir / "report.md"


def test_existing_output_is_not_overwritten(tmp_path: Path) -> None:
    """Prove a second conversion does not overwrite the first output file."""
    source = _make_pdf(tmp_path / "report.pdf")
    pipeline = Pipeline(
        {DocFormat.PDF: FakeReader(1)},
        {DocFormat.MD: FakeWriter()},
    )
    first = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert first.output_path == tmp_path / "report.md"
    assert first.output_path is not None
    first_content = first.output_path.read_text(encoding="utf-8")

    second = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert second.output_path == tmp_path / "report (1).md"
    assert second.output_path is not None
    assert second.output_path.exists()
    assert first.output_path.read_text(encoding="utf-8") == first_content
    assert source.read_bytes() == b"%PDF-1.4\n%fake\n"


def test_same_format_is_failed(tmp_path: Path) -> None:
    """Prove a same-format request is rejected without raising."""
    source = _make_pdf(tmp_path / "report.pdf")
    pipeline = Pipeline({}, {})
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.PDF)
    )
    assert result.status is ConversionStatus.FAILED
    assert result.error_message


def test_missing_reader_is_failed(tmp_path: Path) -> None:
    """Prove a missing reader produces a FAILED result."""
    source = _make_pdf(tmp_path / "report.pdf")
    pipeline = Pipeline({}, {DocFormat.MD: FakeWriter()})
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.FAILED
    assert result.error_message


def test_missing_writer_is_failed(tmp_path: Path) -> None:
    """Prove a missing writer produces a FAILED result."""
    source = _make_pdf(tmp_path / "report.pdf")
    pipeline = Pipeline({DocFormat.PDF: FakeReader(1)}, {})
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.FAILED
    assert result.error_message


def test_corrupt_source_is_failed(tmp_path: Path) -> None:
    """Prove a corrupt source produces a FAILED result instead of raising."""
    source = tmp_path / "report.pdf"
    source.write_text("not a pdf", encoding="utf-8")
    pipeline = Pipeline(
        {DocFormat.PDF: FakeReader(1)},
        {DocFormat.MD: FakeWriter()},
    )
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.FAILED
    assert result.error_message


def test_exploding_reader_is_failed_and_cleans_up(tmp_path: Path) -> None:
    """Prove a reader that raises mid-stream fails cleanly."""
    source = _make_pdf(tmp_path / "report.pdf")
    pipeline = Pipeline(
        {DocFormat.PDF: ExplodingReader()},
        {DocFormat.MD: FakeWriter()},
    )
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.FAILED
    assert result.error_message
    assert not (tmp_path / "report.md.part").exists()
    assert not (tmp_path / "report.md").exists()


def test_empty_reader_is_failed_and_cleans_up(tmp_path: Path) -> None:
    """Prove an empty reader produces the no-content failure."""
    source = _make_pdf(tmp_path / "report.pdf")
    pipeline = Pipeline(
        {DocFormat.PDF: EmptyReader()},
        {DocFormat.MD: FakeWriter()},
    )
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.FAILED
    assert "no readable content" in result.error_message
    assert not (tmp_path / "report.md.part").exists()
    assert not (tmp_path / "report.md").exists()


def test_progress_callback_called_once_per_chunk(tmp_path: Path) -> None:
    """Prove the progress callback fires once per chunk with growing counts."""
    source = _make_pdf(tmp_path / "report.pdf")
    pipeline = Pipeline(
        {DocFormat.PDF: FakeReader(3)},
        {DocFormat.MD: FakeWriter()},
    )
    calls: list[tuple[int, int | None]] = []

    def progress(done: int, total: int | None) -> None:
        calls.append((done, total))

    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD),
        progress=progress,
    )
    assert result.status is ConversionStatus.SUCCESS
    assert [call[0] for call in calls] == [1, 2, 3]
    assert all(call[1] is None for call in calls)


def test_progress_callback_that_raises_is_ignored(tmp_path: Path) -> None:
    """Prove a broken progress callback does not break the conversion."""
    source = _make_pdf(tmp_path / "report.pdf")
    pipeline = Pipeline(
        {DocFormat.PDF: FakeReader(2)},
        {DocFormat.MD: FakeWriter()},
    )
    calls: list[int] = []

    def progress(done: int, total: int | None) -> None:
        calls.append(done)
        raise RuntimeError("bad progress")

    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD),
        progress=progress,
    )
    assert result.status is ConversionStatus.SUCCESS
    assert calls


def test_cancel_stops_conversion_and_cleans_up(tmp_path: Path) -> None:
    """Prove a cancellation produces CANCELLED with no leftover files."""
    source = _make_pdf(tmp_path / "report.pdf")
    cancel = threading.Event()
    pipeline = Pipeline(
        {DocFormat.PDF: FakeReader(5, cancel_event=cancel, cancel_after=2)},
        {DocFormat.MD: FakeWriter()},
    )
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD),
        cancel=cancel,
    )
    assert result.status is ConversionStatus.CANCELLED
    assert result.error_message == ""
    assert not (tmp_path / "report.md.part").exists()
    assert not (tmp_path / "report.md").exists()


def test_writer_permission_error_is_failed_with_locked_message(
    tmp_path: Path,
) -> None:
    """Prove a PermissionError from the writer maps to the file-locked message."""
    source = _make_pdf(tmp_path / "report.pdf")
    pipeline = Pipeline(
        {DocFormat.PDF: FakeReader(1)},
        {DocFormat.MD: PermissionDeniedWriter()},
    )
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.FAILED
    assert result.error_message == FileLockedError().user_message


def test_default_convert_has_no_readers(tmp_path: Path) -> None:
    """Prove the module-level convert() returns FAILED without raising."""
    source = _make_pdf(tmp_path / "report.pdf")
    result = default_convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.FAILED
    assert result.error_message