"""Smoke tests for MD Converter Phase 1."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

import pytest

from md_converter import __version__
from md_converter.app import main
from md_converter.config import (
    ensure_app_dirs,
    get_app_data_dir,
    get_logs_dir,
    setup_logging,
)
from md_converter.core.errors import (
    ConversionError,
    CorruptFileError,
    FileLockedError,
    FileTooLargeError,
    NoTextLayerError,
    OutputNotWritableError,
    PasswordProtectedError,
    UnsupportedFormatError,
)
from md_converter.core.models import Chunk, ConversionRequest, DocFormat
from md_converter.core.transforms.math_hook import apply, process_block


ERROR_CLASSES: list[type[ConversionError]] = [
    PasswordProtectedError,
    CorruptFileError,
    NoTextLayerError,
    FileTooLargeError,
    OutputNotWritableError,
    FileLockedError,
    UnsupportedFormatError,
]


def test_version_is_non_empty_string() -> None:
    """Prove the package exposes a non-empty version string."""
    assert isinstance(__version__, str)
    assert __version__


def test_chunk_is_frozen() -> None:
    """Prove Chunk instances cannot be mutated."""
    chunk = Chunk(index=1, markdown="hello")
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(chunk, "index", 2)


def test_conversion_request_defaults(tmp_path: Path) -> None:
    """Prove ConversionRequest starts with no output directory and AI mode off."""
    request = ConversionRequest(
        source=tmp_path / "source.pdf",
        target_format=DocFormat.PDF,
    )
    assert request.output_dir is None
    assert request.ai_mode is False


@pytest.mark.parametrize("error_class", ERROR_CLASSES)
def test_error_classes_have_default_messages(
    error_class: type[ConversionError],
) -> None:
    """Prove each error class has a usable default user message."""
    error = error_class()
    assert isinstance(error, ConversionError)
    assert error.user_message
    assert str(error) == error.user_message


@pytest.mark.parametrize("error_class", ERROR_CLASSES)
def test_error_classes_accept_custom_messages(
    error_class: type[ConversionError],
) -> None:
    """Prove a custom message overrides the default message."""
    error = error_class("custom message")
    assert error.user_message == "custom message"
    assert str(error) == "custom message"


def test_config_uses_appdata_and_creates_dirs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prove config reads APPDATA at call time and only creates dirs on demand."""
    monkeypatch.setenv("APPDATA", str(tmp_path))

    app_dir = get_app_data_dir()
    logs_dir = get_logs_dir()

    assert app_dir == tmp_path / "MDConverter"
    assert not app_dir.exists()
    assert not logs_dir.exists()

    ensure_app_dirs()

    assert app_dir.is_dir()
    assert logs_dir.is_dir()


def test_setup_logging_does_not_duplicate_handlers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prove setup_logging is idempotent and creates a log file."""
    monkeypatch.setenv("APPDATA", str(tmp_path))

    logger = logging.getLogger("md_converter")

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    try:
        setup_logging()
        first_count = len(logger.handlers)

        setup_logging()
        assert len(logger.handlers) == first_count

        logger.info("smoke test message")
        assert (get_logs_dir() / "md_converter.log").exists()
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


def test_math_hook_process_block_is_passthrough() -> None:
    """Prove process_block returns the identical Unicode math string."""
    text = "∑ ∫ α ≤"
    assert process_block(text) == text


def test_math_hook_apply_preserves_chunks() -> None:
    """Prove apply returns equal chunks in Phase 1."""
    chunks = [Chunk(index=1, markdown="∑ ∫ α ≤", raw_text="raw text")]
    assert list(apply(chunks)) == chunks


def test_app_main_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    """Prove main returns success and prints the package version."""
    assert main() == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out