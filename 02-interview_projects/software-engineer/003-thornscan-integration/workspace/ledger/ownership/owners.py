"""OWNERS files: which team owns which paths of a repository.

CODEOWNERS-like syntax, one rule per line::

    # Payments owns the service; exceptions follow the broad rule.
    *                     @fernwick/payments
    /src/checkout/auth/   @fernwick/identity
    Dockerfile            @fernwick/platform   # trailing comments are fine

Paths are repo-relative POSIX paths, as ``normalize.paths.normalize_path``
produces them. Pattern rules:

* ``*`` matches within one path segment, ``?`` one character, ``**`` across segments;
* a leading ``/``, or a ``/`` inside the pattern, anchors it at the repository root;
* a pattern without ``/`` matches the file name at any depth (``*.sql``, ``Dockerfile``);
* a trailing ``/`` matches everything below a directory (``docs/`` at any depth,
  ``/docs/`` only at the root);
* anything else must match the whole path: ``/src/auth`` does not cover ``src/auth/login.py``.

The last matching rule wins, so broad rules go first and exceptions after them.
Each rule names exactly one team, as ``@fernwick/<slug>`` (GitHub style) or ``@<slug>``.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path

from ledger.core.errors import ParseError

_OWNER = re.compile(r"@(?:[A-Za-z0-9_.-]+/)?([a-z0-9][a-z0-9-]*)")
_TRAILING_COMMENT = re.compile(r"\s+#.*$")


@dataclass(frozen=True)
class OwnerRule:
    pattern: str
    team: str  # slug without "@" or org prefix
    line: int

    def matches(self, path: str) -> bool:
        return _compile(self.pattern).fullmatch(path) is not None


@dataclass(frozen=True)
class OwnersFile:
    rules: tuple[OwnerRule, ...]

    def team_for(self, path: str) -> str | None:
        """Slug of the team owning ``path`` (last matching rule wins), or None when no rule matches."""
        path = path.replace("\\", "/").removeprefix("./").lstrip("/")
        for rule in reversed(self.rules):
            if rule.matches(path):
                return rule.team
        return None


def parse_owners(text: str, *, source: str = "OWNERS") -> OwnersFile:
    rules = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pattern, *owners = _TRAILING_COMMENT.sub("", line).split()
        if len(owners) != 1:
            problem = "has no team" if not owners else "names more than one team"
            raise ParseError(f"{source}:{number}: rule {pattern!r} {problem}", source=source, line=number)
        match = _OWNER.fullmatch(owners[0])
        if match is None:
            raise ParseError(
                f"{source}:{number}: owner {owners[0]!r} is not a team (@fernwick/<slug>)", source=source, line=number
            )
        if not pattern.strip("/"):
            raise ParseError(f"{source}:{number}: empty pattern {pattern!r}", source=source, line=number)
        rules.append(OwnerRule(pattern=pattern, team=match.group(1), line=number))
    return OwnersFile(tuple(rules))


def load_owners(path: Path) -> OwnersFile | None:
    """Parse the OWNERS file at ``path``; None when the repository has none."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as exc:
        raise ParseError(f"{path}: OWNERS file is not UTF-8", source=str(path)) from exc
    return parse_owners(text, source=str(path))


@functools.lru_cache(maxsize=1024)
def _compile(pattern: str) -> re.Pattern[str]:
    directory = pattern.endswith("/")
    body = pattern.strip("/")
    anchored = pattern.startswith("/") or "/" in body
    parts = [] if anchored else ["(?:.*/)?"]
    i = 0
    while i < len(body):
        if body.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif body.startswith("**", i):
            parts.append(".*")
            i += 2
        else:
            parts.append({"*": "[^/]*", "?": "[^/]"}.get(body[i]) or re.escape(body[i]))
            i += 1
    if directory:
        parts.append("/.+")
    return re.compile("".join(parts))
