"""Promote runtime-proven career sources after parent/feed deduplication."""
from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).parent
DEFAULT_INPUT = ROOT / "career_source_promotable.yaml"
DEFAULT_OUTPUT = ROOT / "source_overrides_v19.yaml"

# Several submitted brands intentionally resolve to one parent hiring portal.
# One canonical scanner prevents duplicate requests and avoids presenting every
# parent-company vacancy as if it belonged to each subsidiary.
CANONICAL_NAME = {
    "Cisco Meraki": "Cisco",
    "Duo Security": "Cisco",
    "Splunk": "Cisco",
    "Collins Aerospace": "Raytheon Technologies",
    "Pratt & Whitney": "Raytheon Technologies",
    "CyberArk": "Palo Alto Networks",
    "National Instruments": "Emerson",
    "Juniper Networks": "Hewlett Packard Enterprise",
    "Optum": "UnitedHealth Group",
    "Heap": "Contentsquare",
    "Refinitiv": "LSEG",
    "VMware by Broadcom": "Broadcom",
    "Shell Technology Centre Bangalore": "Shell",
}

ALIASES = {
    "Cisco": ["Cisco Meraki", "Duo Security", "Splunk"],
    "Raytheon Technologies": ["Collins Aerospace", "Pratt & Whitney"],
    "Palo Alto Networks": ["CyberArk"],
    "Emerson": ["National Instruments"],
    "Hewlett Packard Enterprise": ["Juniper Networks"],
    "UnitedHealth Group": ["Optum"],
    "Contentsquare": ["Heap"],
    "LSEG": ["Refinitiv"],
    "Broadcom": ["VMware by Broadcom"],
    "Shell": ["Shell Technology Centre Bangalore"],
    "Cigna": ["Evernorth Health Services"],
    "Synopsys": ["Ansys"],
}


def source_identity(company: dict[str, Any]) -> tuple[str, str]:
    """Return the provider identity used to detect duplicate scanners."""
    endpoint = str(company.get("url") or company.get("slug") or "").rstrip("/")
    return str(company.get("ats") or ""), endpoint.casefold()


def build_reviewed(raw_companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reviewed: OrderedDict[str, dict[str, Any]] = OrderedDict()
    identities: dict[tuple[str, str], str] = {}

    for raw in raw_companies:
        submitted_name = str(raw["name"])
        canonical = CANONICAL_NAME.get(submitted_name, submitted_name)
        record = dict(raw)
        record["name"] = canonical
        if canonical in ALIASES:
            record["aliases"] = ALIASES[canonical]

        if canonical in reviewed:
            if source_identity(reviewed[canonical]) != source_identity(record):
                raise ValueError(f"conflicting sources for canonical company {canonical}")
            continue

        identity = source_identity(record)
        if identity in identities:
            raise ValueError(
                f"duplicate source identity for {canonical} and {identities[identity]}"
            )
        identities[identity] = canonical
        reviewed[canonical] = record

    return list(reviewed.values())


def promote(input_path: Path, output_path: Path) -> dict[str, Any]:
    document = yaml.safe_load(input_path.read_text(encoding="utf-8")) or {}
    raw_companies = document.get("companies") or []
    reviewed = build_reviewed(raw_companies)
    output = {
        "metadata": {
            "verified_at": "2026-08-10",
            "raw_parser_supported_sources": len(raw_companies),
            "reviewed_unique_sources": len(reviewed),
            "note": (
                "Runtime-proven sources promoted after parent-portal identity "
                "consolidation. Aliases are labels, not separate scanners."
            ),
        },
        "companies": reviewed,
    }
    output_path.write_text(
        yaml.safe_dump(output, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = promote(args.input, args.output)
    print(
        "Promoted "
        f"{output['metadata']['reviewed_unique_sources']} unique sources from "
        f"{output['metadata']['raw_parser_supported_sources']} runtime candidates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
