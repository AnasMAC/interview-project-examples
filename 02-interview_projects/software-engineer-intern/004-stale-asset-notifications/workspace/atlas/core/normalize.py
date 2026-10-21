"""Canonical forms for hostnames, IP addresses and networks.

Every importer, the merge step and the API normalize through these functions
so the same asset reached by different sources gets the same key:

* hostnames: trimmed, one trailing dot dropped (zone files write FQDNs as
  ``www.example.test.``), lower-cased, non-ASCII labels converted to A-labels
  with UTS 46 / IDNA 2008 (``idna`` package, non-transitional, so ``ß`` stays
  distinct from ``ss``). Underscore labels (``_dmarc``) are accepted.
* IPs: ``ipaddress`` text form, so IPv6 is compressed and lower-case;
  IPv4-mapped IPv6 (``::ffff:198.51.100.7``) becomes the IPv4 address.
* networks: ``ip_network(strict=False)``, so host bits are cleared.
"""

from __future__ import annotations

import ipaddress
import re

import idna

_LABEL = re.compile(r"^(?!-)[a-z0-9_-]{1,63}(?<!-)$")

# Not reachable from the internet. Documentation ranges (192.0.2.0/24,
# 198.51.100.0/24, 203.0.113.0/24, 2001:db8::/32) are deliberately absent:
# Atlas fixtures and the seed use them as "public" addresses.
_NON_PUBLIC = [
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4",
        "::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8",
    )
]


class NormalizationError(ValueError):
    """The value cannot be turned into a canonical hostname, IP or network."""


def normalize_hostname(value: str, *, allow_wildcard: bool = False) -> str:
    name = value.strip()
    if name.endswith("."):
        name = name[:-1]
    if name == "":
        raise NormalizationError(f"empty hostname: {value!r}")
    labels = []
    for index, label in enumerate(name.split(".")):
        if label == "*" and index == 0 and allow_wildcard:
            labels.append(label)
            continue
        if label.isascii():
            label = label.lower()
        else:
            try:
                label = idna.alabel(idna.uts46_remap(label, std3_rules=False)).decode("ascii")
            except idna.IDNAError as error:
                raise NormalizationError(f"invalid hostname label {label!r}: {error}") from None
        if _LABEL.match(label) is None:
            raise NormalizationError(f"invalid hostname label {label!r} in {value!r}")
        labels.append(label)
    hostname = ".".join(labels)
    if len(hostname) > 253:
        raise NormalizationError(f"hostname longer than 253 characters: {value!r}")
    return hostname


def normalize_ip(value: str) -> str:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if "%" in text:
        raise NormalizationError(f"scoped IPv6 addresses are not inventory assets: {value!r}")
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        raise NormalizationError(f"invalid IP address: {value!r}") from None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return str(address)


def normalize_cidr(value: str) -> str:
    try:
        return str(ipaddress.ip_network(value.strip(), strict=False))
    except ValueError:
        raise NormalizationError(f"invalid network: {value!r}") from None


def ip_in_network(ip: str, cidr: str) -> bool:
    address = ipaddress.ip_address(normalize_ip(ip))
    network = ipaddress.ip_network(normalize_cidr(cidr))
    return address.version == network.version and address in network


def is_public_ip(ip: str) -> bool:
    address = ipaddress.ip_address(normalize_ip(ip))
    return not any(address.version == net.version and address in net for net in _NON_PUBLIC)
