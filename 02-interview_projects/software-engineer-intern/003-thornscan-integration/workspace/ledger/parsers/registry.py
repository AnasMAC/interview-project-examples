"""Parser registry: which parser reads a report, decided by its content.

CI jobs upload whatever file the scanner wrote, often under a generic name
(``report.json``, ``results.xml``), so detection looks at the content first:
every registered parser is asked to ``sniff`` the start of the file, in
registration order. The file name only breaks a tie between parsers that
both claim the content (its suffix against ``Parser.extensions``); after
that, the first registered parser wins.

The built-in parsers are registered on first use, in ``BUILTIN_MODULES``
order. A new format is a module exposing ``PARSER`` added to that tuple.
"""

from __future__ import annotations

import importlib
import threading
from pathlib import PurePath
from typing import Protocol

from ledger.core import log
from ledger.core.errors import ParseError, UnknownFormat
from ledger.core.models import ParsedReport

# Sniffing order. SARIF before Kitewatch: both are JSON objects, and SARIF has the stricter marker.
BUILTIN_MODULES = ("sarif", "kitewatch", "depwarden", "pentest_csv")
# TODO(priya): Thornscan writes .jsonl; detecting by file extension first would save sniffing every upload.

_log = log.get_logger("parsers.registry")
_lock = threading.Lock()
_parsers: dict[str, Parser] = {}
_builtins_loaded = False


class Parser(Protocol):
    format: str

    def sniff(self, data: bytes, filename: str | None) -> bool: ...

    def parse(self, data: bytes, *, source: str) -> ParsedReport: ...


def register(parser: Parser) -> Parser:
    """Add ``parser`` after the built-ins; registering another parser under a taken format is an error."""
    _load_builtins()
    with _lock:
        _add(parser)
    return parser


def formats() -> list[str]:
    return list(_load_builtins())


def get_parser(fmt: str) -> Parser:
    parser = _load_builtins().get(fmt)
    if parser is None:
        raise UnknownFormat(f"unknown report format {fmt!r}", format=fmt, formats=formats())
    return parser


def detect(data: bytes, filename: str | None = None) -> Parser:
    """The parser for ``data``; UnknownFormat when no parser recognises it."""
    name = filename or "report"
    if not data or data.isspace():
        raise UnknownFormat(f"{name}: empty report", source=name)
    candidates = []
    for parser in _load_builtins().values():
        try:
            claimed = parser.sniff(data, filename)
        except Exception:  # a sniffer bug must not hide the other formats
            _log.exception("parsers.sniff_failed", extra={"format": parser.format, "source": name})
            claimed = False
        if claimed:
            candidates.append(parser)
    if not candidates:
        raise UnknownFormat(f"{name}: no parser recognises this content", source=name, formats=formats())
    if len(candidates) > 1 and filename:
        suffix = PurePath(filename).suffix.lower()
        by_name = [parser for parser in candidates if suffix in getattr(parser, "extensions", ())]
        if by_name:
            candidates = by_name
    if len(candidates) > 1:
        _log.info("parsers.ambiguous", extra={"source": name, "formats": [p.format for p in candidates]})
    return candidates[0]


def parse_report(data: bytes, *, source: str, fmt: str | None = None) -> ParsedReport:
    """Parse one report file; ``fmt`` skips detection. ParseError / UnknownFormat on bad input."""
    parser = get_parser(fmt) if fmt else detect(data, source)
    try:
        report = parser.parse(data, source=source)
    except ParseError:
        raise
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        # A structurally odd report is the uploader's problem (422), not a server error.
        _log.warning(
            "parsers.malformed", extra={"source": source, "format": parser.format, "error": type(exc).__name__}
        )
        raise ParseError(f"{source}: malformed {parser.format} report", source=source) from exc
    _log.info(
        "parsers.parsed",
        extra={"source": source, "format": report.format, "tool": report.tool, "findings": len(report.findings)},
    )
    return report


def _add(parser: Parser) -> None:
    existing = _parsers.get(parser.format)
    if existing is not None and existing is not parser:
        raise ValueError(f"report format {parser.format!r} is already registered")
    _parsers[parser.format] = parser


def _load_builtins() -> dict[str, Parser]:
    # The API serves requests from several threads; the first ones may arrive together.
    global _builtins_loaded
    if not _builtins_loaded:
        with _lock:
            if not _builtins_loaded:
                for module in BUILTIN_MODULES:
                    _add(importlib.import_module(f"{__package__}.{module}").PARSER)
                _builtins_loaded = True
    return _parsers
