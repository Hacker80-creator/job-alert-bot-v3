"""Adapters for MediaTek and Nagarro first-party job feeds."""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v27 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v27
JSON_HEADERS = {**bot.HEADERS, "Accept": "application/json"}


def parse_mediatek(company: dict[str, Any]) -> list[bot.Job]:
    """Query the public tRPC endpoint used by MediaTek's official jobs page."""
    payload = {
        "0": {
            "json": {
                "locales": "en_US",
                "page": 1,
                "jobQueryInfo": {},
                "filters": {
                    "categorys": [],
                    "workExperiences": [],
                    "locations": ["0000168800"],
                    "programs": [],
                },
                "sortBy": "publishedDate",
                "order": "DESC",
                "limit": 100,
            }
        }
    }
    response = requests.get(
        "https://careers.mediatek.com/api/trpc/job.getJobs",
        params={"batch": "1", "input": json.dumps(payload, separators=(",", ":"))},
        headers=JSON_HEADERS,
        timeout=40,
    )
    response.raise_for_status()
    document = response.json()[0]["result"]["data"]["json"]
    jobs: list[bot.Job] = []
    for item in document.get("jobs", []):
        job_id = str(item.get("id") or "").strip()
        title = bot.clean_text(str(item.get("title") or ""))
        if not job_id or not title:
            continue
        properties = item.get("properties") or {}
        location_data = properties.get("location") or {}
        category_data = properties.get("category") or {}
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.clean_text(str(location_data.get("code") or "Bangalore")),
            url=f"https://careers.mediatek.com/en/jobs/{quote(job_id)}",
            source="Official careers: MediaTek",
            description=bot.clean_text(str(item.get("description") or "")),
            department=bot.clean_text(str(category_data.get("label") or "")),
            requisition_id=job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def _nagarro_feed_url(careers_url: str) -> str:
    page = requests.get(careers_url, headers=bot.HEADERS, timeout=40)
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")
    script_url = ""
    for script in soup.select("script[src]"):
        src = str(script.get("src") or "")
        if "Careers_JobListing" in src:
            script_url = urljoin(careers_url, src)
            break
    if not script_url:
        raise ValueError("Nagarro job-list script was not found")
    script = requests.get(script_url, headers=bot.HEADERS, timeout=40)
    script.raise_for_status()
    match = re.search(r'ALL_JOBS_API="([^"]+)"', script.text)
    if not match:
        raise ValueError("Nagarro public job feed was not found")
    return match.group(1)


def parse_nagarro(company: dict[str, Any]) -> list[bot.Job]:
    """Read Nagarro's first-party Azure table, filtering at source to India."""
    feed_url = _nagarro_feed_url(company["url"])
    params = {
        "$filter": "Job_Country eq 'India'",
        "$select": (
            "Expertise,Job_Title,Job_City,Job_Country,Level_name,Job_Url,"
            "index,Is_job_remote_friendly"
        ),
    }
    rows: list[dict[str, Any]] = []
    while True:
        response = requests.get(feed_url, params=params, headers=JSON_HEADERS, timeout=40)
        response.raise_for_status()
        rows.extend(response.json().get("value", []))
        partition_key = response.headers.get("x-ms-continuation-NextPartitionKey")
        row_key = response.headers.get("x-ms-continuation-NextRowKey")
        if not partition_key or not row_key:
            break
        params["NextPartitionKey"] = partition_key
        params["NextRowKey"] = row_key

    jobs: list[bot.Job] = []
    for item in rows:
        title = bot.clean_text(str(item.get("Job_Title") or ""))
        url = str(item.get("Job_Url") or "").strip()
        if not title or not url:
            continue
        city = bot.clean_text(str(item.get("Job_City") or ""))
        location = "Remote India" if city.lower() in {"wfa/remote", "remote"} else f"{city}, India"
        job_id_match = re.search(r"/(\d+)(?:[/?#]|$)", urlparse(url).path)
        requisition_id = job_id_match.group(1) if job_id_match else str(item.get("index") or "")
        description = " | ".join(filter(None, [
            bot.clean_text(str(item.get("Expertise") or "")),
            bot.clean_text(str(item.get("Level_name") or "")),
        ]))
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=url,
            source="Official careers: Nagarro",
            description=description,
            department=bot.clean_text(str(item.get("Expertise") or "")),
            requisition_id=requisition_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def fetch_company_jobs_with_custom_v28(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "mediatek": parse_mediatek,
        "nagarro_azure": parse_nagarro,
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
