"""Exception hierarchy. The API maps ``status`` and ``to_dict()`` straight to the response."""

from __future__ import annotations

from typing import Any


class LedgerError(Exception):
    code = "ledger_error"
    status = 500

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, **self.details}


class ConfigError(LedgerError):
    code = "config_error"


class MigrationError(LedgerError):
    code = "migration_error"


class InvalidInput(LedgerError):
    code = "invalid_input"
    status = 400


class Unauthorized(LedgerError):
    code = "unauthorized"
    status = 401


class Forbidden(LedgerError):
    code = "forbidden"
    status = 403


class NotFound(LedgerError):
    code = "not_found"
    status = 404


class Conflict(LedgerError):
    code = "conflict"
    status = 409


class PayloadTooLarge(LedgerError):
    code = "payload_too_large"
    status = 413


class ParseError(LedgerError):
    """A scanner report that cannot be read. Details usually carry ``source`` and ``line``."""

    code = "parse_error"
    status = 422


class UnknownFormat(ParseError):
    code = "unknown_format"
    status = 415
