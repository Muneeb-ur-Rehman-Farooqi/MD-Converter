"""Tests for md_converter.core.readers.pdf_reader."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import pymupdf

from md_converter.core.errors import (
    ConversionError,
    CorruptFileError,
    NoTextLayerError,
    PasswordProtectedError,
)
from md_converter.core.models import (
    ConversionRequest,
    ConversionStatus,
    DocFormat,
)
from md_converter.core.pipeline import Pipeline
from md_converter.core.readers import pdf_reader
from md_converter.core.readers.pdf_reader import (
    _bullet_to_markdown,
    _join_block_lines,
    _round_size,
    _spans_to_markdown,
    _table_to_markdown,
)
from md_converter.core.transforms import math_hook
from md_converter.core.writers import md_writer


# ----------------------------- fixture helpers ----------------------------- #


def _make_text_pdf(path: Path, pages: list[list[str]]) -> None:
    """Create a PDF with one page per inner list and one body line per string."""
    doc = pymupdf.open()
    try:
        for lines in pages:
            page = doc.new_page()
            y = 72
            for line in lines:
                page.insert_text((72, y), line, fontsize=11, fontname="helv")
                y += 16
        doc.save(path)
    finally:
        doc.close()


def _make_heading_pdf(path: Path) -> None:
    """Create a PDF with a 24pt heading, a 16pt heading and 8 body lines."""
    doc = pymupdf.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "Chapter One", fontsize=24, fontname="helv")
        page.insert_text((72, 160), "Section A", fontsize=16, fontname="helv")
        y = 240
        for i in range(8):
            page.insert_text(
                (72, y),
                f"Body line {i + 1} here.",
                fontsize=11,
                fontname="helv",
            )
            y += 20
        doc.save(path)
    finally:
        doc.close()


def _make_ruled_table_pdf(path: Path) -> None:
    """Create a PDF with a ruled 3x3 table and a short word in each cell."""
    doc = pymupdf.open()
    try:
        page = doc.new_page()
        x0, y0 = 72, 72
        col_w, row_h = 100, 30
        page.draw_rect(
            pymupdf.Rect(x0, y0, x0 + 3 * col_w, y0 + 3 * row_h)
        )
        for i in range(1, 3):
            page.draw_line(
                pymupdf.Point(x0 + i * col_w, y0),
                pymupdf.Point(x0 + i * col_w, y0 + 3 * row_h),
            )
            page.draw_line(
                pymupdf.Point(x0, y0 + i * row_h),
                pymupdf.Point(x0 + 3 * col_w, y0 + i * row_h),
            )
        cells = [
            ["Name", "Qty", "Price"],
            ["Apple", "1", "$1"],
            ["Bread", "2", "$3"],
        ]
        for r, row in enumerate(cells):
            for c, text in enumerate(row):
                page.insert_text(
                    (x0 + c * col_w + 5, y0 + r * row_h + 20),
                    text,
                    fontsize=11,
                    fontname="helv",
                )
        doc.save(path)
    finally:
        doc.close()


def _make_encrypted_pdf(path: Path) -> None:
    """Create a PDF protected by a user password."""
    doc = pymupdf.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "secret text", fontsize=11, fontname="helv")
        doc.save(
            path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw="secret",
            owner_pw="owner",
        )
    finally:
        doc.close()


# ----------------------------- pure helpers -------------------------------- #


def test_round_size() -> None:
    """Prove _round_size rounds to the nearest 0.5."""
    assert _round_size(11.2) == 11.0
    assert _round_size(11.3) == 11.5
    assert _round_size(23.9) == 24.0


def test_table_to_markdown_normal() -> None:
    """Prove a simple 2x2 table becomes a standard pipe table."""
    md = _table_to_markdown([["A", "B"], ["1", "2"]])
    assert md == "| A | B |\n| --- | --- |\n| 1 | 2 |"


def test_table_to_markdown_none_cells() -> None:
    """Prove None cells become empty strings."""
    md = _table_to_markdown([["A", None], ["1", "2"]])
    assert md == "| A |  |\n| --- | --- |\n| 1 | 2 |"


def test_table_to_markdown_pipe_and_newline_in_cell() -> None:
    """Prove pipes are escaped and newlines become <br>."""
    md = _table_to_markdown([["a|b", "c\nd"], ["1", "2"]])
    assert "\\|" in md
    assert "<br>" in md
    assert "\n" in md  # still a pipe table


def test_table_to_markdown_ragged_rows_padded() -> None:
    """Prove short rows are padded with empty cells."""
    md = _table_to_markdown([["A", "B", "C"], ["1"], ["4", "5"]])
    lines = md.split("\n")
    assert lines[0] == "| A | B | C |"
    assert lines[1] == "| --- | --- | --- |"
    assert lines[2] == "| 1 |  |  |"
    assert lines[3] == "| 4 | 5 |  |"


def test_table_to_markdown_too_few_rows() -> None:
    """Prove a single-row table gives an empty string."""
    assert _table_to_markdown([["A", "B"]]) == ""
    assert _table_to_markdown([]) == ""


def test_join_block_lines_dehyphenation() -> None:
    """Prove a hyphen after a letter joins with a lowercase next line."""
    assert _join_block_lines(["meth-", "od leads"]) == "method leads"


def test_join_block_lines_hyphen_uppercase_not_merged() -> None:
    """Prove a hyphen followed by an uppercase letter is not merged."""
    assert _join_block_lines(["foo-", "Bar"]) == "foo- Bar"


def test_join_block_lines_normal() -> None:
    """Prove normal lines are joined with one space."""
    assert _join_block_lines(["a", "b", "c"]) == "a b c"
    assert _join_block_lines(["a", "", "b"]) == "a b"


def test_bullet_to_markdown() -> None:
    """Prove the supported bullet characters become Markdown list items."""
    assert _bullet_to_markdown("• item") == "- item"
    assert _bullet_to_markdown("- item") == "- item"
    assert _bullet_to_markdown("– item") == "- item"
    assert _bullet_to_markdown("* item") == "- item"
    assert _bullet_to_markdown("-item") is None
    assert _bullet_to_markdown("plain text") is None


def test_spans_to_markdown_bold() -> None:
    """Prove a bold span is wrapped in **...**."""
    spans = [{"text": "hello", "flags": pymupdf.TEXT_FONT_BOLD}]
    assert _spans_to_markdown(spans) == "**hello**"


def test_spans_to_markdown_italic() -> None:
    """Prove an italic span is wrapped in *...*."""
    spans = [{"text": "hello", "flags": pymupdf.TEXT_FONT_ITALIC}]
    assert _spans_to_markdown(spans) == "*hello*"


def test_spans_to_markdown_bold_italic() -> None:
    """Prove a bold+italic span is wrapped in ***...***."""
    spans = [
        {
            "text": "hello",
            "flags": pymupdf.TEXT_FONT_BOLD | pymupdf.TEXT_FONT_ITALIC,
        }
    ]
    assert _spans_to_markdown(spans) == "***hello***"


def test_spans_to_markdown_whitespace_outside_markers() -> None:
    """Prove whitespace stays outside the emphasis markers."""
    spans = [{"text": " hello ", "flags": pymupdf.TEXT_FONT_BOLD}]
    assert _spans_to_markdown(spans) == " **hello** "


def test_spans_to_markdown_merges_consecutive_bold_spans() -> None:
    """Prove two consecutive bold spans are merged into one run."""
    spans = [
        {"text": "foo", "flags": pymupdf.TEXT_FONT_BOLD},
        {"text": "bar", "flags": pymupdf.TEXT_FONT_BOLD},
    ]
    assert _spans_to_markdown(spans) == "**foobar**"


# ----------------------------- reader tests -------------------------------- #


def test_read_returns_generator_and_defers_opening(tmp_path: Path) -> None:
    """Prove read() is a generator and does not touch the file until iterated."""
    source = tmp_path / "not_a.pdf"
    source.write_bytes(b"not a pdf at all")
    gen = pdf_reader.read(source)
    assert inspect.isgenerator(gen)
    with pytest.raises(ConversionError):
        next(gen)


def test_single_page_with_body_lines(tmp_path: Path) -> None:
    """Prove a single page with a few lines yields one Chunk."""
    source = tmp_path / "a.pdf"
    _make_text_pdf(source, [["Hello world", "second line"]])
    chunks = list(pdf_reader.read(source))
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.index == 1
    assert "Hello world" in chunk.markdown
    assert "second line" in chunk.markdown
    assert "Hello world" in chunk.raw_text
    assert "second line" in chunk.raw_text


def test_three_pages_give_indices_one_two_three(tmp_path: Path) -> None:
    """Prove three pages yield chunks with 1-based indices in order."""
    source = tmp_path / "a.pdf"
    _make_text_pdf(source, [["page one"], ["page two"], ["page three"]])
    chunks = list(pdf_reader.read(source))
    assert [c.index for c in chunks] == [1, 2, 3]
    assert "page one" in chunks[0].markdown
    assert "page two" in chunks[1].markdown
    assert "page three" in chunks[2].markdown


def test_latin1_characters_survive(tmp_path: Path) -> None:
    """Prove Latin-1 characters survive extraction unchanged."""
    source = tmp_path / "a.pdf"
    _make_text_pdf(source, [["café naïve"]])
    chunks = list(pdf_reader.read(source))
    assert "café naïve" in chunks[0].markdown
    assert "café naïve" in chunks[0].raw_text


def test_heading_detection(tmp_path: Path) -> None:
    """Prove 24pt/16pt headings are marked and 11pt body stays plain."""
    source = tmp_path / "a.pdf"
    _make_heading_pdf(source)
    chunks = list(pdf_reader.read(source))
    assert len(chunks) == 1
    lines = chunks[0].markdown.split("\n")
    assert "# Chapter One" in lines
    assert "## Section A" in lines
    for line in lines:
        if "Body line" in line:
            assert not line.startswith("#")


def test_ruled_table_produces_pipe_table(tmp_path: Path) -> None:
    """Prove a ruled 3x3 table becomes a pipe table with unique cell words."""
    source = tmp_path / "table.pdf"
    _make_ruled_table_pdf(source)
    chunks = list(pdf_reader.read(source))
    assert len(chunks) == 1
    md = chunks[0].markdown
    assert "| --- |" in md
    for word in ("Name", "Qty", "Price", "Apple", "Bread"):
        assert md.count(word) == 1


def test_detect_tables_false_skips_tables(tmp_path: Path) -> None:
    """Prove detect_tables=False leaves out the pipe-table separator."""
    source = tmp_path / "table.pdf"
    _make_ruled_table_pdf(source)
    chunks = list(pdf_reader.read(source, detect_tables=False))
    assert chunks
    assert all("| --- |" not in c.markdown for c in chunks)


def test_blank_page_between_text_pages(tmp_path: Path) -> None:
    """Prove a blank page between two text pages does not yield a chunk."""
    source = tmp_path / "a.pdf"
    doc = pymupdf.open()
    try:
        p1 = doc.new_page()
        p1.insert_text((72, 72), "page one", fontsize=11, fontname="helv")
        doc.new_page()  # blank page, index 2
        p3 = doc.new_page()
        p3.insert_text((72, 72), "page three", fontsize=11, fontname="helv")
        doc.save(source)
    finally:
        doc.close()
    chunks = list(pdf_reader.read(source))
    assert [c.index for c in chunks] == [1, 3]


def test_all_blank_pages_raise_no_text_layer(tmp_path: Path) -> None:
    """Prove a document of blank pages raises NoTextLayerError."""
    source = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    try:
        doc.new_page()
        doc.new_page()
        doc.save(source)
    finally:
        doc.close()
    with pytest.raises(NoTextLayerError):
        list(pdf_reader.read(source))


def test_encrypted_pdf_raises_password_protected(tmp_path: Path) -> None:
    """Prove a user-password PDF raises PasswordProtectedError."""
    source = tmp_path / "enc.pdf"
    _make_encrypted_pdf(source)
    with pytest.raises(PasswordProtectedError):
        list(pdf_reader.read(source))


def test_corrupt_pdf_raises_corrupt_error(tmp_path: Path) -> None:
    """Prove a fake PDF file raises CorruptFileError."""
    source = tmp_path / "bad.pdf"
    source.write_bytes(b"%PDF-1.4\nthis is not really a pdf")
    with pytest.raises(CorruptFileError):
        list(pdf_reader.read(source))


def test_file_deletable_after_full_read(tmp_path: Path) -> None:
    """Prove the file handle is released after full consumption."""
    source = tmp_path / "a.pdf"
    _make_text_pdf(source, [["one"]])
    chunks = list(pdf_reader.read(source))
    assert chunks
    source.unlink()  # would raise on Windows if the handle were still open


def test_file_deletable_after_partial_read(tmp_path: Path) -> None:
    """Prove the file handle is released when the generator is closed early."""
    source = tmp_path / "a.pdf"
    _make_text_pdf(source, [["page one"], ["page two"], ["page three"]])
    gen = pdf_reader.read(source)
    first = next(gen)
    assert first.index == 1
    gen.close()
    source.unlink()  # would raise on Windows if the handle were still open


def test_150_pages_yield_150_chunks(tmp_path: Path) -> None:
    """Prove a 150-page PDF yields 150 chunks with consecutive indices."""
    source = tmp_path / "big.pdf"
    _make_text_pdf(source, [[f"page {i}"] for i in range(1, 151)])
    chunks = list(pdf_reader.read(source))
    assert len(chunks) == 150
    assert [c.index for c in chunks] == list(range(1, 151))


def test_end_to_end_pipeline_pdf_to_md(tmp_path: Path) -> None:
    """Prove the F1 pipeline converts a small PDF to Markdown next to the PDF."""
    source = tmp_path / "doc.pdf"
    _make_heading_pdf(source)

    pipeline = Pipeline(
        readers={DocFormat.PDF: pdf_reader},
        writers={DocFormat.MD: md_writer},
        transforms=(math_hook,),
    )
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )

    assert result.status is ConversionStatus.SUCCESS
    assert result.output_path == tmp_path / "doc.md"
    assert result.output_path is not None
    text = result.output_path.read_text(encoding="utf-8")
    assert "# Chapter One" in text
    assert "Body line" in text
    assert not (tmp_path / "doc.md.part").exists()


def test_end_to_end_pipeline_blank_pdf_fails_with_ocr_message(
    tmp_path: Path,
) -> None:
    """Prove an all-blank PDF produces a FAILED result mentioning OCR."""
    source = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    try:
        doc.new_page()
        doc.save(source)
    finally:
        doc.close()

    pipeline = Pipeline(
        readers={DocFormat.PDF: pdf_reader},
        writers={DocFormat.MD: md_writer},
        transforms=(math_hook,),
    )
    result = pipeline.convert(
        ConversionRequest(source=source, target_format=DocFormat.MD)
    )

    assert result.status is ConversionStatus.FAILED
    assert "OCR" in result.error_message