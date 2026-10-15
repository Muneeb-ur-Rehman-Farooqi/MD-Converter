"""PDF reader for the MD Converter pipeline (feature F1, digital PDFs)."""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pymupdf

from md_converter.core.errors import (
    CorruptFileError,
    FileLockedError,
    NoTextLayerError,
    PasswordProtectedError,
)
from md_converter.core.models import Chunk

logger = logging.getLogger(__name__)

# Image bytes are slow and heavy; strip them from every dict extraction.
_DICT_FLAGS = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES

# Known limits of this reader:
# - No multi-column reordering.
# - No Markdown escaping (raw special characters pass through).
# - No superscript / subscript handling.
# - Tables are detected only when ruled lines are present.
# - Headings are guessed from font-size ratios and section numbering; some
#   headings will still be missed or mislabelled.
# - Page furniture is removed by learned style and position. Contents-page
#   detection is not done yet.
# - Cross-page paragraph repair is deferred to F6.
# - Equation handling is Phase 5 (math_hook).

# Ratio thresholds for heading detection. Chosen from real measurements on a
# 558-page textbook (body 10.0 pt) and deliberately kept as named constants so
# they can be tuned when new data disagrees.
_HEADING_MIN_RATIO = 1.05
_HEADING_MAX_RATIO = 3.0
_HEADING_H1_RATIO = 1.6
_HEADING_H2_RATIO = 1.25

# Furniture thresholds. Chosen from real measurements on a 558-page textbook
# (header at y0 ~ 22-26 on a 660 pt page, size 9.0, font
# "HelveticaNeueLTPro-Roman", body 10.0 TimesNewRomanPSStd-Regular) and kept
# as named constants so they can be tuned when new data disagrees.
_FURNITURE_ZONE = 0.08
_FURNITURE_MIN_SHARE = 0.6
_FURNITURE_MIN_PAGES = 3
_FURNITURE_MAX_LINES = 2
_FURNITURE_MAX_CHARS = 100

_BULLET_CHARS = ("•", "●", "▪", "◦", "‣", "∙", "·", "-", "–", "—", "*")

# Anchored at the start: integer groups separated by single dots, optional
# trailing dot, then at least one whitespace character.
_NUMBERING_PATTERN = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")


def _round_size(size: float) -> float:
    """Round a font size to the nearest 0.5."""
    return round(size * 2) / 2


def _clean_text(text: str) -> str:
    """Replace every Unicode control character (category Cc) with a space.

    Control characters are junk in Markdown and illegal in XML (a future
    DOCX writer would reject them), so they must not reach the writer. All
    other characters pass through untouched: no normalization, no stripping,
    no escaping.
    """
    if not text:
        return text
    return "".join(
        " " if unicodedata.category(ch) == "Cc" else ch for ch in text
    )


def _clean_block(block: dict) -> dict:
    """Return a copy of block with span texts cleaned of control characters."""
    new_block = dict(block)
    new_lines: list[dict] = []
    for line in block.get("lines", []):
        new_line = dict(line)
        new_spans: list[dict] = []
        for span in line.get("spans", []):
            new_span = dict(span)
            new_span["text"] = _clean_text(str(span.get("text", "")))
            new_spans.append(new_span)
        new_line["spans"] = new_spans
        new_lines.append(new_line)
    new_block["lines"] = new_lines
    return new_block


def _sample_page_numbers(page_count: int) -> list[int]:
    """Return the sampled 0-based page indices used for typography estimation.

    Up to 20 pages spread evenly across the document: pages 0, step, 2*step,
    ... below page_count, with step = max(1, page_count // 20).
    """
    if page_count <= 0:
        return []
    step = max(1, page_count // 20)
    return list(range(0, page_count, step))[:20]


def _estimate_sizes(doc: Any) -> tuple[float | None, list[float]]:
    """Estimate the body font size and heading sizes from a document.

    Samples up to 20 pages spread evenly across the document and counts how
    many characters are drawn at each rounded font size. The size with the
    most characters is the body size; any other size in
    [1.15 * body, 3.0 * body] is a heading size, sorted largest first and
    capped at three entries.

    The second element of the return value is no longer used for heading
    classification (the new design uses size ratios and section numbering),
    but it is still produced here because scripts/inspect_fonts.py prints it.
    """
    page_count = int(doc.page_count)
    if page_count <= 0:
        return None, []
    char_counts: dict[float, int] = {}
    for page_index in _sample_page_numbers(page_count):
        page = doc[page_index]
        data = page.get_text("dict", flags=_DICT_FLAGS)
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            cleaned = _clean_block(block)
            for line in cleaned.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text", ""))
                    if not text.strip():
                        continue
                    key = _round_size(float(span.get("size", 0.0)))
                    char_counts[key] = char_counts.get(key, 0) + len(text)
    if not char_counts:
        return None, []
    body_size = max(char_counts.items(), key=lambda item: item[1])[0]
    headings = [
        size
        for size in char_counts
        if body_size * 1.15 <= size <= body_size * 3.0
    ]
    headings.sort(reverse=True)
    return body_size, headings[:3]


def _numbering_depth(text: str) -> int | None:
    """Return how many dot-separated number groups text starts with, or None.

    "1.1 Digital Computers" -> 2, "1.6.3 The Reflected Code" -> 3,
    "3. Methods" -> 1, "2 Intro" -> 1. Anything that does not begin with
    a section number (or that has no whitespace after the number) -> None.
    """
    stripped = text.strip()
    match = _NUMBERING_PATTERN.match(stripped)
    if match is None:
        return None
    return len(match.group(1).split("."))


def _collapse_letter_spacing(text: str) -> str:
    """Collapse "C h a p t e r"-style letter spacing into "Chapter".

    Only collapses when the text splits on single spaces into at least four
    tokens and every token is exactly one character. Otherwise returns the
    text unchanged.
    """
    tokens = text.split(" ")
    if len(tokens) >= 4 and all(
        len(token) == 1 and token != " " for token in tokens
    ):
        return "".join(tokens)
    return text


def _heading_level(size: float, body_size: float, text: str) -> int | None:
    """Return the Markdown heading level 1..6 for a block, or None.

    Rules:
    - ratio = size / body_size must be in
      [_HEADING_MIN_RATIO, _HEADING_MAX_RATIO].
    - If the text starts with a section number, the level is the number of
      dot-separated groups (capped at 6).
    - Otherwise the level comes from the ratio:
      >= _HEADING_H1_RATIO -> 1, >= _HEADING_H2_RATIO -> 2, else 3.
    """
    if body_size <= 0:
        return None
    ratio = size / body_size
    if ratio < _HEADING_MIN_RATIO or ratio > _HEADING_MAX_RATIO:
        return None
    depth = _numbering_depth(text)
    if depth is not None:
        return min(depth, 6)
    if ratio >= _HEADING_H1_RATIO:
        return 1
    if ratio >= _HEADING_H2_RATIO:
        return 2
    return 3


def _block_signature(
    block: dict, page_height: float
) -> tuple[str, float, str] | None:
    """Return (zone, dominant rounded size, dominant font) for a text block.

    Returns None when the block is blank, has more than
    _FURNITURE_MAX_LINES non-blank lines, has more than
    _FURNITURE_MAX_CHARS characters in total (sum of the stripped non-blank
    line lengths), or does not fall in the top or bottom _FURNITURE_ZONE
    band of the page.
    """
    if page_height <= 0:
        return None
    bbox = block.get("bbox")
    if not bbox:
        return None

    size_counts: dict[float, int] = {}
    font_counts: dict[str, int] = {}
    non_blank_lines = 0
    total_chars = 0
    for line in block.get("lines", []):
        line_text = ""
        for span in line.get("spans", []):
            text = _clean_text(str(span.get("text", "")))
            line_text += text
            if not text.strip():
                continue
            key = _round_size(float(span.get("size", 0.0)))
            size_counts[key] = size_counts.get(key, 0) + len(text)
            font = str(span.get("font", ""))
            font_counts[font] = font_counts.get(font, 0) + len(text)
        stripped = line_text.strip()
        if stripped:
            non_blank_lines += 1
            total_chars += len(stripped)

    if non_blank_lines == 0:
        return None
    if non_blank_lines > _FURNITURE_MAX_LINES:
        return None
    if total_chars > _FURNITURE_MAX_CHARS:
        return None

    y0 = float(bbox[1])
    y1 = float(bbox[3])
    if y0 < page_height * _FURNITURE_ZONE:
        zone = "top"
    elif y1 > page_height * (1 - _FURNITURE_ZONE):
        zone = "bottom"
    else:
        return None

    if not size_counts:
        return None
    dominant_size = max(size_counts.items(), key=lambda item: item[1])[0]
    dominant_font = max(font_counts.items(), key=lambda item: item[1])[0]
    return (zone, dominant_size, dominant_font)


def _learn_furniture(doc: Any) -> list[tuple[str, float, str]]:
    """Learn recurring page-furniture styles from the sampled pages.

    Returns the signatures (zone, size, font) that appear on at least
    max(_FURNITURE_MIN_PAGES, ceil(_FURNITURE_MIN_SHARE * pages_with_text))
    sampled pages that contain text, and whose (size, font) differs from the
    document's body style. Sorted for determinism.
    """
    page_count = int(doc.page_count)
    if page_count <= 0:
        return []

    style_counts: dict[tuple[float, str], int] = {}
    page_signatures: list[set[tuple[str, float, str]]] = []

    for page_index in _sample_page_numbers(page_count):
        try:
            page = doc[page_index]
            data = page.get_text("dict", flags=_DICT_FLAGS)
        except Exception:
            logger.debug(
                "Skipping page %d for furniture learning", page_index
            )
            continue
        page_height = float(data.get("height", 0.0))
        has_text = False
        sigs: set[tuple[str, float, str]] = set()
        for raw_block in data.get("blocks", []):
            if raw_block.get("type") != 0:
                continue
            block = _clean_block(raw_block)
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text", ""))
                    if not text.strip():
                        continue
                    has_text = True
                    size = _round_size(float(span.get("size", 0.0)))
                    font = str(span.get("font", ""))
                    style_counts[(size, font)] = (
                        style_counts.get((size, font), 0) + len(text)
                    )
            sig = _block_signature(block, page_height)
            if sig is not None:
                sigs.add(sig)
        if has_text:
            page_signatures.append(sigs)

    pages_with_text = len(page_signatures)
    if pages_with_text < _FURNITURE_MIN_PAGES:
        return []

    body_style: tuple[float, str] | None = None
    if style_counts:
        body_style = max(style_counts.items(), key=lambda item: item[1])[0]

    threshold = max(
        _FURNITURE_MIN_PAGES,
        math.ceil(_FURNITURE_MIN_SHARE * pages_with_text),
    )

    signature_page_counts: dict[tuple[str, float, str], int] = {}
    for sigs in page_signatures:
        for sig in sigs:
            signature_page_counts[sig] = signature_page_counts.get(sig, 0) + 1

    qualifying: list[tuple[str, float, str]] = []
    for sig, count in signature_page_counts.items():
        if count < threshold:
            continue
        if body_style is not None and (sig[1], sig[2]) == body_style:
            continue
        qualifying.append(sig)

    return sorted(qualifying)


def _table_to_markdown(rows: list[list[str | None]]) -> str:
    """Convert extracted table rows to a Markdown pipe table.

    The first row is the header. Returns "" for fewer than two rows or when
    every cell is empty. Short rows are padded with empty cells.
    """
    if len(rows) < 2:
        return ""
    cleaned: list[list[str]] = []
    for row in rows:
        cleaned_row: list[str] = []
        for cell in row:
            value = "" if cell is None else str(cell)
            value = value.replace("\n", "<br>")
            value = value.replace("|", "\\|")
            value = value.strip()
            cleaned_row.append(value)
        cleaned.append(cleaned_row)
    if all(not cell for row in cleaned for cell in row):
        return ""
    width = max(len(row) for row in cleaned)
    for row in cleaned:
        while len(row) < width:
            row.append("")
    lines = [
        "| " + " | ".join(cleaned[0]) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    for row in cleaned[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _join_block_lines(lines: list[str]) -> str:
    """Join lines into one paragraph with hyphen-aware line merging.

    Kept for callers outside this module and for its existing tests. The
    reader itself now uses _join_line_spans for paragraph building so that
    emphasis markers can be applied after de-hyphenation.

    Cross-page hyphenation and further cleanup belong to F6.
    """
    stripped = [line.strip() for line in lines]
    non_empty = [line for line in stripped if line]
    if not non_empty:
        return ""
    parts: list[str] = [non_empty[0]]
    for current in non_empty[1:]:
        prev = parts[-1]
        if (
            len(prev) >= 2
            and prev.endswith("-")
            and prev[-2].isalpha()
            and current[:1].islower()
        ):
            parts[-1] = prev[:-1] + current
        else:
            parts.append(current)
    return " ".join(parts)


def _join_line_spans(lines: list[list[dict]]) -> list[dict]:
    """Join per-line span lists into one paragraph-long span list.

    Handles line-end de-hyphenation and inserts a single space between
    consecutive lines (keeping the emphasis state when both sides agree).
    Never mutates the input dicts.
    """
    if not lines:
        return []
    prepared: list[list[dict]] = []
    for line in lines:
        copied = [dict(span) for span in line]
        if copied:
            copied[0]["text"] = str(copied[0].get("text", "")).lstrip()
            copied[-1]["text"] = str(copied[-1].get("text", "")).rstrip()
            copied = [s for s in copied if str(s.get("text", ""))]
        if copied:
            prepared.append(copied)
    if not prepared:
        return []

    result: list[dict] = list(prepared[0])
    for i in range(1, len(prepared)):
        prev_line = prepared[i - 1]
        next_line = prepared[i]
        prev_text = "".join(str(s.get("text", "")) for s in prev_line)
        next_text = "".join(str(s.get("text", "")) for s in next_line)

        if (
            len(prev_text) >= 2
            and prev_text.endswith("-")
            and prev_text[-2].isalpha()
            and next_text
            and next_text[0].islower()
        ):
            last = result[-1]
            last["text"] = str(last.get("text", ""))[:-1]
            if not str(last.get("text", "")):
                result.pop()
        else:
            prev_flags = int(result[-1].get("flags", 0)) if result else 0
            next_flags = int(next_line[0].get("flags", 0)) if next_line else 0
            same_bold = (
                bool(prev_flags & pymupdf.TEXT_FONT_BOLD)
                == bool(next_flags & pymupdf.TEXT_FONT_BOLD)
            )
            same_italic = (
                bool(prev_flags & pymupdf.TEXT_FONT_ITALIC)
                == bool(next_flags & pymupdf.TEXT_FONT_ITALIC)
            )
            sep_flags = prev_flags if (same_bold and same_italic) else 0
            result.append({"text": " ", "flags": sep_flags})

        result.extend(prepared[i])

    return result


def _bullet_to_markdown(line: str) -> str | None:
    """Return a Markdown list item if line looks like a bullet, else None."""
    stripped = line.strip()
    if not stripped:
        return None
    if stripped[0] not in _BULLET_CHARS:
        return None
    rest = stripped[1:]
    if not rest or rest[0] not in (" ", "\t"):
        return None
    return "- " + rest.strip()


def _spans_to_markdown(spans: list[dict]) -> str:
    """Merge spans into Markdown with bold and italic markers.

    Consecutive spans with the same bold/italic state are merged. Leading
    and trailing whitespace stays outside the markers.
    """
    if not spans:
        return ""
    runs: list[tuple[bool, bool, str]] = []
    for span in spans:
        text = str(span.get("text", ""))
        flags = int(span.get("flags", 0))
        bold = bool(flags & pymupdf.TEXT_FONT_BOLD)
        italic = bool(flags & pymupdf.TEXT_FONT_ITALIC)
        if runs and runs[-1][0] == bold and runs[-1][1] == italic:
            runs[-1] = (bold, italic, runs[-1][2] + text)
        else:
            runs.append((bold, italic, text))
    parts: list[str] = []
    for bold, italic, text in runs:
        if not text:
            continue
        if not text.strip():
            parts.append(text)
            continue
        core = text.strip()
        leading = text[: len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]
        if bold and italic:
            parts.append(leading + "***" + core + "***" + trailing)
        elif bold:
            parts.append(leading + "**" + core + "**" + trailing)
        elif italic:
            parts.append(leading + "*" + core + "*" + trailing)
        else:
            parts.append(text)
    return "".join(parts)


def _extract_raw_text(blocks: list[dict]) -> str:
    """Return the untouched text of every text block, joined by newlines."""
    block_texts: list[str] = []
    for block in blocks:
        line_texts: list[str] = []
        for line in block.get("lines", []):
            line_texts.append(
                "".join(str(span.get("text", "")) for span in line.get("spans", []))
            )
        block_texts.append("\n".join(line_texts))
    return "\n".join(block_texts)


def _dominant_size(block: dict) -> float | None:
    """Return the rounded size of the span with the most characters."""
    counts: dict[float, int] = {}
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = str(span.get("text", ""))
            if not text.strip():
                continue
            key = _round_size(float(span.get("size", 0.0)))
            counts[key] = counts.get(key, 0) + len(text)
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def _find_containing_table(
    block: dict,
    tables: list[tuple[tuple[float, float, float, float], str]],
) -> int | None:
    """Return the index of the accepted table whose bbox contains the block centre."""
    bbox = block.get("bbox")
    if not bbox:
        return None
    cx = (float(bbox[0]) + float(bbox[2])) / 2
    cy = (float(bbox[1]) + float(bbox[3])) / 2
    for index, (table_bbox, _) in enumerate(tables):
        x0, y0, x1, y1 = table_bbox
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return index
    return None


def _format_block(block: dict, body_size: float | None) -> str:
    """Format one text block as a heading or as body text with list items."""
    non_blank: list[tuple[str, list[dict]]] = []
    for line in block.get("lines", []):
        spans = line.get("spans", [])
        text = "".join(str(span.get("text", "")) for span in spans)
        if text.strip():
            non_blank.append((text, spans))
    if not non_blank:
        return ""

    if body_size is not None:
        dominant = _dominant_size(block)
        total_chars = sum(len(text.strip()) for text, _ in non_blank)
        if (
            dominant is not None
            and len(non_blank) <= 3
            and total_chars <= 150
        ):
            joined = " ".join(text.strip() for text, _ in non_blank)
            collapsed = _collapse_letter_spacing(joined).strip()
            level = _heading_level(dominant, body_size, collapsed)
            if level is not None:
                return "#" * level + " " + collapsed

    paragraph_lines_spans: list[list[dict]] = []
    items: list[str] = []
    for text, spans in non_blank:
        bullet = _bullet_to_markdown(text)
        if bullet is not None:
            items.append(bullet)
            continue
        if items:
            items[-1] = items[-1] + " " + text.strip()
        else:
            paragraph_lines_spans.append(spans)

    parts: list[str] = []
    if paragraph_lines_spans:
        joined_spans = _join_line_spans(paragraph_lines_spans)
        joined_text = _spans_to_markdown(joined_spans)
        if joined_text:
            parts.append(joined_text)
    if items:
        parts.append("\n".join(items))
    return "\n".join(parts)


def read(
    path: Path,
    *,
    detect_tables: bool = True,
    strip_furniture: bool = True,
) -> Iterator[Chunk]:
    """Yield one Chunk per non-empty page of the PDF at path.

    Generator: the file is not opened until iteration begins, and the
    document handle is released as soon as the generator is closed, even if
    the consumer stops early.
    """
    try:
        doc = pymupdf.open(path)
    except PermissionError as exc:
        raise FileLockedError() from exc
    except (RuntimeError, ValueError) as exc:
        raise CorruptFileError(
            f"This PDF could not be opened: {path.name}"
        ) from exc

    with doc:
        if doc.needs_pass and not doc.authenticate(""):
            raise PasswordProtectedError()
        if doc.page_count == 0:
            raise CorruptFileError("This PDF has no pages.")

        # Only the body size is used now; the heading-size list is kept in
        # the helper's return value for scripts/inspect_fonts.py.
        body_size, _unused_heading_sizes = _estimate_sizes(doc)

        furniture: set[tuple[str, float, str]] = set()
        if strip_furniture:
            furniture = set(_learn_furniture(doc))

        pages_skipped = 0
        chunks_emitted = 0

        for n in range(doc.page_count):
            page = doc[n]
            data = page.get_text("dict", flags=_DICT_FLAGS)
            page_height = float(data.get("height", 0.0))
            text_blocks = [
                _clean_block(block)
                for block in data.get("blocks", [])
                if block.get("type") == 0
            ]

            raw_text = _extract_raw_text(text_blocks)
            if not raw_text.strip():
                pages_skipped += 1
                logger.debug("Skipping blank page %d of %s", n + 1, path.name)
                continue

            accepted_tables: list[
                tuple[tuple[float, float, float, float], str]
            ] = []
            if detect_tables:
                try:
                    finder = page.find_tables()
                    for table in finder.tables:
                        if table.row_count < 2 or table.col_count < 2:
                            continue
                        rows = table.extract()
                        cleaned_rows: list[list[str | None]] = [
                            [
                                _clean_text(cell) if cell is not None else None
                                for cell in row
                            ]
                            for row in rows
                        ]
                        md = _table_to_markdown(cleaned_rows)
                        if not md:
                            continue
                        bbox = tuple(float(v) for v in table.bbox)
                        accepted_tables.append(
                            ((bbox[0], bbox[1], bbox[2], bbox[3]), md)
                        )
                except Exception:
                    logger.warning(
                        "Table detection failed on page %d of %s",
                        n + 1,
                        path.name,
                    )

            emitted_tables: set[int] = set()
            block_outputs: list[str] = []
            for block in text_blocks:
                if furniture:
                    sig = _block_signature(block, page_height)
                    if sig is not None and sig in furniture:
                        continue
                table_index = _find_containing_table(block, accepted_tables)
                if table_index is not None:
                    if table_index not in emitted_tables:
                        block_outputs.append(accepted_tables[table_index][1])
                        emitted_tables.add(table_index)
                    continue
                block_md = _format_block(block, body_size)
                if block_md:
                    block_outputs.append(block_md)

            for index, (_, md) in enumerate(accepted_tables):
                if index not in emitted_tables:
                    block_outputs.append(md)

            markdown = "\n\n".join(block_outputs).strip()
            if not markdown:
                pages_skipped += 1
                continue

            chunks_emitted += 1
            yield Chunk(index=n + 1, markdown=markdown, raw_text=raw_text)

        if chunks_emitted == 0:
            raise NoTextLayerError()
        if pages_skipped:
            logger.info(
                "Skipped %d page(s) with no text in %s",
                pages_skipped,
                path.name,
            )