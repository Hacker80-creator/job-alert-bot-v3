"""Production entry point for the verified v44 careers-source expansion."""
from __future__ import annotations

import custom_source_parsers_v30
import job_match_expanded as expanded
import job_match_resume as resume
import job_monitor as bot
import job_monitor_entry
import job_monitor_entry_v2
import job_monitor_entry_v43
import job_monitor_parallel
import source_registry_v44


def load_final_config() -> dict:
    config = job_monitor_entry_v43.load_final_config()
    existing = {
        str(company["name"]).casefold(): company
        for company in config.get("companies", [])
    }
    overrides = source_registry_v44.build_source_overrides()
    for override in overrides:
        prior = existing.get(str(override["name"]).casefold())
        if not prior:
            continue
        aliases = list(dict.fromkeys([
            *prior.get("aliases", []),
            *override.get("aliases", []),
        ]))
        if aliases:
            override["aliases"] = aliases
    return job_monitor_entry_v2.apply_overrides(config, overrides)


if __name__ == "__main__":
    bot.is_target_title = resume.resume_is_target_title
    bot.score_job = resume.resume_score_job
    bot.parse_workday_search = expanded.parse_workday_with_generic_details
    bot.parse_smartrecruiters = expanded.parse_smartrecruiters_with_generic_details
    bot.parse_lever = job_monitor_entry.parse_lever_with_region
    bot.fetch_company_jobs = custom_source_parsers_v30.fetch_company_jobs_with_custom_v30
    job_monitor_parallel.load_merged_config = load_final_config
    raise SystemExit(job_monitor_parallel.run())
