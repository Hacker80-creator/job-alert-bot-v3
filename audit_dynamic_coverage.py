"""Report coverage of the dynamic company-source backlog."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

import job_monitor_entry_v32


ROOT = Path(__file__).parent


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def main() -> int:
    document = yaml.safe_load(
        (ROOT / "career_source_runtime_status.yaml").read_text(encoding="utf-8")
    )
    dynamic = [
        item
        for item in document["companies"]
        if item.get("status") == "DYNAMIC"
        or (
            item.get("status") == "REDIRECT"
            and item.get("resolved_status") == "DYNAMIC"
        )
    ]
    labels = {
        normalized(label)
        for company in job_monitor_entry_v32.load_final_config()["companies"]
        if company.get("enabled", True)
        for label in [company["name"], *company.get("aliases", [])]
    }
    covered = [item for item in dynamic if normalized(item["name"]) in labels]
    remaining = [item for item in dynamic if normalized(item["name"]) not in labels]
    print(f"dynamic={len(dynamic)} covered={len(covered)} remaining={len(remaining)}")
    for index, item in enumerate(remaining, 1):
        print(
            f"{index:03d}|{item['name']}|{item.get('source_url', '')}|"
            f"{item.get('final_url', '')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
