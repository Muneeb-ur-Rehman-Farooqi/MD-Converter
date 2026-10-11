"""Diagnostic tool: dump font/typography facts about pages of a PDF.

Examples:
    python -m scripts.inspect_fonts "C:\\Dev\\samples\\report.pdf" 1
    python -m scripts.inspect_fonts "C:\\Dev\\samples\\report.pdf" 1-3 5 7-9

This is a developer tool for the architect, not a product feature. It never
modifies the PDF and it prints everything to stdout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf

from md_converter.core.readers.pdf_reader import _estimate_sizes

_DICT_FLAGS = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES


def _round_size(size: float) -> float:
    """Round a font size to the nearest 0.5."""
    return round(size * 2) / 2


def _parse_page_spec(value: str) -> list[int]:
    """Parse a single CLI page argument as 'N' or 'N-M' into a list of ints."""
    text = value.strip()
    if "-" in text:
        parts = text.split("-")
        if len(parts) != 2:
            raise argparse.ArgumentTypeError(
                f"invalid page spec {value!r}; use N or N-M"
            )
        try:
            start = int(parts[0])
            end = int(parts[1])
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"invalid page spec {value!r}; use N or N-M"
            ) from exc
        if start < 1 or end < start:
            raise argparse.ArgumentTypeError(
                f"invalid page range {value!r}; start must be >= 1 and <= end"
            )
        return list(range(start, end + 1))
    try:
        number = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid page number {value!r}"
        ) from exc
    if number < 1:
        raise argparse.ArgumentTypeError(
            f"page numbers must be >= 1, got {number}"
        )
    return [number]


def _flatten_pages(specs: list[list[int]]) -> list[int]:
    """Flatten parsed page specs, removing duplicates, keeping first-seen order."""
    seen: set[int] = set()
    ordered: list[int] = []
    for spec in specs:
        for number in spec:
            if number not in seen:
                seen.add(number)
                ordered.append(number)
    return ordered


def _block_lines_text(block: dict) -> list[str]:
    """Return the block's line texts, one entry per line, in PyMuPDF order."""
    texts: list[str] = []
    for line in block.get("lines", []):
        parts = [str(span.get("text", "")) for span in line.get("spans", [])]
        texts.append("".join(parts))
    return texts


def _block_is_blank(block: dict) -> bool:
    """Return True when the block has no non-whitespace text at all."""
    for text in _block_lines_text(block):
        if text.strip():
            return False
    return True


def _non_blank_line_count(block: dict) -> int:
    """Count the block's non-blank lines."""
    return sum(1 for text in _block_lines_text(block) if text.strip())


def _dominant_size_and_font(block: dict) -> tuple[float | None, str]:
    """Return the rounded size and font with the most characters in the block."""
    size_counts: dict[float, int] = {}
    font_counts: dict[str, int] = {}
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = str(span.get("text", ""))
            if not text:
                continue
            size = _round_size(float(span.get("size", 0.0)))
            size_counts[size] = size_counts.get(size, 0) + len(text)
            font = str(span.get("font", ""))
            font_counts[font] = font_counts.get(font, 0) + len(text)
    if not size_counts:
        return None, ""
    dominant_size = max(size_counts.items(), key=lambda item: item[1])[0]
    dominant_font = max(font_counts.items(), key=lambda item: item[1])[0]
    return dominant_size, dominant_font


def _bold_and_total_chars(block: dict) -> tuple[int, int]:
    """Return (characters in bold spans, total characters) for the block."""
    bold_chars = 0
    total_chars = 0
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = str(span.get("text", ""))
            length = len(text)
            if length == 0:
                continue
            total_chars += length
            if int(span.get("flags", 0)) & pymupdf.TEXT_FONT_BOLD:
                bold_chars += length
    return bold_chars, total_chars


def _block_preview(block: dict, limit: int = 70) -> str:
    """Return the first `limit` characters of the block's collapsed text."""
    line_texts = [text.strip() for text in _block_lines_text(block)]
    joined = " ".join(text for text in line_texts if text)
    collapsed = " ".join(joined.split())
    return collapsed[:limit]


def _y0(block: dict) -> float:
    """Return the block's bbox y0, or 0.0 when bbox is missing."""
    bbox = block.get("bbox")
    if not bbox:
        return 0.0
    return float(bbox[1])


def _print_page(doc: object, page_number: int) -> None:
    """Print the block table for one 1-based page number."""
    page = doc[page_number - 1]
    data = page.get_text("dict", flags=_DICT_FLAGS)
    blocks = data.get("blocks", [])

    print(f"=== page {page_number} ===")
    header = (
        f"{'#':>3}  {'y0':>6}  {'lines':>5}  {'size':>6}  "
        f"{'B':>1}  {'font':<24}  text"
    )
    print(header)

    visible_index = 0
    for block in blocks:
        if block.get("type") != 0:
            continue
        if _block_is_blank(block):
            continue
        visible_index += 1

        size, font = _dominant_size_and_font(block)
        bold_chars, total_chars = _bold_and_total_chars(block)
        bold_flag = "B" if total_chars > 0 and bold_chars * 2 > total_chars else "-"
        line_count = _non_blank_line_count(block)
        y0 = round(_y0(block))
        size_text = f"{size:>6.1f}" if size is not None else f"{'n/a':>6}"
        preview = _block_preview(block)
        print(
            f"{visible_index:>3}  {y0:>6}  {line_count:>5}  {size_text}  "
            f"{bold_flag:>1}  {font:<24}  {preview}"
        )


def _print_histogram(
    doc: object,
    page_numbers: list[int],
    top_n: int = 8,
) -> None:
    """Print the top-N rounded sizes by character count across the pages."""
    counts: dict[float, int] = {}
    for page_number in page_numbers:
        page = doc[page_number - 1]
        data = page.get_text("dict", flags=_DICT_FLAGS)
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            if _block_is_blank(block):
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text", ""))
                    if not text:
                        continue
                    size = _round_size(float(span.get("size", 0.0)))
                    counts[size] = counts.get(size, 0) + len(text)

    print()
    print("histogram (characters per rounded size):")
    if not counts:
        print("  (no text on the requested pages)")
        return
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    for size, chars in ranked[:top_n]:
        print(f"  {size:.1f}: {chars}")


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the inspector."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.inspect_fonts",
        description=(
            "Dump font/typography facts about one or more pages of a PDF."
        ),
    )
    parser.add_argument(
        "pdf",
        type=Path,
        help="Path to the PDF file.",
    )
    parser.add_argument(
        "pages",
        nargs="+",
        type=_parse_page_spec,
        help="One or more 1-based page numbers or ranges (e.g. 1, 3-6).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the font inspector and return an exit code."""
    # The Windows console uses a legacy code page, so characters it cannot
    # encode (math symbols, box drawing, etc.) would raise UnicodeEncodeError
    # and kill the script. Reconfigure stdout to replace such characters.
    sys.stdout.reconfigure(errors="replace")

    parser = _build_parser()
    args = parser.parse_args(argv)

    pdf_path: Path = args.pdf
    if not pdf_path.is_file():
        print(f"error: not a file: {pdf_path}", file=sys.stderr)
        return 2

    try:
        doc = pymupdf.open(pdf_path)
    except Exception as exc:
        print(f"error: could not open {pdf_path}: {exc}", file=sys.stderr)
        return 2

    with doc:
        page_count = int(doc.page_count)
        if page_count <= 0:
            print(f"error: {pdf_path} has no pages", file=sys.stderr)
            return 2

        requested = _flatten_pages(args.pages)
        out_of_range = [n for n in requested if n < 1 or n > page_count]
        if out_of_range:
            print(
                f"error: page(s) out of range 1..{page_count}: "
                f"{', '.join(str(n) for n in out_of_range)}",
                file=sys.stderr,
            )
            return 2

        body_size, heading_sizes = _estimate_sizes(doc)
        body_text = (
            f"{body_size:.1f}" if body_size is not None else "none"
        )
        if heading_sizes:
            headings_text = "[" + ", ".join(
                f"{size:.1f}" for size in heading_sizes
            ) + "]"
        else:
            headings_text = "[]"
        print(
            f"{pdf_path.name} | pages: {page_count} | "
            f"body size: {body_text} | heading sizes: {headings_text}"
        )

        for page_number in requested:
            print()
            _print_page(doc, page_number)

        _print_histogram(doc, requested)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())