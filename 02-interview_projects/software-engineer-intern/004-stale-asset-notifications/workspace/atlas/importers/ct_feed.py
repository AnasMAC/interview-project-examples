# ruff: noqa: E501
# (Zoe) some feed lines/messages are long, didn't want to wrap them all. TODO: clean up and drop this.
"""Certificate transparency feed importer.

Input is JSON lines as written by the CT monitor, one log entry per line:

  {"log": "argon2026h2", "index": 1834455, "type": "x509" | "precert", "seen": "2026-10-28T11:02:17Z",
   "cert": {"fingerprint_sha256": "...", "der": "<base64, optional>", "serial": "...",
            "subject": {"cn": "...", "o": "..."}, "issuer": {"cn": "...", "o": "..."},
            "not_before": "...", "not_after": "...", "san": ["DNS:www.example.test", "IP:203.0.113.5"]}}

Notes:
- the same cert shows up once per log -> dedupe on fingerprint
- precert + final cert have the same issuer/serial but different fingerprints -> keep the final one, keep a precert only if the final cert is not in the feed
- fingerprint is sometimes upper case with colons (AB:CD:..), sometimes missing (then sha256 of der)
- dates are ISO or unix seconds depending on the monitor version
- wildcard SANs (*.example.test) are kept as is; non-wildcard SANs also give a "covers" link so the host gets created; wildcards are matched by the merge step
  (the apex SAN is emitted as a host too, merge folds it into the zone's domain asset)
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re

from atlas.core import clock
from atlas.core.normalize import normalize_hostname
from atlas.importers.base import ImportBatch, ImportFormatError, Observation, ObservedLink, parse_timestamp


def parse(text: str, *, source_name: str = "") -> ImportBatch:
    warnings = []
    certs = {}  # fingerprint -> info dict
    finals = set()  # (issuer, serial) of x509 entries
    latest_seen = None
    good = bad = 0
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            bad += 1
            warnings.append(f"line {n}: not valid JSON, skipped")
            continue
        if not isinstance(e, dict) or not isinstance(e.get("cert"), dict):
            bad += 1
            warnings.append(f"line {n}: no cert object, skipped")
            continue
        good += 1
        c = e["cert"]
        fp = str(c.get("fingerprint_sha256") or "").replace(":", "").strip().lower()
        if not fp and c.get("der"):
            try:
                fp = hashlib.sha256(base64.b64decode(c["der"], validate=True)).hexdigest()
            except (binascii.Error, ValueError, TypeError):
                warnings.append(f"line {n}: der is not valid base64, skipped")
                continue
        if not re.fullmatch(r"[0-9a-f]{64}", fp):
            warnings.append(f"line {n}: missing or bad sha256 fingerprint {fp[:20]!r}, skipped")
            continue
        try:
            seen = parse_timestamp(e["seen"]) if e.get("seen") is not None else None
        except ValueError:
            seen = None
        if seen and (latest_seen is None or seen > latest_seen):
            latest_seen = seen
        subj = c.get("subject") if isinstance(c.get("subject"), dict) else {}
        iss = c.get("issuer") if isinstance(c.get("issuer"), dict) else {}
        issuer = str(iss.get("cn") or iss.get("o") or "").strip()
        serial = str(c.get("serial") or "").replace(":", "").strip().lower().lstrip("0") or "0"
        is_pre = str(e.get("type", "x509")).lower() == "precert"
        if not is_pre:
            finals.add((issuer, serial))
        if fp in certs:
            continue  # same cert from another log
        try:
            nb = parse_timestamp(c.get("not_before"))
            na = parse_timestamp(c.get("not_after"))
        except ValueError as err:
            warnings.append(f"line {n}: bad validity dates ({err}), skipped")
            continue
        sans = []
        for s in c.get("san") or []:
            if not isinstance(s, str):
                continue
            t, _, v = s.partition(":") if ":" in s else ("DNS", ":", s)
            if t.strip().upper() != "DNS":
                continue  # IP / email / URI SANs are not hostnames
            try:
                h = normalize_hostname(v, allow_wildcard=True)
            except ValueError as err:
                warnings.append(f"line {n}: SAN {v!r} dropped: {err}")
                continue
            if h not in sans:
                sans.append(h)
        cn = str(subj.get("cn") or "").strip()
        certs[fp] = {"pre": is_pre, "key": (issuer, serial), "attrs": {
            "subject_cn": cn,
            "sans": sans,
            "issuer": issuer,
            "serial": serial,
            "not_before": clock.isoformat(nb),
            "not_after": clock.isoformat(na),
        }, "ext": f"{e.get('log', '')}#{e.get('index', '')}", "label": cn or (sans[0] if sans else fp[:16])}

    if bad and not good:
        raise ImportFormatError("no readable CT entries in the file (is this JSON lines?)")
    observations = []
    for fp, info in certs.items():
        if info["pre"] and info["key"] in finals:
            continue  # final cert is in the feed, the precert would be a duplicate asset
        observations.append(Observation(
            kind="certificate",
            value=fp,
            label=info["label"],
            attributes=info["attrs"],
            external_id=info["ext"],
            links=tuple(ObservedLink("covers", "host", h) for h in info["attrs"]["sans"] if not h.startswith("*.")),
        ))
    return ImportBatch(
        importer="ct_feed",
        source_kind="ct_feed",
        source_name=source_name or "ct feed",
        observed_at=latest_seen or clock.now(),
        observations=observations,
        warnings=warnings,
    )
