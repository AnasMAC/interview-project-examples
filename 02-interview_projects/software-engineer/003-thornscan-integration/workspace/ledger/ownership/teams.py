"""Map a finding to the team that owns it: the OWNERS rule for its path, else the repository's team."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ledger.core import log
from ledger.core.config import Settings
from ledger.core.models import Location, LocationKind, Repo
from ledger.core.repo import team_by_slug
from ledger.ownership.owners import OwnersFile

_log = log.get_logger("ledger.ownership.teams")


def owners_path(settings: Settings, repo: Repo) -> Path:
    return settings.samples_dir / "repos" / repo.name / "OWNERS"


def resolve_team_id(conn: sqlite3.Connection, repo: Repo, location: Location, owners: OwnersFile | None) -> int:
    """Owning team id for a finding at ``location``.

    Only code locations are looked up in OWNERS; URL and package findings, paths
    no rule covers and slugs Ledger does not know fall back to ``repo.team_id``.
    """
    if owners is None or location.kind != LocationKind.CODE or not location.path:
        return repo.team_id
    slug = owners.team_for(location.path)
    if slug is None:
        return repo.team_id
    team = team_by_slug(conn, slug)
    if team is None:
        _log.warning("ownership.unknown_team", extra={"repo": repo.name, "team": slug, "path": location.path})
        return repo.team_id
    return team.id
