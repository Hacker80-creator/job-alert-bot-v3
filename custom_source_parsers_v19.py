"""Adapters for public job sitemaps discovered in the dynamic backlog."""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v18 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v18
HEADERS = {
    **bot.HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/xml",
}
DEFAULT_SLUG_TERMS = (
    "data",
    "analytics",
    "analyst",
    "machinelearning",
    "businessanalyst",
    "artificialintelligence",
    "agenticai",
)


def _embedded_value(page: str, key: str) -> str:
    match = re.search(
        rf'\\"{re.escape(key)}\\":\\"((?:\\\\.|[^"\\\\])*)\\"',
        page,
    )
    if not match:
        return ""
    try:
        return bot.clean_text(json.loads(f'"{match.group(1)}"'))
    except (TypeError, ValueError, json.JSONDecodeError):
        return bot.clean_text(match.group(1).replace(r'\"', '"'))


def parse_next_sitemap(company: dict[str, Any]) -> list[bot.Job]:
    """Read target job pages from a public sitemap and their Next.js payload."""
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    terms = tuple(
        re.sub(r"[^a-z0-9]+", "", str(term).casefold())
        for term in company.get("slug_terms") or DEFAULT_SLUG_TERMS
    )
    candidates: list[str] = []
    for element in root.iter():
        if not element.tag.endswith("loc") or not element.text:
            continue
        url = element.text.strip()
        path = urlparse(url).path
        if "/job/" not in path.casefold():
            continue
        slug = path.casefold().split("/job/", 1)[1].rsplit("/", 1)[0]
        normalized = re.sub(r"[^a-z0-9]+", "", slug)
        if any(term and term in normalized for term in terms):
            candidates.append(url)

    max_pages = max(1, int(company.get("max_job_pages", 40)))
    jobs: list[bot.Job] = []
    for url in list(dict.fromkeys(candidates))[:max_pages]:
        detail = requests.get(url, headers=HEADERS, timeout=30)
        detail.raise_for_status()
        title = _embedded_value(detail.text, "jobTitle")
        location = _embedded_value(detail.text, "location")
        requisition_id = _embedded_value(detail.text, "jobReqId")
        if not title:
            continue
        soup = BeautifulSoup(detail.text, "html.parser")
        main = soup.select_one("main")
        description = bot.clean_text(main.get_text(" ") if main else "")
        area_match = re.search(
            r'\\"area\\":\[\{.*?\\"label\\":\\"((?:\\\\.|[^"\\\\])*)\\"',
            detail.text,
        )
        department = ""
        if area_match:
            try:
                department = bot.clean_text(json.loads(f'"{area_match.group(1)}"'))
            except (TypeError, ValueError, json.JSONDecodeError):
                department = bot.clean_text(area_match.group(1))
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=url,
            source="Official careers: job sitemap",
            description=description,
            department=department,
            requisition_id=requisition_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def fetch_company_jobs_with_custom_v19(
    company: dict[str, Any],
) -> list[bot.Job]:
    parser = {"next_sitemap": parse_next_sitemap}.get(company.get("ats"))
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
