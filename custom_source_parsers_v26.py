"""Adapters for MyNextHire, Zoho Recruit, and Kissflow public careers pages."""
from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v25 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v25
HEADERS = {**bot.HEADERS, "Accept": "text/html,application/json,*/*"}


def _mynexthire_detail_url(company: dict[str, Any], job_id: str) -> str:
    value = {
        "pageType": "jd",
        "cvSource": "careers",
        "reqId": int(job_id) if job_id.isdigit() else job_id,
        "requester": {"id": "", "code": "", "name": ""},
        "page": "careers",
        "bufilter": -1,
        "customFields": {},
    }
    encoded = base64.b64encode(
        json.dumps(value, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return f"{company['career_site_url']}?src=careers&p={encoded}"


def parse_mynexthire(company: dict[str, Any]) -> list[bot.Job]:
    response = requests.post(
        company["url"],
        json={"source": "careers", "code": "", "filterByBuId": -1},
        headers={**HEADERS, "Content-Type": "application/json"},
        timeout=40,
    )
    response.raise_for_status()
    jobs: list[bot.Job] = []
    for item in response.json().get("reqDetailsBOList") or []:
        job_id = bot.clean_text(item.get("reqId"))
        title = bot.clean_text(item.get("reqTitle") or item.get("designation"))
        if not job_id or not title:
            continue
        locations = [
            place.get("office") or place.get("address")
            for place in item.get("locationList") or []
            if isinstance(place, dict)
        ]
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.flatten_location(locations or item.get("location")),
            url=_mynexthire_detail_url(company, job_id),
            source="Official careers: MyNextHire",
            description=bot.clean_text(item.get("jdDisplay")),
            department=bot.clean_text(item.get("buName") or item.get("careerStream")),
            requisition_id=job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_zoho_recruit_public(company: dict[str, Any]) -> list[bot.Job]:
    """Decode the public job-list JSON embedded by Zoho Recruit."""
    response = requests.get(company["url"], headers=HEADERS, timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    raw_jobs: list[dict[str, Any]] = []
    for node in soup.select("input[value]"):
        value = node.get("value", "")
        if "Job_Opening_Name" not in value or not value.lstrip().startswith("["):
            continue
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, list) and decoded and isinstance(decoded[0], dict):
            if "id" in decoded[0] and "Job_Opening_Name" in decoded[0]:
                raw_jobs = decoded
                break
    if not raw_jobs:
        raise ValueError("Zoho Recruit page did not expose its public job list")

    jobs: list[bot.Job] = []
    for item in raw_jobs:
        job_id = bot.clean_text(item.get("id"))
        title = bot.clean_text(item.get("Posting_Title") or item.get("Job_Opening_Name"))
        if not job_id or not title or not item.get("Publish", True):
            continue
        slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.flatten_location([item.get("City"), item.get("Country")]),
            url=f"{company['career_site_url'].rstrip('/')}/{job_id}/{slug}?source=CareerSite",
            source="Official careers: Zoho Recruit",
            description="",
            requisition_id=job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_kissflow_jobs(company: dict[str, Any]) -> list[bot.Job]:
    response = requests.get(company["url"], headers=HEADERS, timeout=40)
    response.raise_for_status()
    listing = BeautifulSoup(response.text, "html.parser")
    links: dict[str, str] = {}
    listing_host = urlparse(company["url"]).netloc
    for anchor in listing.select("a.career-in-row[href]"):
        url = urljoin(company["url"], anchor.get("href"))
        heading = anchor.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        label = bot.clean_text(
            heading.get_text(" ") if heading else anchor.get_text(" ")
        )
        if urlparse(url).netloc != listing_host or not label:
            continue
        if label.casefold() in {"explore more", "apply", "apply now", "get jobs"}:
            continue
        path = urlparse(url).path.strip("/")
        if path and path not in {"careers"}:
            links.setdefault(url, label.split("Experience:", 1)[0].strip())

    jobs: list[bot.Job] = []
    for url, listing_title in links.items():
        detail = requests.get(url, headers=HEADERS, timeout=40)
        detail.raise_for_status()
        soup = BeautifulSoup(detail.text, "html.parser")
        text = bot.clean_text((soup.select_one("main") or soup.body).get_text(" "))
        title_node = soup.find(["h1", "h2"])
        title = bot.clean_text(title_node.get_text(" ") if title_node else listing_title)
        location_match = re.search(
            r"Work Location\s*:\s*(.+?)(?=\s+(?:Apply now|Job Description|Experience)\b)",
            text,
            re.I,
        )
        jobs.append(bot.Job(
            company=company["name"],
            title=title or listing_title,
            location=bot.clean_text(location_match.group(1)) if location_match else "",
            url=url,
            source="Official careers: Kissflow",
            description=text,
            requisition_id=urlparse(url).path.rstrip("/").rsplit("/", 1)[-1],
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def fetch_company_jobs_with_custom_v26(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "mynexthire": parse_mynexthire,
        "zoho_recruit_public": parse_zoho_recruit_public,
        "kissflow_jobs": parse_kissflow_jobs,
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
