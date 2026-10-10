"""Tests for the default pipeline after registering the PDF reader and MD writer."""

from __future__ import annotations

import threading
import zipfile
from pathlib import Path

import pymupdf

from md_converter.core.models import (
    ConversionRequest,
    ConversionStatus,
    DocFormat,
)
from md_converter.core.pipeline import convert


def _make_text_pdf(path: Path, page_texts: list[str]) -> None:
    """Create a PDF with one page per string and a single text line on each."""
    doc = pymupdf.open()
    try:
        for text in page_texts:
            page = doc.new_page()
            page.insert_text((72, 72), text, fontsize=11, fontname="helv")
        doc.save(path)
    finally:
        doc.close()


def _make_docx(path: Path) -> None:
    """Create a minimal real-looking DOCX file."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")


def test_pdf_to_md_succeeds(tmp_path: Path) -> None:
    """Prove PDF -> MD succeeds through the default pipeline."""
    source = tmp_path / "doc.pdf"
    _make_text_pdf(source, ["Hello world"])
    result = convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.SUCCESS
    assert result.output_path == tmp_path / "doc.md"
    assert result.output_path is not None
    assert result.output_path.exists()
    assert "Hello world" in result.output_path.read_text(encoding="utf-8")
    assert not (tmp_path / "doc.md.part").exists()


def test_pdf_to_md_honours_output_dir(tmp_path: Path) -> None:
    """Prove output_dir is used and created when missing."""
    source = tmp_path / "doc.pdf"
    _make_text_pdf(source, ["Hello"])
    out_dir = tmp_path / "nested" / "out"
    result = convert(
        ConversionRequest(
            source=source,
            target_format=DocFormat.MD,
            output_dir=out_dir,
        )
    )
    assert result.status is ConversionStatus.SUCCESS
    assert out_dir.is_dir()
    assert result.output_path == out_dir / "doc.md"


def test_pdf_to_docx_fails(tmp_path: Path) -> None:
    """Prove PDF -> DOCX fails cleanly because no DOCX writer is registered."""
    source = tmp_path / "doc.pdf"
    _make_text_pdf(source, ["Hello"])
    result = convert(
        ConversionRequest(source=source, target_format=DocFormat.DOCX)
    )
    assert result.status is ConversionStatus.FAILED
    assert result.error_message


def test_docx_to_md_fails(tmp_path: Path) -> None:
    """Prove DOCX -> MD fails cleanly because no DOCX reader is registered."""
    source = tmp_path / "doc.docx"
    _make_docx(source)
    result = convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.FAILED
    assert result.error_message


def test_md_to_pdf_fails(tmp_path: Path) -> None:
    """Prove MD -> PDF fails cleanly because no MD reader is registered."""
    source = tmp_path / "doc.md"
    source.write_text("# hello\n", encoding="utf-8")
    result = convert(
        ConversionRequest(source=source, target_format=DocFormat.PDF)
    )
    assert result.status is ConversionStatus.FAILED
    assert result.error_message


def test_progress_on_five_page_pdf(tmp_path: Path) -> None:
    """Prove the progress callback receives increasing counts ending at 5."""
    source = tmp_path / "doc.pdf"
    _make_text_pdf(source, [f"page {i}" for i in range(1, 6)])
    counts: list[int] = []

    def progress(done: int, total: int | None) -> None:
        counts.append(done)

    result = convert(
        ConversionRequest(source=source, target_format=DocFormat.MD),
        progress=progress,
    )
    assert result.status is ConversionStatus.SUCCESS
    assert counts == [1, 2, 3, 4, 5]


def test_cancel_from_progress_callback(tmp_path: Path) -> None:
    """Prove cancel set from the progress callback after two pages cancels cleanly."""
    source = tmp_path / "doc.pdf"
    _make_text_pdf(source, [f"page {i}" for i in range(1, 11)])
    cancel = threading.Event()

    def progress(done: int, total: int | None) -> None:
        if done >= 2:
            cancel.set()

    result = convert(
        ConversionRequest(source=source, target_format=DocFormat.MD),
        progress=progress,
        cancel=cancel,
    )
    assert result.status is ConversionStatus.CANCELLED
    assert not (tmp_path / "doc.md").exists()
    assert not (tmp_path / "doc.md.part").exists()


def test_fake_pdf_fails_without_raising(tmp_path: Path) -> None:
    """Prove a .pdf file containing plain text fails cleanly through convert()."""
    source = tmp_path / "fake.pdf"
    source.write_text("this is not a pdf", encoding="utf-8")
    result = convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )
    assert result.status is ConversionStatus.FAILED
    assert result.error_message