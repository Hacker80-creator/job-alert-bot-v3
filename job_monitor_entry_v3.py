"""Production entry point with the second verified source-repair batch."""
from __future__ import annotations

from pathlib import Path

import yaml

import job_monitor as bot
import job_monitor_entry
import job_monitor_entry_v2
import job_monitor_parallel


ROOT = Path(__file__).parent
OVERRIDES_FILE = ROOT / "source_overrides_v2.yaml"
BASE_LOAD_CONFIG = job_monitor_entry_v2.load_config_with_overrides


def load_config_with_all_overrides() -> dict:
    config = BASE_LOAD_CONFIG()
    if not OVERRIDES_FILE.exists():
        return config
    document = yaml.safe_load(OVERRIDES_FILE.read_text(encoding="utf-8")) or {}
    return job_monitor_entry_v2.apply_overrides(config, document.get("companies", []))


if __name__ == "__main__":
    bot.parse_lever = job_monitor_entry.parse_lever_with_region
    job_monitor_parallel.load_merged_config = load_config_with_all_overrides
    raise SystemExit(job_monitor_parallel.run())
