"""Tavant browser-compatibility wrapper over all verified custom parsers."""
from __future__ import annotations

from typing import Any

import custom_source_parsers_v4 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v4


def parse_tavant_browser_compatible(company: dict[str, Any]) -> list[bot.Job]:
    """Use the plain browser user-agent expected by Tavant's Zwayam proxy."""
    original = bot.HEADERS["User-Agent"]
    bot.HEADERS["User-Agent"] = "Mozilla/5.0"
    try:
        return previous.parse_tavant_zwayam(company)
    finally:
        bot.HEADERS["User-Agent"] = original


def fetch_company_jobs_with_custom_v5(company: dict[str, Any]) -> list[bot.Job]:
    if company.get("ats") != "tavant_browser_transport":
        return BASE_CUSTOM_FETCH(company)
    try:
        jobs = parse_tavant_browser_compatible(company)
        print(f"{company['name']}: {len(jobs)} raw jobs from tavant_browser_transport")
        return jobs
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        bot.SCAN_ERRORS.append(company["name"])
        return []
