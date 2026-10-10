"""Math normalization hook for the Markdown transform pipeline."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import replace

from md_converter.core.models import Chunk


def process_block(markdown: str) -> str:
    """Return the Markdown block unchanged in Phase 1."""
    return markdown


def apply(chunks: Iterable[Chunk]) -> Iterator[Chunk]:
    """Yield chunks with process_block applied to their Markdown.

    Phase 5 will replace process_block only; nothing else in the pipeline changes.
    """
    for chunk in chunks:
        yield replace(chunk, markdown=process_block(chunk.markdown))