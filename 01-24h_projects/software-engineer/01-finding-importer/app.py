"""Exercise scaffold: CLI I/O works; the assessed feature is intentionally absent."""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import typing



def top_validation(payload: dict[str, typing.Any], arguments: argparse.Namespace) -> tuple[str, list[str], list[dict[str, typing.Any]]]:
    json_tenant = payload.get("tenant")
    if not isinstance(json_tenant, str):
        raise ValueError("Top-level 'tenant' must be a string.")

    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Top-level 'assets' must be an array.")

    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Top-level 'records' must be an array.")

    if json_tenant != arguments.tenant:
        raise ValueError("Tenant in JSON does not match the CLI argument.")

    return json_tenant, assets, records

def validate_row(row: dict[str, typing.Any], expected_tenant: str, allowed_assets: list[str]) -> tuple[bool, str]:
    required_fields = ["source_id", "tenant", "asset_id", "rule_id", "location", "severity", "evidence"]

    # 1. Validate types and empty strings
    for field in required_fields:
        val = row.get(field)
        if not isinstance(val, str):
            return False, f"Field '{field}' is missing or not a string."
        if not val.strip():
            return False, f"Field '{field}' is empty."

    # 2. Validate business logic
    if row["tenant"].strip() != expected_tenant:
        return False, "Tenant does not match the allowed tenant."

    if row["asset_id"].strip() not in allowed_assets:
        return False, "Asset ID is not in the allowed assets list."

    valid_severities = {"critical", "high", "medium", "low", "info"}
    if row["severity"].strip().lower() not in valid_severities:
        return False, "Invalid severity level."

    return True, ""

def duplicaion(row: dict[str, typing.Any],unique_findings: dict[tuple[str, str, str, str], dict[str, typing.Any]])-> bool:
    severity_rank = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    # 1. Clean the fields and create the tuple key
    tenant = row["tenant"].strip()
    asset_id = row["asset_id"].strip()
    rule_id = row["rule_id"].strip()
    location = row["location"].strip()

    dedup_key = (tenant, asset_id, rule_id, location)

    severity = row["severity"].strip().lower()
    evidence = row["evidence"].strip()
    source_id = row["source_id"].strip()

    if dedup_key not in unique_findings:
        # First time seeing this combination, create the new record
        unique_findings[dedup_key] = {
            "tenant": tenant,
            "asset_id": asset_id,
            "rule_id": rule_id,
            "location": location,
            "severity": severity,
            "evidence": [evidence],       # Stored as an array
            "source_ids": [source_id]     # Stored as an array
        }
        return False

    else:
        # We found a duplicate, merge it into the existing record
        existing = unique_findings[dedup_key]

        # Upgrade severity if the new one is higher
        if severity_rank[severity] > severity_rank[existing["severity"]]:
            existing["severity"] = severity

        # Add unique evidence and sort
        if evidence not in existing["evidence"]:
            existing["evidence"].append(evidence)
            existing["evidence"].sort()

        # Add unique source_id and sort
        if source_id not in existing["source_ids"]:
            existing["source_ids"].append(source_id)
            existing["source_ids"].sort()
        return True

def import_findings(payload: dict[str, typing.Any], arguments: argparse.Namespace) -> dict[str, typing.Any]:
    json_tenant, assets, records = top_validation(payload, arguments)

    rejected_rows: list[dict[str, typing.Any]] = []

    unique_findings: dict[tuple[str, str, str, str], dict[str, typing.Any]] = {}
    summary={
        "input_rows":len(records),
        "accepted_rows":0,
        "unique_findings":0,
        "duplicate_rows":0,
        "rejected_rows":0
    }

    # enumerate(records, start=1) gives us the 1-based row number requested by the README
    for row_index, row in enumerate(records, start=1):
        is_valid, error_reason = validate_row(row, json_tenant, assets)

        if not is_valid:
            # Safely get source_id if it's a string, otherwise None
            source_id = row.get("source_id")
            if not isinstance(source_id, str):
                source_id = None

            rejected_rows.append({
                "row": row_index,
                "source_id": source_id,
                "reason": error_reason
            })
            summary["rejected_rows"] += 1
            continue
        summary["accepted_rows"] += 1
        is_duplicated = duplicaion(row,unique_findings)
        if is_duplicated:
            summary["duplicate_rows"] += 1
        else:
            summary["unique_findings"] += 1

    sorted_findings = [unique_findings[key] for key in sorted(unique_findings.keys())]

    # Return the exact schema requested by the README
    return {
        "findings": sorted_findings,
        "rejected": rejected_rows,
        "summary": summary
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import and deduplicate a synthetic finding batch.")
    parser.add_argument("--input", default="inputs/primary.json", help="UTF-8 fixture JSON")
    parser.add_argument("--tenant", default="north")
    arguments = parser.parse_args()
    try:
        payload = json.loads(pathlib.Path(arguments.input).read_text(encoding="utf-8"))
        if isinstance(payload, dict) is False:
            raise ValueError("input must be a JSON object")
        result = import_findings(payload, arguments)
        print(json.dumps(result, indent=2, sort_keys=True))
    except NotImplementedError as error:
        print(str(error), file=sys.stderr)
        return 3
    except (OSError, UnicodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
