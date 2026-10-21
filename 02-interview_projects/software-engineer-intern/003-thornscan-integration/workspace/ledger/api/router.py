"""A small method + path router.

Patterns are literal segments and ``{name}`` / ``{name:int}`` placeholders,
each matching exactly one path segment. A trailing slash is ignored
(``/api/v1/findings/`` is ``/api/v1/findings``). A path that matches no
pattern is a 404; a path that matches only under other methods is a 405 whose
``allowed`` detail lists them (the server sends it as the ``Allow`` header).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ledger.core.errors import LedgerError, NotFound

_PLACEHOLDER = re.compile(r"\{([a-z_]+)(?::(int))?\}")
_CONVERTERS: dict[str | None, tuple[str, Callable[[str], Any]]] = {
    None: (r"[^/]+", str),
    "int": (r"[0-9]{1,18}", int),
}


class MethodNotAllowed(LedgerError):
    code = "method_not_allowed"
    status = 405


@dataclass(frozen=True)
class Route:
    method: str
    pattern: str
    handler: Callable[..., Any]
    role: str | None                    # None = no authentication
    regex: re.Pattern[str]
    converters: dict[str, Callable[[str], Any]]


class Router:
    def __init__(self) -> None:
        self.routes: list[Route] = []

    def add(self, method: str, pattern: str, handler: Callable[..., Any], *, role: str | None) -> None:
        converters: dict[str, Callable[[str], Any]] = {}
        parts, last = [], 0
        for found in _PLACEHOLDER.finditer(pattern):
            regex, convert = _CONVERTERS[found.group(2)]
            parts.append(re.escape(pattern[last:found.start()]) + f"(?P<{found.group(1)}>{regex})")
            converters[found.group(1)] = convert
            last = found.end()
        parts.append(re.escape(pattern[last:]))
        self.routes.append(Route(method.upper(), pattern, handler, role, re.compile("".join(parts)), converters))

    def resolve(self, method: str, path: str) -> tuple[Route, dict[str, Any]]:
        path = path.rstrip("/") or "/"
        allowed = []
        for route in self.routes:
            found = route.regex.fullmatch(path)
            if found is None:
                continue
            if route.method == method.upper():
                return route, {name: route.converters[name](value) for name, value in found.groupdict().items()}
            allowed.append(route.method)
        if allowed:
            raise MethodNotAllowed(f"{method} not allowed on {path}", allowed=sorted(set(allowed)))
        raise NotFound(f"no route for {path}", path=path)
