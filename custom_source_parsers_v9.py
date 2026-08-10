"""Verified first-party parsers for the final stale-source repair batch."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v8 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v8
HEADERS = {
    "User-Agent": "job-alert-bot/1.0 (+https://github.com/Hacker80-creator/job-alert-bot-v3)",
    "Accept": "text/html,application/json,application/xml,text/xml,*/*",
}
NUTANIX_TARGET_SLUG_TERMS = (
    "ai-", "analytics", "analyst", "business-intelligence", "data-", "decision-scientist",
    "machine-learning", "ml-", "scientist",
)


def _schema_location(posting: dict[str, Any]) -> str:
    values: list[str] = []
    locations = posting.get("jobLocation") or []
    locations = [locations] if isinstance(locations, dict) else locations
    for location in locations:
        address = location.get("address") if isinstance(location, dict) else {}
        if isinstance(address, dict):
            values.extend(str(address.get(key) or "") for key in (
                "addressLocality", "addressRegion", "addressCountry",
            ))
    if str(posting.get("jobLocationType") or "").casefold() == "telecommute":
        values.append("Remote")
        allowed = posting.get("applicantLocationRequirements") or []
        allowed = [allowed] if isinstance(allowed, dict) else allowed
        values.extend(str(item.get("name") or "") for item in allowed if isinstance(item, dict))
    return bot.flatten_location([value for value in values if value])


def parse_nutanix_sitemap(company: dict[str, Any]) -> list[bot.Job]:
    """Read likely target jobs from Nutanix's official sitemap and JobPosting data."""
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    urls = []
    for element in root.iter():
        if element.tag.endswith("loc") and element.text:
            url = element.text.strip()
            path = urlparse(url).path.casefold()
            if "/jobs/" in path and any(term in path for term in NUTANIX_TARGET_SLUG_TERMS):
                urls.append(url)

    jobs: list[bot.Job] = []
    for url in dict.fromkeys(urls):
        detail = requests.get(url, headers=HEADERS, timeout=30)
        detail.raise_for_status()
        soup = BeautifulSoup(detail.text, "html.parser")
        posting = None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                document = json.loads(script.string or "")
            except (TypeError, json.JSONDecodeError):
                continue
            documents = document if isinstance(document, list) else [document]
            posting = next((
                item for item in documents
                if isinstance(item, dict) and item.get("@type") == "JobPosting"
            ), None)
            if posting:
                break
        if posting:
            jobs.append(bot.Job(
                company=company["name"],
                title=bot.clean_text(posting.get("title")),
                location=_schema_location(posting),
                url=url,
                source="Official careers: Nutanix sitemap",
                description=bot.clean_text(posting.get("description")),
                department=bot.clean_text(posting.get("occupationalCategory")),
                wlb_score=company.get("wlb_score", 4),
            ))
    return jobs


def parse_coindcx_next_data(company: dict[str, Any]) -> list[bot.Job]:
    """Read CoinDCX's server-rendered official MyNextHire opening list."""
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    script = BeautifulSoup(response.text, "html.parser").find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        raise ValueError("CoinDCX __NEXT_DATA__ job payload is missing")
    document = json.loads(script.string)
    raw_jobs = (
        document.get("props", {}).get("pageProps", {})
        .get("initialNextHireState", {}).get("careersJobsList", [])
    )
    jobs: list[bot.Job] = []
    for item in raw_jobs:
        job_id = str(item.get("requisitionId") or "")
        if not job_id:
            continue
        minimum, maximum = item.get("yrsOfExpMin"), item.get("yrsOfExpMax")
        experience = (
            f"Experience required: {minimum or 0} to {maximum or minimum or 0} years."
            if minimum is not None or maximum is not None else ""
        )
        jobs.append(bot.Job(
            company=company["name"],
            title=bot.clean_text(item.get("requisitionTitle")),
            location=bot.flatten_location(item.get("officeLocationNames")),
            url=f"https://coindcx.mynexthire.com/employer/jobs/careers/{job_id}/-1",
            source="Official careers: CoinDCX MyNextHire",
            description=" ".join(filter(None, [
                experience, bot.clean_text(item.get("jobDescription")),
                bot.clean_text(item.get("designation")),
            ])),
            department=bot.clean_text(item.get("orgUnitName")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_siemens_avature(company: dict[str, Any]) -> list[bot.Job]:
    """Search Siemens Healthineers' public Avature portal and enrich local matches."""
    settings = bot.load_config()["settings"]
    jobs_by_url: dict[str, bot.Job] = {}
    for term in company.get("search_terms") or ["data", "machine learning", "analytics", "AI"]:
        response = requests.post(
            company["url"], data={"listFilterMode": "true", "search": term},
            headers=HEADERS, timeout=30,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for article in soup.select("article.article--result"):
            link = article.select_one("h3 a[href*='/JobDetail/']")
            if not link:
                continue
            url = str(link.get("href") or "")
            location = article.select_one(".list-item-location")
            family = article.select_one(".list-item-family")
            if url and url not in jobs_by_url:
                jobs_by_url[url] = bot.Job(
                    company=company["name"], title=bot.clean_text(link.get_text(" ")),
                    location=bot.clean_text(location.get_text(" ") if location else ""),
                    url=url, source="Official careers: Siemens Healthineers Avature",
                    description="",
                    department=bot.clean_text(family.get_text(" ") if family else ""),
                    wlb_score=company.get("wlb_score", 4),
                )

    for job in jobs_by_url.values():
        if bot.is_target_title(job.title) and bot.has_location_match(job.location, settings):
            detail = requests.get(job.url, headers=HEADERS, timeout=30)
            detail.raise_for_status()
            description = BeautifulSoup(detail.text, "html.parser").select_one(
                "article.article--details .article__content"
            )
            if description:
                job.description = bot.clean_text(description.get_text(" "))
    return list(jobs_by_url.values())


def parse_greenhouse_lightweight(company: dict[str, Any]) -> list[bot.Job]:
    """Use Greenhouse's metadata-only payload for unusually large boards."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{company['slug']}/jobs?content=false"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    jobs: list[bot.Job] = []
    for item in response.json().get("jobs", []):
        jobs.append(bot.Job(
            company=company["name"],
            title=bot.clean_text(item.get("title")),
            location=bot.flatten_location(item.get("location")),
            url=str(item.get("absolute_url") or ""),
            source="Official careers: Greenhouse",
            description="",
            department=bot.flatten_location(item.get("departments")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def fetch_company_jobs_with_custom_v9(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "nutanix_sitemap": parse_nutanix_sitemap,
        "coindcx_next_data": parse_coindcx_next_data,
        "siemens_avature": parse_siemens_avature,
        "greenhouse_lightweight": parse_greenhouse_lightweight,
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
