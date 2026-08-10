"""Verified parsers for Atlassian and SAP SuccessFactors career sites."""
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v9 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v9
HEADERS = previous.HEADERS


def parse_atlassian_listings(company: dict[str, Any]) -> list[bot.Job]:
    """Read Atlassian's first-party careers listing endpoint."""
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Atlassian careers payload is not a list")

    jobs: list[bot.Job] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        portal = item.get("portalJobPost") or {}
        portal = portal if isinstance(portal, dict) else {}
        title = bot.clean_text(item.get("title"))
        url = str(portal.get("portalUrl") or item.get("applyUrl") or "")
        if not title or not url:
            continue
        description = bot.clean_text(" ".join(
            str(item.get(field) or "")
            for field in ("overview", "responsibilities", "qualifications")
        ))
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.flatten_location(item.get("locations")),
            url=url,
            source="Official careers: Atlassian",
            description=description,
            department=bot.clean_text(item.get("category")),
            salary_text=bot.clean_text(item.get("compensation")),
            wlb_score=company.get("wlb_score", 5),
        ))
    return jobs


def parse_successfactors_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read a public SAP SuccessFactors job table and enrich relevant local jobs."""
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    settings = bot.load_config()["settings"]
    jobs: list[bot.Job] = []
    for row in soup.select("tr.data-row"):
        link = row.select_one("span.jobTitle.hidden-phone a.jobTitle-link")
        if link is None:
            link = row.select_one("a.jobTitle-link")
        if link is None:
            continue
        title = bot.clean_text(link.get_text(" "))
        url = urljoin(company["url"], str(link.get("href") or ""))
        location_node = row.select_one("td.colLocation span.jobLocation")
        department_node = row.select_one("td.colFacility span.jobFacility")
        location = bot.clean_text(location_node.get_text(" ") if location_node else "")
        department = bot.clean_text(
            department_node.get_text(" ") if department_node else ""
        )
        if not title or not url:
            continue
        job = bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=url,
            source="Official careers: SAP SuccessFactors",
            department=department,
            wlb_score=company.get("wlb_score", 3),
        )
        if bot.is_target_title(title) and bot.has_location_match(location, settings):
            detail = requests.get(url, headers=HEADERS, timeout=30)
            detail.raise_for_status()
            description = BeautifulSoup(detail.text, "html.parser").select_one(
                ".jobdescription"
            )
            if description:
                job.description = bot.clean_text(description.get_text(" "))
        jobs.append(job)
    return jobs


def fetch_company_jobs_with_custom_v10(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "atlassian_listings": parse_atlassian_listings,
        "successfactors_html": parse_successfactors_html,
    }.get(company.get("ats"))
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
