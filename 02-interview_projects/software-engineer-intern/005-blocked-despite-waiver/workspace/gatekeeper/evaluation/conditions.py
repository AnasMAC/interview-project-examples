"""Rule conditions: the ``when:`` block of a policy rule.

``when`` has two optional dimensions, ``branches`` and ``environments``. A
missing dimension matches everything; when both are given, both must match.
Within a dimension any entry may match.

Branch entries are ``fnmatch`` globs matched case-sensitively against the
branch name the adapter produced (``refs/heads/`` already stripped). Note that
``*`` also crosses ``/``: ``release/*`` matches ``release/4.12`` and
``release/4.12/hotfix-1``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase

ENVIRONMENTS = ("production", "staging", "development")
# Spellings of the legacy runner's ``deploy_env``; teams that migrated to
# Forgeline copied them into their policies, so the DSL keeps accepting them.
ENVIRONMENT_ALIASES = {"prod": "production", "stg": "staging", "dev": "development"}


def normalize_environment(name: str) -> str | None:
    """Canonical environment name, or ``None`` for an unknown one."""
    name = name.strip().lower()
    name = ENVIRONMENT_ALIASES.get(name, name)
    return name if name in ENVIRONMENTS else None


def branch_matches(patterns: tuple[str, ...], branch: str) -> bool:
    return any(fnmatchcase(branch, pattern) for pattern in patterns)


@dataclass(frozen=True)
class Condition:
    branches: tuple[str, ...] | None = None
    environments: tuple[str, ...] | None = None

    def matches(self, *, branch: str, environment: str) -> bool:
        if self.branches is not None and not branch_matches(self.branches, branch):
            return False
        return self.environments is None or environment in self.environments
