"""Tests for md_converter.core.writers.md_writer."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

from md_converter.core.models import Chunk
from md_converter.core.writers.md_writer import write


def test_chunks_separated_by_one_blank_line(tmp_path: Path) -> None:
    """Prove chunks are separated by one blank line and the file ends with LF."""
    output = tmp_path / "out.md"
    chunks = [Chunk(index=1, markdown="one"), Chunk(index=2, markdown="two")]
    write(chunks, output)
    assert output.read_text(encoding="utf-8") == "one\n\ntwo\n"


def test_empty_and_whitespace_chunks_are_skipped(tmp_path: Path) -> None:
    """Prove empty and whitespace-only chunks do not reach the file."""
    output = tmp_path / "out.md"
    chunks = [
        Chunk(index=1, markdown="one"),
        Chunk(index=2, markdown=""),
        Chunk(index=3, markdown="   \n  "),
        Chunk(index=4, markdown="two"),
    ]
    write(chunks, output)
    assert output.read_text(encoding="utf-8") == "one\n\ntwo\n"


def test_no_chunks_gives_empty_file(tmp_path: Path) -> None:
    """Prove an empty iterable writes an empty file."""
    output = tmp_path / "out.md"
    write([], output)
    assert output.read_bytes() == b""


def test_no_bom_and_no_crlf(tmp_path: Path) -> None:
    """Prove the file is UTF-8 without BOM and has LF line endings."""
    output = tmp_path / "out.md"
    chunks = [Chunk(index=1, markdown="one"), Chunk(index=2, markdown="two")]
    write(chunks, output)
    data = output.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in data


def test_non_ascii_round_trip(tmp_path: Path) -> None:
    """Prove non-ASCII text survives a round trip."""
    output = tmp_path / "out.md"
    text = "∑ ∫ α ≤ café"
    write([Chunk(index=1, markdown=text)], output)
    assert output.read_text(encoding="utf-8") == text + "\n"


def test_cancel_preset_writes_nothing(tmp_path: Path) -> None:
    """Prove an already-set cancel event stops the writer before any chunk."""
    output = tmp_path / "out.md"
    cancel = threading.Event()
    cancel.set()
    chunks = [Chunk(index=1, markdown="one")]
    write(chunks, output, cancel)
    assert output.read_bytes() == b""


def test_cancel_mid_stream_stops_before_second_chunk(tmp_path: Path) -> None:
    """Prove cancel set after the first chunk stops the writer before the next.

    The writer must not write the second chunk, but the non-empty file must
    still end with exactly one newline, so the writer breaks out of its loop
    instead of returning early.
    """
    output = tmp_path / "out.md"
    cancel = threading.Event()

    def gen() -> Iterator[Chunk]:
        yield Chunk(index=1, markdown="one")
        cancel.set()
        yield Chunk(index=2, markdown="two")

    write(gen(), output, cancel)
    assert output.read_text(encoding="utf-8") == "one\n"


def test_writer_consumes_iterable_lazily(tmp_path: Path) -> None:
    """Prove the writer pulls one chunk at a time, not a materialised list.

    If the writer converted the iterable into a list first, the generator
    would be drained up front and cancel would be set before any chunk was
    written, leaving the file empty. Lazy iteration instead pulls exactly
    one chunk beyond the last one written: the generator sets cancel only
    when it is resumed after yielding the second chunk, so a third chunk is
    pulled before the writer notices the flag. That third chunk is never
    written, and the file still ends with a single newline.
    """
    output = tmp_path / "out.md"
    cancel = threading.Event()
    pulls = 0

    def gen() -> Iterator[Chunk]:
        nonlocal pulls
        for i in range(1, 5):
            pulls += 1
            yield Chunk(index=i, markdown=f"chunk {i}")
            if i == 2:
                cancel.set()

    write(gen(), output, cancel)
    assert pulls == 3
    assert output.read_text(encoding="utf-8") == "chunk 1\n\nchunk 2\n"