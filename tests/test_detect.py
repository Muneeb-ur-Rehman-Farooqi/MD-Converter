"""Tests for md_converter.core.detect."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from md_converter.core.detect import detect_format, extension_for
from md_converter.core.errors import CorruptFileError, UnsupportedFormatError
from md_converter.core.models import DocFormat


def _make_pdf(path: Path) -> Path:
    """Write a minimal real-looking PDF file."""
    path.write_bytes(b"%PDF-1.4\n%fake\n")
    return path


def _make_docx(path: Path, *, with_document: bool = True) -> Path:
    """Write a minimal DOCX-like zip file."""
    with zipfile.ZipFile(path, "w") as archive:
        if with_document:
            archive.writestr("word/document.xml", "<w:document/>")
        else:
            archive.writestr("other.txt", "no document here")
    return path


def _make_md(path: Path, text: str = "# Heading\n\nSome text.\n") -> Path:
    """Write a small Markdown file."""
    path.write_text(text, encoding="utf-8")
    return path


def test_detect_pdf(tmp_path: Path) -> None:
    """Prove a real-looking PDF is detected as PDF."""
    assert detect_format(_make_pdf(tmp_path / "file.pdf")) is DocFormat.PDF


def test_detect_docx(tmp_path: Path) -> None:
    """Prove a real-looking DOCX is detected as DOCX."""
    assert detect_format(_make_docx(tmp_path / "file.docx")) is DocFormat.DOCX


def test_detect_md(tmp_path: Path) -> None:
    """Prove a Markdown file is detected as MD."""
    assert detect_format(_make_md(tmp_path / "file.md")) is DocFormat.MD


def test_detect_markdown_extension(tmp_path: Path) -> None:
    """Prove the .markdown extension is detected as MD."""
    assert detect_format(_make_md(tmp_path / "file.markdown")) is DocFormat.MD


def test_detect_uppercase_pdf(tmp_path: Path) -> None:
    """Prove the .PDF extension is detected case-insensitively."""
    assert detect_format(_make_pdf(tmp_path / "file.PDF")) is DocFormat.PDF


def test_detect_mixed_case_docx(tmp_path: Path) -> None:
    """Prove the .Docx extension is detected case-insensitively."""
    assert detect_format(_make_docx(tmp_path / "file.Docx")) is DocFormat.DOCX


def test_detect_uppercase_md(tmp_path: Path) -> None:
    """Prove the .MD extension is detected case-insensitively."""
    assert detect_format(_make_md(tmp_path / "file.MD")) is DocFormat.MD


def test_unknown_extension_raises_unsupported(tmp_path: Path) -> None:
    """Prove an unknown extension raises UnsupportedFormatError."""
    path = tmp_path / "file.txt"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        detect_format(path)


def test_pdf_with_plain_text_is_corrupt(tmp_path: Path) -> None:
    """Prove a .pdf whose content is not a PDF is rejected."""
    path = tmp_path / "file.pdf"
    path.write_text("this is not a pdf", encoding="utf-8")
    with pytest.raises(CorruptFileError):
        detect_format(path)


def test_docx_without_document_xml_is_corrupt(tmp_path: Path) -> None:
    """Prove a DOCX zip without word/document.xml is rejected."""
    path = _make_docx(tmp_path / "file.docx", with_document=False)
    with pytest.raises(CorruptFileError):
        detect_format(path)


def test_docx_that_is_not_zip_is_corrupt(tmp_path: Path) -> None:
    """Prove a .docx that is plain text is rejected."""
    path = tmp_path / "file.docx"
    path.write_text("not a zip", encoding="utf-8")
    with pytest.raises(CorruptFileError):
        detect_format(path)


def test_md_with_nul_bytes_is_corrupt(tmp_path: Path) -> None:
    """Prove a Markdown file containing NUL bytes is rejected."""
    path = tmp_path / "file.md"
    path.write_bytes(b"# Heading\n\x00binary\n")
    with pytest.raises(CorruptFileError):
        detect_format(path)


def test_missing_file_raises_corrupt(tmp_path: Path) -> None:
    """Prove a missing file raises CorruptFileError."""
    with pytest.raises(CorruptFileError):
        detect_format(tmp_path / "nope.pdf")


def test_directory_path_raises_corrupt(tmp_path: Path) -> None:
    """Prove a directory path raises CorruptFileError."""
    directory = tmp_path / "adir"
    directory.mkdir()
    with pytest.raises(CorruptFileError):
        detect_format(directory)


def test_extension_for_returns_canonical_extensions() -> None:
    """Prove extension_for returns the expected strings for each format."""
    assert extension_for(DocFormat.PDF) == ".pdf"
    assert extension_for(DocFormat.DOCX) == ".docx"
    assert extension_for(DocFormat.MD) == ".md"