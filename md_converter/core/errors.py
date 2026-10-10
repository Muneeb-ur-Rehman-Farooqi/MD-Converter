"""User-facing conversion errors for MD Converter."""

from __future__ import annotations


class ConversionError(Exception):
    """Base class for errors that can be shown to the user."""

    def __init__(self, user_message: str) -> None:
        """Store a human-friendly message and expose it through str()."""
        super().__init__(user_message)
        self.user_message = user_message

    def __str__(self) -> str:
        """Return the user-facing message."""
        return self.user_message


class PasswordProtectedError(ConversionError):
    """Raised when a file needs a password before it can be read."""

    DEFAULT_MESSAGE: str = (
        "This file is password-protected. Remove the password in the original "
        "app and try again."
    )

    def __init__(self, message: str | None = None) -> None:
        """Create the error, using the default message when none is given."""
        super().__init__(message if message is not None else self.DEFAULT_MESSAGE)


class CorruptFileError(ConversionError):
    """Raised when a file is damaged or cannot be parsed."""

    DEFAULT_MESSAGE: str = (
        "This file appears to be damaged and cannot be read. Try opening it in "
        "its original app or use a different copy."
    )

    def __init__(self, message: str | None = None) -> None:
        """Create the error, using the default message when none is given."""
        super().__init__(message if message is not None else self.DEFAULT_MESSAGE)


class NoTextLayerError(ConversionError):
    """Raised when a PDF has no extractable text layer."""

    DEFAULT_MESSAGE: str = (
        "This PDF contains only scanned images, so no text can be extracted. "
        "Scanned files need OCR, which is not available yet."
    )

    def __init__(self, message: str | None = None) -> None:
        """Create the error, using the default message when none is given."""
        super().__init__(message if message is not None else self.DEFAULT_MESSAGE)


class FileTooLargeError(ConversionError):
    """Raised when a file is too large for safe conversion on this machine."""

    DEFAULT_MESSAGE: str = (
        "This file is too large to convert safely on this machine. Try splitting "
        "it into smaller files."
    )

    def __init__(self, message: str | None = None) -> None:
        """Create the error, using the default message when none is given."""
        super().__init__(message if message is not None else self.DEFAULT_MESSAGE)


class OutputNotWritableError(ConversionError):
    """Raised when the output folder cannot be written."""

    DEFAULT_MESSAGE: str = (
        "The output folder is not writable. Choose a different folder or check "
        "your permissions."
    )

    def __init__(self, message: str | None = None) -> None:
        """Create the error, using the default message when none is given."""
        super().__init__(message if message is not None else self.DEFAULT_MESSAGE)


class FileLockedError(ConversionError):
    """Raised when another program has the file open."""

    DEFAULT_MESSAGE: str = (
        "The file is open in another program. Close it and try again."
    )

    def __init__(self, message: str | None = None) -> None:
        """Create the error, using the default message when none is given."""
        super().__init__(message if message is not None else self.DEFAULT_MESSAGE)


class UnsupportedFormatError(ConversionError):
    """Raised when the source format is not supported."""

    DEFAULT_MESSAGE: str = (
        "This file format is not supported. Use PDF, DOCX or Markdown."
    )

    def __init__(self, message: str | None = None) -> None:
        """Create the error, using the default message when none is given."""
        super().__init__(message if message is not None else self.DEFAULT_MESSAGE)