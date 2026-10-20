"""Application exceptions with messages that are safe to show to users."""

from __future__ import annotations


class TDIError(Exception):
    """Base class. ``str(exc)`` is always a user-safe message."""


class ValidationFailure(TDIError):  # noqa: N818 - domain term, not an error-suffix class
    """Input failed validation.

    ``errors`` maps a field key (for example ``"quantity"`` or ``"ingredients[0].quantity"``)
    to a message. Model-level problems use the key ``"__all__"``.
    """

    def __init__(self, errors: dict[str, str] | str):
        if isinstance(errors, str):
            errors = {"__all__": errors}
        self.errors: dict[str, str] = dict(errors)
        super().__init__(" ".join(self.errors.values()))


class NotFound(TDIError):  # noqa: N818
    """A referenced record does not exist."""


class Conflict(TDIError):  # noqa: N818
    """The operation conflicts with existing data (duplicate identifier, record in use)."""


class StorageError(TDIError):
    """The database could not complete the operation. Nothing was saved."""

    DEFAULT_MESSAGE = "The record could not be saved. Your changes have not been confirmed."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.DEFAULT_MESSAGE)
