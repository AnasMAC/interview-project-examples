"""Periscope port-scan results (``periscope scan --output json``).

One ``ip`` observation per host that was up, with its open ports. A host that
is up with no open port is still reported so the merge closes the services
it no longer sees; a host that was down tells us nothing and is skipped.
Only ``open`` ports count: ``closed``, ``filtered`` and the UDP
``open|filtered`` guess are left out.

Periscope reports TLS as ``"tunnel": "ssl"`` next to the protocol it found
inside (``http``), which Atlas stores as the usual name (``https``). Ports
without a service name get the IANA name for well-known ports. Hostnames the
scan was pointed at (``"source": "target"``) become ``host`` observations
resolving to the address; reverse-DNS names (``"ptr"``) are not trusted.
"""

from __future__ import annotations

import json

from atlas.core import clock
from atlas.core.normalize import normalize_hostname, normalize_ip
from atlas.importers.base import (
    ImportBatch,
    ImportFormatError,
    Observation,
    ObservedLink,
    ObservedService,
    parse_timestamp,
)

_TLS_NAMES = {"http": "https", "imap": "imaps", "pop3": "pop3s", "smtp": "smtps", "ldap": "ldaps"}
_WELL_KNOWN = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "domain", 80: "http", 110: "pop3", 123: "ntp",
    143: "imap", 161: "snmp", 443: "https", 445: "microsoft-ds", 3306: "mysql", 3389: "ms-wbt-server",
    5432: "postgresql", 6379: "redis", 8080: "http-alt", 8443: "https-alt",
}
# AssetService column sizes.
_MAX_SERVICE, _MAX_PRODUCT, _MAX_BANNER = 64, 200, 512


def _service(entry: dict) -> ObservedService:
    port = entry.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError(f"invalid port {port!r}")
    protocol = str(entry.get("protocol", "tcp")).lower()
    if protocol not in ("tcp", "udp"):
        raise ValueError(f"port {port}: unsupported protocol {protocol!r}")
    detail = entry.get("service") or {}
    name = str(detail.get("name") or "").lower()
    if detail.get("tunnel") == "ssl":
        name = _TLS_NAMES.get(name, name)
    product = " ".join(str(detail[key]) for key in ("product", "version") if detail.get(key))
    return ObservedService(
        port=port,
        protocol=protocol,
        service=(name or _WELL_KNOWN.get(port, ""))[:_MAX_SERVICE],
        product=product[:_MAX_PRODUCT],
        banner=" ".join(str(detail.get("banner") or "").split())[:_MAX_BANNER],
    )


def parse(text: str, *, source_name: str = "") -> ImportBatch:
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ImportFormatError(f"not a Periscope result: invalid JSON ({error})") from None
    if not isinstance(data, dict) or not isinstance(data.get("hosts"), list):
        raise ImportFormatError("not a Periscope result: no hosts list")
    scan = data.get("scan") if isinstance(data.get("scan"), dict) else {}
    scanner = data.get("scanner") if isinstance(data.get("scanner"), dict) else {}
    warnings: list[str] = []
    try:
        observed_at = parse_timestamp(scan.get("finished_at") or scan.get("started_at"))
    except ValueError:
        observed_at = clock.now()
        warnings.append("scan has no readable finished_at; using the import time")

    ips: dict[str, list[ObservedService]] = {}
    hosts: dict[str, list[ObservedLink]] = {}
    for position, host in enumerate(data["hosts"]):
        if not isinstance(host, dict):
            warnings.append(f"host #{position}: not an object, skipped")
            continue
        try:
            address = normalize_ip(str(host.get("address", "")))
        except ValueError as error:
            warnings.append(f"host #{position}: {error}")
            continue
        if host.get("state", "up") != "up":
            continue
        services = ips.setdefault(address, [])
        for entry in host.get("ports") or []:
            if not isinstance(entry, dict) or entry.get("state") != "open":
                continue
            try:
                service = _service(entry)
            except ValueError as error:
                warnings.append(f"{address}: {error}")
                continue
            # A host listed twice (two scan targets, one address): keep the first sighting of a port.
            if all((s.port, s.protocol) != (service.port, service.protocol) for s in services):
                services.append(service)
        for name in host.get("hostnames") or []:
            if not isinstance(name, dict) or name.get("source") != "target":
                continue
            try:
                link = ObservedLink("resolves_to", "ip", address)
                host_links = hosts.setdefault(normalize_hostname(str(name.get("name", ""))), [])
            except ValueError as error:
                warnings.append(f"{address}: {error}")
                continue
            if link not in host_links:
                host_links.append(link)

    observations = [
        Observation(kind="ip", value=ip, label=ip, attributes={"version": 6 if ":" in ip else 4},
                    services=tuple(services))
        for ip, services in ips.items()
    ]
    observations += [
        Observation(kind="host", value=name, label=name, links=tuple(links)) for name, links in hosts.items()
    ]
    default_name = " ".join(filter(None, [scanner.get("name", "periscope"), scan.get("profile")]))
    return ImportBatch(
        importer="port_scan",
        source_kind="port_scan",
        source_name=source_name or default_name,
        observed_at=observed_at,
        observations=observations,
        warnings=warnings,
    )
