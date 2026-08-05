"""Hardened custom source parsers, including Microsoft's current careers API."""
from __future__ import annotations

import time
from typing import Any

import requests

import custom_source_parsers as previous
import job_match_expanded as expanded
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom


def _get_with_throttle_retry(
    session: requests.Session, url: str, params: dict[str, Any]
) -> requests.Response:
    response = session.get(url, params=params, headers=bot.HEADERS, timeout=25)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "2")
        try:
            delay = min(8.0, max(1.0, float(retry_after)))
        except ValueError:
            delay = 2.0
        time.sleep(delay)
        response = session.get(url, params=params, headers=bot.HEADERS, timeout=25)
    return response


def parse_microsoft_eightfold(company: dict[str, Any]) -> list[bot.Job]:
    """Query Microsoft's official feed gently and retain partial successes."""
    terms = company.get("search_terms") or [
        "data scientist",
        "machine learning engineer",
        "data analyst",
        "applied scientist",
        "AI engineer",
    ]
    locations = company.get("search_locations") or [
        "Bengaluru, Karnataka, India",
        "Remote, India",
    ]
    session = requests.Session()
    jobs_by_id: dict[str, bot.Job] = {}
    successful_queries = 0
    failed_queries = 0
    domain = company["domain"]
    career_url = company["career_site_url"].rstrip("/")
    detail_url = company["url"].rsplit("/", 1)[0] + "/position_details"
    settings = bot.load_config()["settings"]

    for term in terms:
        for location_query in locations:
            response = _get_with_throttle_retry(
                session,
                company["url"],
                {
                    "domain": domain,
                    "query": term,
                    "location": location_query,
                    "start": 0,
                },
            )
            if response.status_code == 429:
                failed_queries += 1
                print(f"WARN Microsoft throttled query: {term} / {location_query}")
                continue
            response.raise_for_status()
            successful_queries += 1
            positions = (response.json().get("data") or {}).get("positions") or []
            for item in positions:
                job_id = str(item.get("id") or "")
                if not job_id or job_id in jobs_by_id:
                    continue
                jobs_by_id[job_id] = bot.Job(
                    company=company["name"],
                    title=bot.clean_text(item.get("name") or item.get("title")),
                    location=bot.flatten_location(item.get("locations") or item.get("location")),
                    url=f"{career_url}/job/{job_id}?domain={domain}",
                    source="Official careers: Microsoft",
                    description=bot.clean_text(item.get("jobDescription") or item.get("description")),
                    department=bot.clean_text(item.get("department") or item.get("jobFunction")),
                    wlb_score=company.get("wlb_score", 4),
                )
            time.sleep(float(company.get("request_delay_seconds", 0.6)))

    if successful_queries == 0:
        raise RuntimeError("all Microsoft careers queries were throttled or failed")

    # Fetch details only for a few broad titles. Explicit data/AI titles do not
    # need descriptions to pass, and avoiding needless detail calls reduces
    # the chance of API throttling.
    detail_budget = max(0, int(company.get("max_generic_details", 3)))
    for job in jobs_by_id.values():
        if detail_budget <= 0:
            break
        if not expanded.is_generic_technical_title(job.title):
            continue
        if expanded.bot_original_is_target_title(job.title):
            continue
        if not bot.has_location_match(job.location, settings):
            continue
        job_id = job.url.split("/job/", 1)[1].split("?", 1)[0]
        response = _get_with_throttle_retry(
            session,
            detail_url,
            {"position_id": job_id, "domain": domain, "hl": "en"},
        )
        if response.status_code == 429:
            print(f"WARN Microsoft throttled detail: {job.title}")
            continue
        response.raise_for_status()
        info = response.json().get("data") or {}
        if isinstance(info.get("data"), dict):
            info = info["data"]
        job.description = bot.clean_text(
            info.get("jobDescription") or info.get("description")
        ) or job.description
        job.department = bot.clean_text(info.get("department")) or job.department
        detail_budget -= 1
        time.sleep(float(company.get("request_delay_seconds", 0.6)))

    if failed_queries:
        print(
            f"WARN Microsoft retained partial results after {failed_queries} throttled queries"
        )
    return list(jobs_by_id.values())


def fetch_company_jobs_with_custom_v2(company: dict[str, Any]) -> list[bot.Job]:
    if company.get("ats") != "microsoft_eightfold":
        return BASE_CUSTOM_FETCH(company)
    try:
        jobs = parse_microsoft_eightfold(company)
        print(f"{company['name']}: {len(jobs)} raw jobs from microsoft_eightfold")
        return jobs
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        bot.SCAN_ERRORS.append(company["name"])
        return []
