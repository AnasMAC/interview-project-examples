"""Importer lookup by the name stored in ``import.run`` job payloads."""

from __future__ import annotations

from collections.abc import Callable

from atlas.importers import ct_feed, nimbus, port_scan, zone_file
from atlas.importers.base import ImportBatch

IMPORTERS: dict[str, Callable[..., ImportBatch]] = {
    "zone_file": zone_file.parse,
    "nimbus": nimbus.parse,
    "ct_feed": ct_feed.parse,
    "port_scan": port_scan.parse,
}


class UnknownImporter(KeyError):
    """No importer is registered under that name (permanent job failure)."""


def get_importer(name: str) -> Callable[..., ImportBatch]:
    try:
        return IMPORTERS[name]
    except KeyError:
        known = ", ".join(sorted(IMPORTERS))
        raise UnknownImporter(f"unknown importer {name!r} (known: {known})") from None
