"""Adapter for Robosoft's first-party, server-rendered careers board."""
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v28 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v28


def parse_robosoft(company: dict[str, Any]) -> list[bot.Job]:
    response = requests.get(company["url"], headers=bot.HEADERS, timeout=40)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for anchor in soup.select('a[href^="/careers/"]'):
        url = urljoin(company["url"], str(anchor.get("href") or ""))
        if url in seen:
            continue
        card = anchor.parent
        if card is None:
            continue
        heading = card.select_one("h3")
        tags = [bot.clean_text(tag.get_text(" ")) for tag in card.select("span")]
        title = bot.clean_text(heading.get_text(" ") if heading else "")
        location = ", ".join(tag for tag in tags if tag)
        if not title or not location:
            continue
        seen.add(url)
        detail = requests.get(url, headers=bot.HEADERS, timeout=40)
        detail.raise_for_status()
        detail_soup = BeautifulSoup(detail.text, "html.parser")
        description_node = detail_soup.select_one("main") or detail_soup.body
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=url,
            source="Official careers: Robosoft",
            description=bot.clean_text(
                description_node.get_text(" ") if description_node else ""
            ),
            requisition_id=urlparse(url).path.rstrip("/").rsplit("/", 1)[-1],
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def fetch_company_jobs_with_custom_v29(company: dict[str, Any]) -> list[bot.Job]:
    if company.get("ats") != "robosoft_html":
        return BASE_CUSTOM_FETCH(company)
    try:
        jobs = parse_robosoft(company)
        print(f"{company['name']}: {len(jobs)} raw jobs from robosoft_html")
        return jobs
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        bot.SCAN_ERRORS.append(company["name"])
        return []
