"""Additional first-party parsers for production source repairs."""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v2 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v2


def decode_json_envelope(response: requests.Response) -> dict[str, Any]:
    """Decode APIs which wrap their JSON response in a JSON string."""
    value: Any = response.json()
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("job source returned a non-object JSON response")
    return value


def parse_zwayam_hardened(company: dict[str, Any]) -> list[bot.Job]:
    """Read Zwayam with retry, longer read timeout and double-JSON support."""
    jobs: list[bot.Job] = []
    page_size = 10
    max_results = max(page_size, int(company.get("max_results", 100)))
    portal_url = company["career_site_url"].rstrip("/")
    headers = {
        **bot.HEADERS,
        "Origin": f"https://{company['domain']}",
        "Referer": f"{portal_url}/",
    }

    for offset in range(0, max_results, page_size):
        criteria = {
            "paginationStartNo": offset,
            "selectedCall": "sort",
            "sortCriteria": {"name": "modifiedDate", "isAscending": False},
            "anyOfTheseWords": "",
        }
        response: requests.Response | None = None
        for attempt in range(3):
            try:
                response = requests.post(
                    company["url"],
                    data={
                        "filterCri": json.dumps(criteria),
                        "domain": company["domain"],
                        "companyId": company["company_id"],
                    },
                    headers=headers,
                    timeout=(10, int(company.get("read_timeout_seconds", 45))),
                )
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        if response is None:
            raise RuntimeError("Zwayam request did not return a response")

        data = decode_json_envelope(response).get("data") or {}
        raw_jobs = data.get("data") or []
        for item in raw_jobs:
            source = item.get("_source") or item
            slug = bot.clean_text(source.get("jobUrl"))
            salary_parts = [source.get("minJobSalary"), source.get("maxJobSalary")]
            salary_text = ""
            if all(str(value or "").strip() for value in salary_parts):
                salary_text = f"INR {salary_parts[0]}-{salary_parts[1]} per annum"
            description = " ".join(filter(None, [
                bot.clean_text(source.get("mediumDescription")),
                bot.clean_text(source.get("role")),
                bot.clean_text(source.get("jdSkillsKnown")),
                bot.clean_text(source.get("experienceUIField") or source.get("yrsOfExperience")),
            ]))
            jobs.append(bot.Job(
                company=company["name"],
                title=bot.clean_text(source.get("jobTitle")),
                location=bot.flatten_location(
                    source.get("locationSeparatedbySlash")
                    or source.get("jobLocationRecord")
                    or source.get("location")
                ),
                url=f"{portal_url}/job/{slug}" if slug else portal_url,
                source="Official careers: Zwayam",
                description=description,
                department=bot.clean_text(source.get("text1") or source.get("departmentName")),
                salary_text=salary_text,
                wlb_score=company.get("wlb_score", 3),
            ))
        if not raw_jobs or not data.get("hasMoreData"):
            break
        time.sleep(0.15)
    return jobs


def parse_phenom(company: dict[str, Any]) -> list[bot.Job]:
    """Read a first-party Phenom careers widget with India city facets."""
    terms = company.get("search_terms") or ["data", "machine learning", "AI", "analytics"]
    cities = company.get("search_cities") or ["Bengaluru", "Bangalore", "Remote"]
    size = max(10, min(100, int(company.get("page_size", 50))))
    max_pages = max(1, int(company.get("max_pages_per_query", 3)))
    headers = {
        **bot.HEADERS,
        "Referer": company["career_site_url"].rstrip("/") + "/search-results",
    }
    by_id: dict[str, bot.Job] = {}

    for term in terms:
        for city in cities:
            for page in range(max_pages):
                payload = {
                    "lang": company.get("locale", "en_global"),
                    "deviceType": "desktop",
                    "country": "global",
                    "pageName": "search-results",
                    "ddoKey": "refineSearch",
                    "sortBy": "",
                    "subsearch": "",
                    "from": page * size,
                    "jobs": True,
                    "counts": True,
                    "all_fields": ["category", "country", "state", "city"],
                    "size": size,
                    "clearAll": False,
                    "jdsource": "facets",
                    "isSliderEnable": True,
                    "keywords": term,
                    "selected_fields": {"country": ["India"], "city": [city]},
                }
                response = requests.post(
                    company["url"], json=payload, headers=headers, timeout=30
                )
                response.raise_for_status()
                container = response.json().get("refineSearch") or {}
                raw_jobs = (container.get("data") or {}).get("jobs") or []
                for item in raw_jobs:
                    job_id = str(
                        item.get("jobId") or item.get("reqId") or item.get("jobSeqNo") or ""
                    )
                    if not job_id or job_id in by_id:
                        continue
                    apply_url = str(item.get("applyUrl") or "")
                    if apply_url.endswith("/apply"):
                        apply_url = apply_url[:-6]
                    if not apply_url:
                        slug = bot.normalize_match_text(str(item.get("title") or "")).replace(" ", "-")
                        seq = item.get("jobSeqNo") or job_id
                        apply_url = (
                            company["career_site_url"].rstrip("/")
                            + f"/job/{seq}/{slug}"
                        )
                    description = " ".join(filter(None, [
                        bot.clean_text(item.get("descriptionTeaser")),
                        bot.clean_text(item.get("ml_skills")),
                        bot.clean_text(item.get("experienceLevel") or item.get("type")),
                    ]))
                    by_id[job_id] = bot.Job(
                        company=company["name"],
                        title=bot.clean_text(item.get("title")),
                        location=bot.flatten_location(
                            item.get("location") or item.get("cityStateCountry")
                            or [item.get("city"), item.get("state"), item.get("country")]
                        ),
                        url=apply_url,
                        source="Official careers: Phenom",
                        description=description,
                        department=bot.clean_text(item.get("category") or item.get("businessSegment")),
                        wlb_score=company.get("wlb_score", 4),
                    )
                try:
                    total = int(container.get("totalHits") or 0)
                except (TypeError, ValueError):
                    total = 0
                if not raw_jobs or len(raw_jobs) < size or (total and (page + 1) * size >= total):
                    break
                time.sleep(0.1)
    return list(by_id.values())


def _expedia_location_from_path(href: str) -> str:
    parts = urlparse(href).path.strip("/").split("/")
    if len(parts) < 4 or parts[0] != "job":
        return ""
    location = parts[-2].replace("-", " ")
    if any(value in location.casefold() for value in ("bangalore", "bengaluru", "india")):
        location += ", India"
    return location


def parse_expedia_html(company: dict[str, Any]) -> list[bot.Job]:
    """Search Expedia's current server-rendered Appcast careers pages."""
    terms = company.get("search_terms") or [
        "data scientist", "machine learning", "data analyst", "analytics", "AI engineer"
    ]
    max_pages = max(1, int(company.get("max_pages_per_term", 3)))
    settings = bot.load_config()["settings"]
    session = requests.Session()
    by_url: dict[str, bot.Job] = {}

    for term in terms:
        previous_count = -1
        for page in range(1, max_pages + 1):
            response = session.get(
                company["url"],
                params={"keyword": term, "mypage": page},
                headers=bot.HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for link in soup.select('a[href*="/job/"]'):
                href = urljoin(company["url"], str(link.get("href") or ""))
                if href in by_url:
                    continue
                title = bot.clean_text(link.get_text(" "))
                if not title or len(title) > 180:
                    continue
                location = _expedia_location_from_path(href)
                by_url[href] = bot.Job(
                    company=company["name"],
                    title=title,
                    location=location,
                    url=href,
                    source="Official careers: Expedia Group",
                    description="",
                    wlb_score=company.get("wlb_score", 4),
                )
            if len(by_url) == previous_count:
                break
            previous_count = len(by_url)

    detail_budget = max(0, int(company.get("max_details", 15)))
    for job in by_url.values():
        if detail_budget <= 0:
            break
        if not bot.has_location_match(job.location, settings):
            continue
        response = session.get(job.url, headers=bot.HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        job.description = bot.clean_text(
            soup.select_one("main") or soup.select_one("article") or soup.body
        )
        detail_budget -= 1
    return list(by_url.values())


def fetch_company_jobs_with_custom_v3(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "zwayam_hardened": parse_zwayam_hardened,
        "phenom": parse_phenom,
        "expedia_html": parse_expedia_html,
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
