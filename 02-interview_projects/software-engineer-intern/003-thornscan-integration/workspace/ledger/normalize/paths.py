"""Repo-relative POSIX paths for code findings.

Scanners report paths the way they saw them: relative to the checkout,
``./``-prefixed, Windows-style from the Windows build agents, or absolute
inside the CI workspace. Fingerprints and OWNERS matching need one spelling,
so everything becomes ``src/payments/refunds.py``. Case is kept: the repos
are built on Linux, where ``Refunds.py`` and ``refunds.py`` are two files.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from ledger.core.models import Repo

# Checkout directories of our CI runners, in the order they are tried when
# the repo name does not appear in the path.
_CI_PREFIXES = (
    re.compile(r"^/builds/[^/]+/[^/]+/"),  # GitLab runners: /builds/<group>/<repo>/
    re.compile(r"^[a-z]:/builds/[^/]+/[^/]+/", re.IGNORECASE),  # Windows runners
    re.compile(r"^[a-z]:/ci/work/[^/]+/", re.IGNORECASE),  # Windows build agents: C:\ci\work\<repo>\
    re.compile(r"^/home/ci/work/[^/]+/"),  # Linux build agents
)
_ABSOLUTE = re.compile(r"^(?:/|[a-z]:/)", re.IGNORECASE)


def normalize_path(raw: str, *, repo: Repo | None = None) -> str:
    """Return ``raw`` as a repo-relative POSIX path.

    With ``repo``, an absolute path is cut after the first segment equal to
    the repo name, which also covers nested groups and a repo that moved to
    another group. Paths outside any known workspace stay absolute.
    """
    path = raw.strip()
    if path[:7].lower() == "file://":
        path = unquote(path[7:])
        if re.match(r"^/[a-z]:/", path, re.IGNORECASE):  # file:///C:/ci/...
            path = path[1:]
    path = path.replace("\\", "/")
    if _ABSOLUTE.match(path):
        path = _strip_workspace(path, repo)
    absolute = path.startswith("/")
    segments = [part for part in path.split("/") if part not in ("", ".")]
    return ("/" if absolute else "") + "/".join(segments)


def _strip_workspace(path: str, repo: Repo | None) -> str:
    if repo is not None:
        segments = path.split("/")
        if repo.name in segments[:-1]:
            return "/".join(segments[segments.index(repo.name) + 1 :])
    for prefix in _CI_PREFIXES:
        match = prefix.match(path)
        if match:
            return path[match.end() :]
    return path
