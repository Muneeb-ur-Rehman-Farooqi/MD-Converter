"""Command-line entry point for MD Converter."""

from __future__ import annotations

from md_converter import __version__


def main() -> int:
    """Print the Phase 1 placeholder message and return success."""
    print(f"MD Converter {__version__} - the interface arrives in Phase 2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())