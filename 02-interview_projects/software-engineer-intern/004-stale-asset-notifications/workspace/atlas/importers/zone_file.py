"""BIND-style zone files (RFC 1035 master file format, the parts customers use).

Handled: ``$ORIGIN`` (also relative to the current origin) and ``$TTL``;
``@``; relative and absolute owner names; a blank owner meaning "same as the
previous record"; optional TTL (``3600``, ``1h30m``) and class in either
order; ``;`` comments outside quotes; records spread over several lines with
parentheses (SOA, long TXT).

Inventory produced: the zone apex as a ``domain``, every owner name with
A/AAAA/CNAME records as a ``host`` with ``resolves_to`` / ``cname`` links, and
in-zone MX exchanges as hosts. Other record types are read and ignored.
Wildcard owners, names outside the zone and ``$INCLUDE`` are skipped with a
warning. The file carries no export time, so ``observed_at`` is now.
"""

from __future__ import annotations

import re

from atlas.core import clock
from atlas.core.normalize import normalize_hostname, normalize_ip
from atlas.importers.base import ImportBatch, ImportFormatError, Observation, ObservedLink

_TTL = re.compile(r"^\d+[smhdw]?(?:\d+[smhdw])*$", re.IGNORECASE)
_CLASSES = {"IN", "CH", "HS"}
_IGNORED_TYPES = {"SOA", "NS", "TXT", "SPF", "SRV", "CAA", "PTR", "DS", "DNSKEY", "HTTPS", "SVCB", "TLSA"}


def _tokens(line: str) -> list[str]:
    """Split one physical line; parentheses are separate tokens, comments dropped."""
    tokens: list[str] = []
    current = ""
    quoted = escaped = False
    for char in line:
        if escaped or char == "\\":
            current += char
            escaped = not escaped
        elif quoted or char == '"':
            current += char
            quoted ^= char == '"'
        elif char == ";":
            break
        elif char.isspace() or char in "()":
            if current:
                tokens.append(current)
                current = ""
            if char in "()":
                tokens.append(char)
        else:
            current += char
    if current:
        tokens.append(current)
    return tokens


def _records(text: str):
    """Yield ``(line number, inherits owner, tokens)`` per logical record."""
    depth = start = 0
    inherits = False
    pending: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        tokens = _tokens(line)
        if depth == 0:
            if not tokens:
                continue
            start, inherits, pending = lineno, line[:1] in (" ", "\t"), []
        for piece in tokens:
            if piece == "(":
                depth += 1
            elif piece == ")":
                depth -= 1
                if depth < 0:
                    raise ImportFormatError(f"line {lineno}: ')' without '('")
            else:
                pending.append(piece)
        if depth == 0 and pending:
            yield start, inherits, pending
    if depth:
        raise ImportFormatError(f"line {start}: '(' is never closed")


def _absolute(name: str, origin: str | None) -> str:
    if name == "@":
        if origin is None:
            raise ValueError("'@' used before $ORIGIN")
        return origin
    if name.endswith("."):
        return normalize_hostname(name, allow_wildcard=True)
    if origin is None:
        raise ValueError(f"relative name {name!r} without $ORIGIN")
    return normalize_hostname(f"{name}.{origin}", allow_wildcard=True)


def _type_and_rdata(tokens: list[str]) -> tuple[str, list[str]]:
    index = 0
    while index < min(len(tokens), 2) and (_TTL.match(tokens[index]) or tokens[index].upper() in _CLASSES):
        index += 1
    if index >= len(tokens):
        raise ValueError("record has no type")
    return tokens[index].upper(), tokens[index + 1 :]


def _in_zone(name: str, apex: str | None) -> bool:
    return apex is None or name == apex or name.endswith("." + apex)


def parse(text: str, *, source_name: str = "") -> ImportBatch:
    origin: str | None = None
    apex: str | None = None
    owner: str | None = None
    links: dict[str, list[ObservedLink]] = {}  # owner name -> links, in file order
    warnings: list[str] = []
    records_read = 0

    for lineno, inherits, tokens in _records(text):
        if tokens[0].startswith("$"):
            directive = tokens[0].upper()
            if directive == "$ORIGIN" and len(tokens) > 1:
                try:
                    origin = _absolute(tokens[1], origin)
                except ValueError as error:
                    raise ImportFormatError(f"line {lineno}: bad $ORIGIN: {error}") from None
                apex = apex or origin
            elif directive != "$TTL":
                warnings.append(f"line {lineno}: {directive} is not supported, skipped")
            continue
        try:
            if not inherits:
                owner = None  # a bad owner name also voids the records inheriting it
                owner = _absolute(tokens.pop(0), origin)
            elif owner is None:
                raise ValueError("record without an owner name")
            rtype, rdata = _type_and_rdata(tokens)
            if rtype in _IGNORED_TYPES:
                if rtype == "SOA" and apex is None:
                    apex = owner
                records_read += 1
                continue
            if rtype not in ("A", "AAAA", "CNAME", "MX"):
                raise ValueError(f"unsupported record type {rtype}")
            if not rdata:
                raise ValueError(f"{rtype} record without data")
            if owner.startswith("*."):
                raise ValueError(f"wildcard record {owner} is not an inventory host, skipped")
            if not _in_zone(owner, apex):
                raise ValueError(f"{owner} is outside the zone {apex}, skipped")
            records_read += 1
            if rtype == "MX":
                exchange = rdata[-1]
                if exchange != "." and _in_zone(target := _absolute(exchange, origin), apex):
                    links.setdefault(target, [])
                continue
            if rtype == "CNAME":
                link = ObservedLink("cname", "host", _absolute(rdata[0], origin))
            else:
                address = normalize_ip(rdata[0])
                if (":" in address) != (rtype == "AAAA"):
                    raise ValueError(f"{rtype} record with address {rdata[0]!r}")
                link = ObservedLink("resolves_to", "ip", address)
            entry = links.setdefault(owner, [])
            if link not in entry:
                entry.append(link)
        except ValueError as error:  # NormalizationError included
            warnings.append(f"line {lineno}: {error}")

    if records_read == 0:
        raise ImportFormatError("no DNS records found; is this a zone file?")
    if apex is not None:
        links = {apex: links.pop(apex, [])} | links
    attributes = {"zone": apex} if apex else {}
    observations = [
        Observation(
            kind="domain" if name == apex else "host",
            value=name,
            label=name,
            attributes=dict(attributes),
            links=tuple(name_links),
        )
        for name, name_links in links.items()
    ]
    return ImportBatch(
        importer="zone_file",
        source_kind="zone_file",
        source_name=source_name or (f"{apex} zone" if apex else "zone file"),
        observed_at=clock.now(),
        observations=observations,
        warnings=warnings,
    )
