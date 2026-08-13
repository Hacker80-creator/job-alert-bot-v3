"""Adapters for the public Keka career widget API."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v20 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v20
HEADERS = {**bot.HEADERS, "Accept": "application/json,text/plain,*/*"}


def parse_keka_embed(company: dict[str, Any]) -> list[bot.Job]:
    """Read the anonymous active-jobs endpoint used by Keka career pages."""
    base = company["career_site_url"].rstrip("/") + "/"
    portal = str(company.get("portal_name") or "default")
    identifier = str(company.get("identifier") or "").strip()
    if not identifier:
        listing = requests.get(base, headers={**HEADERS, "Accept": "text/html,*/*"}, timeout=30)
        listing.raise_for_status()
        identifiers = re.findall(
            r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?![0-9a-f])",
            listing.text,
        )
        if not identifiers:
            raise ValueError("Keka careers page did not expose its public board identifier")
        identifier = identifiers[0]
    endpoint = urljoin(
        base,
        f"api/embedjobs/{portal}/active/{identifier}",
    )
    response = requests.get(endpoint, headers=HEADERS, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Keka active-jobs endpoint returned a non-list payload")

    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        job_id = bot.clean_text(item.get("id"))
        title = bot.clean_text(item.get("title"))
        if not job_id or not title or job_id in seen:
            continue
        seen.add(job_id)
        locations = []
        for place in item.get("jobLocations") or []:
            if not isinstance(place, dict):
                continue
            locations.append(bot.flatten_location([
                place.get("name") or place.get("city"),
                place.get("state"),
                place.get("countryName"),
            ]))
        skills = ", ".join(
            str(skill) for skill in item.get("skillNames") or [] if skill
        )
        description = BeautifulSoup(
            str(item.get("description") or item.get("excerpt") or ""),
            "html.parser",
        ).get_text(" ")
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.flatten_location(locations),
            url=urljoin(base, f"jobdetails/{job_id}"),
            source="Official careers: Keka",
            description=bot.clean_text(" ".join(filter(None, [
                description,
                f"Skills: {skills}" if skills else "",
                f"Experience: {item.get('experience')}" if item.get("experience") else "",
            ]))),
            department=bot.clean_text(item.get("departmentName")),
            requisition_id=bot.clean_text(item.get("jobNumber")) or job_id,
            salary_text=bot.clean_text(item.get("salaryRangeFormat")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def fetch_company_jobs_with_custom_v21(
    company: dict[str, Any],
) -> list[bot.Job]:
    parser = {"keka_embed": parse_keka_embed}.get(company.get("ats"))
    if parser is None:
        return BASE_CUSTOM_FETCH(company)
    try:
        jobs = parser(company)
        print(f"{company['name']}: {len(jobs)} raw jobs from {company['ats']}")
        return jobs
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        bot.SCAN_ERRORS.append(company["name"])
        return []
