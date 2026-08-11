"""Adapters for Rupeek, Sahaj, and Times Internet first-party listings."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v26 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v26
HEADERS = {**bot.HEADERS, "Accept": "text/html,application/xhtml+xml"}


def _soup(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=40)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def parse_rupeek_official(company: dict[str, Any]) -> list[bot.Job]:
    """Read the LinkedIn job links curated on Rupeek's first-party careers page."""
    soup = _soup(company["url"])
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for anchor in soup.select('a[href*="linkedin.com/jobs/view/"]'):
        url = str(anchor.get("href"))
        id_match = re.search(r"-(\d+)(?:[/?#]|$)", url)
        job_id = id_match.group(1) if id_match else ""
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        text = bot.clean_text(anchor.get_text(" "))
        match = re.match(r"(.+?)\s+Location:\s*(.+)", text, re.I)
        title = bot.clean_text(match.group(1)) if match else text
        location = bot.clean_text(match.group(2)) if match else ""
        location = re.sub(
            r"\s+(?:(?:\d+|an?)\s+)?(?:minute|hour|day|week|month)s?\s+ago$",
            "",
            location,
            flags=re.I,
        )
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=url,
            source="Official Rupeek careers page: LinkedIn job",
            requisition_id=job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_sahaj_roles(company: dict[str, Any]) -> list[bot.Job]:
    listing = _soup(company["url"])
    jobs: list[bot.Job] = []
    for card in listing.select(".explore-role-grid"):
        heading = card.select_one(".role-title") or card.find(["h2", "h3", "h4"])
        anchor = card.select_one("a[href]")
        if heading is None or anchor is None:
            continue
        title = bot.clean_text(heading.get_text(" "))
        url = urljoin(company["url"], anchor.get("href"))
        detail = _soup(url)
        text = bot.clean_text((detail.select_one("main") or detail.body).get_text(" "))
        location_match = re.search(
            r"\bLocation:\s*(.+?)(?=\s+(?:About the role|About the Role|Qualification|Give yourself)\b)",
            text,
            re.I,
        )
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.clean_text(location_match.group(1)) if location_match else "",
            url=url,
            source="Official careers: Sahaj",
            description=text,
            requisition_id=urlparse(url).path.rstrip("/").rsplit("/", 1)[-1],
            wlb_score=company.get("wlb_score", 4),
        ))
    return jobs


def parse_times_internet(company: dict[str, Any]) -> list[bot.Job]:
    listing = _soup(company["url"])
    links: dict[str, str] = {}
    for anchor in listing.select('a[href*="/careers/job-detail/"]'):
        url = urljoin(company["url"], anchor.get("href"))
        links.setdefault(url, bot.clean_text(anchor.get_text(" ")))
    jobs: list[bot.Job] = []
    for url, text in links.items():
        match = re.match(
            r"(.+?)\s+LOCATION:\s*(.+?)\s+BUSINESS:\s*(.+?)\s+EXPERIENCE:",
            text,
            re.I,
        )
        title = bot.clean_text(match.group(1)) if match else text
        location = bot.clean_text(match.group(2)) if match else ""
        department = bot.clean_text(match.group(3)) if match else ""
        detail = _soup(url)
        description = bot.clean_text((detail.select_one("main") or detail.body).get_text(" "))
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=url,
            source="Official careers: Times Internet",
            description=description,
            department=department,
            requisition_id=urlparse(url).path.rstrip("/").rsplit("/", 1)[-1],
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def fetch_company_jobs_with_custom_v27(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "rupeek_official": parse_rupeek_official,
        "sahaj_roles": parse_sahaj_roles,
        "times_internet": parse_times_internet,
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
