"""Adapters for first-party WordPress, DataWeave, and Skima career pages."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v23 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v23
HEADERS = {**bot.HEADERS, "Accept": "text/html,application/xhtml+xml"}
UUID_PATH = re.compile(r"^/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/?$", re.I)


def _page(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=40)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _main_text(soup: BeautifulSoup) -> str:
    main = soup.select_one("main") or soup.select_one("article") or soup.body
    return bot.clean_text(main.get_text(" ") if main else "")


def parse_wordpress_job_links(company: dict[str, Any]) -> list[bot.Job]:
    """Follow stable first-party /jobs/ links from a WordPress careers page."""
    listing = _page(company["url"])
    links: dict[str, str] = {}
    for anchor in listing.select("a[href]"):
        href = urljoin(company["url"], anchor.get("href"))
        path = urlparse(href).path.casefold()
        label = bot.clean_text(anchor.get_text(" "))
        if "/jobs/" not in path or path.rstrip("/") == "/jobs":
            continue
        if not label or label.casefold() in {"more details", "apply", "apply now"}:
            continue
        links.setdefault(href, label)

    jobs: list[bot.Job] = []
    for url, listing_title in links.items():
        soup = _page(url)
        heading = soup.find(["h1", "h2"])
        title = bot.clean_text(heading.get_text(" ") if heading else listing_title)
        page_text = _main_text(soup)
        location_match = re.search(
            r"\bLocation\s*[:\-]?\s*([^|]{2,80}?)(?=\s+(?:Employment Type|Experience|Apply Now|$))",
            page_text,
            re.I,
        )
        location = bot.clean_text(location_match.group(1)) if location_match else ""
        jobs.append(bot.Job(
            company=company["name"],
            title=title or listing_title,
            location=location,
            url=url,
            source="Official careers: first-party job pages",
            description=page_text,
            requisition_id=urlparse(url).path.rstrip("/").rsplit("/", 1)[-1],
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_dataweave_jobs(company: dict[str, Any]) -> list[bot.Job]:
    listing = _page(company["url"])
    links: dict[str, tuple[str, str]] = {}
    for anchor in listing.select("a[href]"):
        url = urljoin(company["url"], anchor.get("href"))
        if "/jobs/" not in urlparse(url).path.casefold():
            continue
        label = bot.clean_text(anchor.get_text(" "))
        match = re.match(r"(.+?)\s+in\s+([^|]{2,60}?)(?:\s+We\s+are\b|$)", label, re.I)
        title = bot.clean_text(match.group(1)) if match else label
        location = bot.clean_text(match.group(2)) if match else ""
        if title:
            links[url] = (title, location)

    jobs: list[bot.Job] = []
    for url, (listing_title, location) in links.items():
        soup = _page(url)
        heading = soup.find(["h1", "h2"])
        title = bot.clean_text(heading.get_text(" ") if heading else listing_title)
        jobs.append(bot.Job(
            company=company["name"],
            title=title or listing_title,
            location=location,
            url=url,
            source="Official careers: DataWeave",
            description=_main_text(soup),
            requisition_id=urlparse(url).path.rstrip("/").rsplit("/", 1)[-1],
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_skima_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read all server-rendered pages from a Skima public careers site."""
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    page_number = 1
    max_pages = max(1, int(company.get("max_pages", 20)))
    while page_number <= max_pages:
        separator = "&" if "?" in company["url"] else "?"
        soup = _page(f"{company['url']}{separator}page={page_number}")
        pagination = soup.select_one("[data-pagination-container]")
        last_page = int(pagination.get("data-last-page", 1)) if pagination else 1
        found = 0
        for anchor in soup.select("a[href]"):
            path = urlparse(anchor.get("href")).path
            if not UUID_PATH.fullmatch(path):
                continue
            job_id = path.strip("/")
            if job_id in seen:
                continue
            seen.add(job_id)
            found += 1
            title = bot.clean_text(anchor.get_text(" "))
            card = anchor.parent
            spans = [bot.clean_text(node.get_text(" ")) for node in card.select("span")]
            location = spans[0] if spans else ""
            jobs.append(bot.Job(
                company=company["name"],
                title=title,
                location=location,
                url=urljoin(company["career_site_url"].rstrip("/") + "/", path.lstrip("/")),
                source="Official careers: Skima",
                description=bot.clean_text(card.get_text(" ")),
                requisition_id=job_id,
                wlb_score=company.get("wlb_score", 3),
            ))
        if page_number >= last_page or not found:
            break
        page_number += 1
    return jobs


def fetch_company_jobs_with_custom_v24(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "wordpress_job_links": parse_wordpress_job_links,
        "dataweave_jobs": parse_dataweave_jobs,
        "skima_html": parse_skima_html,
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
