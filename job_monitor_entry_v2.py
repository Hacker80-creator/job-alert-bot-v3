"""Production entry point with verified repairs for stale configured sources."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

import job_monitor as bot
import job_monitor_entry
import job_monitor_parallel


ROOT = Path(__file__).parent
OVERRIDES_FILE = ROOT / "source_overrides.yaml"
BASE_LOAD_CONFIG = job_monitor_parallel.load_merged_config


def apply_overrides(config: dict[str, Any], overrides: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {str(item["name"]).casefold(): item for item in overrides}
    companies: list[dict[str, Any]] = []
    applied: set[str] = set()
    for company in config.get("companies", []):
        key = str(company["name"]).casefold()
        if key in by_name:
            # Preserve ranking metadata such as kind and WLB, replacing only
            # source-specific fields with the live-verified override.
            companies.append({**company, **by_name[key]})
            applied.add(key)
        else:
            companies.append(company)
    for key, override in by_name.items():
        if key not in applied:
            companies.append(override)
    config["companies"] = companies
    return config


def load_config_with_overrides() -> dict[str, Any]:
    config = BASE_LOAD_CONFIG()
    if not OVERRIDES_FILE.exists():
        return config
    document = yaml.safe_load(OVERRIDES_FILE.read_text(encoding="utf-8")) or {}
    return apply_overrides(config, document.get("companies", []))


if __name__ == "__main__":
    bot.parse_lever = job_monitor_entry.parse_lever_with_region
    job_monitor_parallel.load_merged_config = load_config_with_overrides
    raise SystemExit(job_monitor_parallel.run())
