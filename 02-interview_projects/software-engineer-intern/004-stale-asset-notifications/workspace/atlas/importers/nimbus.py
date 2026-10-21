"""Nimbus cloud inventory exports, schema v1 and v2.

Nimbus changed its export with the 2026 account migration; both shapes carry
the same resources under different names (v1 -> v2):

* marker: ``"version": 1`` -> ``"schema": "nimbus.inventory/v2"``
* export time: ``exported_at`` -> ``generatedAt``
* account id: ``account.number`` (``4471-2210-0093``) -> ``account.id``
  (``acct-7f3k9q2mwd``; the old number survives as ``account.legacyNumber``)
* ``resources[]`` -> ``items[]``; ``id`` / ``type`` (``compute.instance``) ->
  ``resourceId`` / ``resourceType`` (``compute/instance``); ``name`` /
  ``region`` -> ``displayName`` / ``location``; ``state`` -> ``lifecycle``
* ``public_ip`` / ``public_ipv6`` -> ``addresses[]`` of ``{"ip", "scope"}``;
  ``dns_names[]`` -> ``endpoints[]``

Each resource becomes a ``cloud_resource`` keyed
``nimbus:<account id>:<resource id>`` with ``attached`` links to its public
addresses and DNS names. Private addresses are not inventory. Terminated
resources are skipped.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

from atlas.core.normalize import normalize_hostname, normalize_ip
from atlas.importers.base import ImportBatch, ImportFormatError, Observation, ObservedLink, parse_timestamp

V2_SCHEMA = "nimbus.inventory/v2"
_GONE_STATES = {"terminated", "deleted"}


def _v1_resource(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "type": item.get("type", ""),
        "name": item.get("name", ""),
        "region": item.get("region", ""),
        "state": item.get("state", ""),
        "public_ips": [ip for ip in (item.get("public_ip"), item.get("public_ipv6")) if ip],
        "dns_names": item.get("dns_names") or [],
    }


def _v2_resource(item: dict) -> dict:
    addresses = item.get("addresses") or []
    return {
        "id": item.get("resourceId"),
        "type": (item.get("resourceType") or "").replace("/", "."),
        "name": item.get("displayName", ""),
        "region": item.get("location", ""),
        "state": item.get("lifecycle", ""),
        "public_ips": [a.get("ip") for a in addresses if isinstance(a, dict) and a.get("scope") == "public"],
        "dns_names": item.get("endpoints") or [],
    }


def _read_export(text: str) -> tuple[str, datetime, list, Callable[[dict], dict]]:
    """Returns (account id, export time, raw items, item mapper) for either schema."""
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ImportFormatError(f"not a Nimbus export: invalid JSON ({error})") from None
    if not isinstance(data, dict) or not isinstance(data.get("account"), dict):
        raise ImportFormatError("not a Nimbus export: no account object")
    if data.get("schema") == V2_SCHEMA:
        id_field, time_field, items_field, mapper = "id", "generatedAt", "items", _v2_resource
    elif data.get("version") == 1:
        id_field, time_field, items_field, mapper = "number", "exported_at", "resources", _v1_resource
    else:
        raise ImportFormatError("unsupported Nimbus export: expected version 1 or schema nimbus.inventory/v2")
    account_id = data["account"].get(id_field)
    if not isinstance(account_id, str) or not account_id.strip():
        raise ImportFormatError(f"Nimbus export without account.{id_field}")
    if not isinstance(data.get(items_field), list):
        raise ImportFormatError(f"Nimbus export without a {items_field!r} list")
    try:
        observed_at = parse_timestamp(data.get(time_field))
    except ValueError as error:
        raise ImportFormatError(f"Nimbus export time: {error}") from None
    return account_id.strip(), observed_at, data[items_field], mapper


def parse(text: str, *, source_name: str = "") -> ImportBatch:
    account_id, observed_at, items, mapper = _read_export(text)
    observations: list[Observation] = []
    warnings: list[str] = []
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            warnings.append(f"resource #{position}: not an object, skipped")
            continue
        resource = mapper(item)
        resource_id = resource["id"]
        if not isinstance(resource_id, str) or not resource_id.strip():
            warnings.append(f"resource #{position}: no resource id, skipped")
            continue
        resource_id = resource_id.strip()
        if str(resource["state"]).lower() in _GONE_STATES:
            warnings.append(f"resource {resource_id}: {resource['state']}, skipped")
            continue
        links: list[ObservedLink] = []
        for raw_ip in resource["public_ips"]:
            try:
                links.append(ObservedLink("attached", "ip", normalize_ip(str(raw_ip))))
            except ValueError as error:
                warnings.append(f"resource {resource_id}: {error}")
        for raw_name in resource["dns_names"]:
            try:
                links.append(ObservedLink("attached", "host", normalize_hostname(str(raw_name))))
            except ValueError as error:
                warnings.append(f"resource {resource_id}: {error}")
        public_ips = [link.value for link in links if link.kind == "ip"]
        observations.append(
            Observation(
                kind="cloud_resource",
                value=f"nimbus:{account_id}:{resource_id}".lower(),
                label=resource["name"] or resource_id,
                attributes={
                    "provider": "nimbus",
                    "account_id": account_id,
                    "resource_type": resource["type"],
                    "region": resource["region"],
                    "public_ip": public_ips[0] if public_ips else None,
                },
                external_id=f"{account_id}/{resource_id}",
                links=tuple(dict.fromkeys(links)),
            )
        )
    return ImportBatch(
        importer="nimbus",
        source_kind="nimbus",
        source_name=source_name or f"nimbus account {account_id}",
        observed_at=observed_at,
        observations=observations,
        warnings=warnings,
    )
