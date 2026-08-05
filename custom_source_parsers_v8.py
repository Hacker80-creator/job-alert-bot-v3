"""Official Expedia jobs-sitemap parser layered over production sources."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests

import custom_source_parsers_v3 as expedia_previous
import custom_source_parsers_v7 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v7
_UPPERCASE_SLUG_WORDS = {"ai", "bi", "ds", "epm", "ii", "iii", "iv", "ml", "nlp", "sql"}


def _title_from_expedia_slug(slug: str) -> str:
    words = slug.strip("-/").split("-")
    return " ".join(
        word.upper() if word.casefold() in _UPPERCASE_SLUG_WORDS else word.capitalize()
        for word in words
        if word
    )


def parse_expedia_sitemap(company: dict[str, Any]) -> list[bot.Job]:
    """Read Expedia's live official sitemap with a single firewall-safe request."""
    response = requests.get(
        company["url"],
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/xml,text/xml,*/*"},
        timeout=30,
    )
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for element in root.iter():
        if not element.tag.endswith("loc") or not element.text:
            continue
        raw_url = element.text.strip()
        parsed = urlparse(raw_url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4 or parts[0] != "job":
            continue
        url = parsed._replace(scheme="https").geturl()
        if url in seen:
            continue
        seen.add(url)
        jobs.append(bot.Job(
            company=company["name"],
            title=_title_from_expedia_slug(parts[1]),
            location=expedia_previous._expedia_location_from_path(url),
            url=url,
            source="Official careers: Expedia Group sitemap",
            description="",
            wlb_score=company.get("wlb_score", 4),
        ))
    return jobs


def fetch_company_jobs_with_custom_v8(company: dict[str, Any]) -> list[bot.Job]:
    if company.get("ats") != "expedia_sitemap":
        return BASE_CUSTOM_FETCH(company)
    try:
        jobs = parse_expedia_sitemap(company)
        print(f"{company['name']}: {len(jobs)} raw jobs from expedia_sitemap")
        return jobs
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        bot.SCAN_ERRORS.append(company["name"])
        return []
