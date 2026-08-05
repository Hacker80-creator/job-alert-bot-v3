"""Promote a discovery artifact only after stricter company-identity checks."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

import source_discovery as discovery


GENERIC_BOARD_WORDS = {
    "external", "website", "product", "products", "recruiting", "recruitment",
    "team", "north", "america", "external", "opportunities",
}
KNOWN_INVALID = {
    # This Lever namespace currently contains obvious demonstration reqs such
    # as "Anirban jobReq 3 - public", not LinkedIn production vacancies.
    ("linkedin", "lever"),
}


def greenhouse_identity_matches(company: str, board_name: str) -> bool:
    expected = discovery.brand_words(company)
    actual = discovery.brand_words(board_name)
    if not expected or not actual:
        return False
    return expected == actual or (expected < actual and actual - expected <= GENERIC_BOARD_WORDS)


def rejection_reason(source: dict[str, Any]) -> str | None:
    name = str(source.get("name") or "")
    ats = str(source.get("ats") or "")
    if not source.get("enabled", True):
        return "disabled"
    if int(source.get("verified_job_count") or 0) <= 0 and ats != "greenhouse":
        return "no observed postings"
    if (name.casefold(), ats.casefold()) in KNOWN_INVALID:
        return "known test or unrelated board"
    if ats == "recruitee":
        # Recruitee's response does not include trustworthy organization
        # identity metadata; short subdomains produced unrelated companies.
        return "provider response does not prove company identity"
    if ats == "greenhouse" and not greenhouse_identity_matches(name, str(source.get("verified_name") or "")):
        return "Greenhouse board name does not match company identity"
    return None


def promote(input_path: Path, output_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    candidate = yaml.safe_load(input_path.read_text(encoding="utf-8")) or {}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for source in candidate.get("companies", []):
        reason = rejection_reason(source)
        if reason:
            rejected.append({"name": str(source.get("name") or ""), "reason": reason})
        else:
            accepted.append(source)
    accepted.sort(key=lambda item: str(item["name"]).casefold())
    output = {
        "metadata": {
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "verified_sources": len(accepted),
            "rejected_after_identity_review": len(rejected),
            "note": "Live-tested sources promoted after strict identity validation.",
        },
        "companies": accepted,
    }
    output_path.write_text(yaml.safe_dump(output, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Promoted {len(accepted)} sources; rejected {len(rejected)}")
    for item in rejected:
        print(f"REJECT {item['name']}: {item['reason']}")
    return accepted, rejected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    promote(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
