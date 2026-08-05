"""Production entry point: verified feeds, adjacent roles, strict experience guardrails."""
from __future__ import annotations

from pathlib import Path

import yaml

import custom_source_parsers
import job_match_expanded as expanded
import job_match_production as production
import job_monitor as bot
import job_monitor_entry
import job_monitor_entry_v2
import job_monitor_entry_v3
import job_monitor_parallel


ROOT = Path(__file__).parent
OVERRIDES_FILE = ROOT / "source_overrides_v4.yaml"


def load_production_config() -> dict:
    config = job_monitor_entry_v3.load_config_with_all_overrides()
    document = yaml.safe_load(OVERRIDES_FILE.read_text(encoding="utf-8")) or {}
    return job_monitor_entry_v2.apply_overrides(config, document.get("companies", []))


if __name__ == "__main__":
    bot.is_target_title = expanded.expanded_is_target_title
    bot.score_job = production.production_score_job
    bot.parse_workday_search = expanded.parse_workday_with_generic_details
    bot.parse_smartrecruiters = expanded.parse_smartrecruiters_with_generic_details
    bot.parse_lever = job_monitor_entry.parse_lever_with_region
    bot.fetch_company_jobs = custom_source_parsers.fetch_company_jobs_with_custom
    job_monitor_parallel.load_merged_config = load_production_config
    raise SystemExit(job_monitor_parallel.run())
