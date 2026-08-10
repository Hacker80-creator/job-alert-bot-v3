"""Company-scope filtering for shared parent TalentBrew portals."""
from __future__ import annotations

from typing import Any

import custom_source_parsers_v11 as talentbrew
import custom_source_parsers_v12 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v12


def _scope_text(job: bot.Job) -> str:
    return bot.normalize_match_text(" ".join([
        job.title,
        job.location,
        job.department,
        job.description,
        job.url,
    ]))


def filter_company_scope(
    jobs: list[bot.Job], company: dict[str, Any]
) -> list[bot.Job]:
    required = bot.normalize_match_text(str(company.get("required_keyword") or ""))
    excluded = bot.normalize_match_text(str(company.get("excluded_keyword") or ""))
    if not required and not excluded:
        return jobs

    scoped: list[bot.Job] = []
    for job in jobs:
        text = _scope_text(job)
        if required and required not in text:
            continue
        if excluded and excluded in text:
            continue
        scoped.append(job)
    return scoped


def fetch_company_jobs_with_custom_v13(company: dict[str, Any]) -> list[bot.Job]:
    if company.get("ats") != "talentbrew_html" or not (
        company.get("required_keyword") or company.get("excluded_keyword")
    ):
        return BASE_CUSTOM_FETCH(company)
    try:
        jobs = talentbrew.parse_talentbrew_html(company)
        scoped = filter_company_scope(jobs, company)
        print(
            f"{company['name']}: {len(scoped)} scoped jobs from "
            f"{len(jobs)} TalentBrew records"
        )
        return scoped
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        bot.SCAN_ERRORS.append(company["name"])
        return []
