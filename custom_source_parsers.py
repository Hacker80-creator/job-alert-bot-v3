"""Parsers for verified first-party career systems outside the common ATS set."""
from __future__ import annotations

import json
from typing import Any

import requests

import job_monitor as bot


BASE_FETCH_COMPANY = bot.fetch_company_jobs


def parse_accenture(company: dict[str, Any]) -> list[bot.Job]:
    """Read Accenture's public India careers search endpoint."""
    terms = company.get("search_terms") or [
        "data scientist", "machine learning", "data analyst", "AI engineer",
    ]
    filters = [
        {"fieldName": "location.keyword", "items": ["Bengaluru"], "multiSelect": False},
        {
            "fieldName": "yearsOfExperience.keyword",
            "items": ["Experience: 0-2 years", "Experience: 2-5 years"],
            "multiSelect": False,
        },
    ]
    headers = {
        **bot.HEADERS,
        "Origin": "https://www.accenture.com",
        "Referer": company.get("career_site_url", "https://www.accenture.com/in-en/careers/jobsearch"),
    }
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    # Relevance catches strong matches; newest ensures a fresh posting is not
    # hidden behind Accenture's very large result set.
    for term in terms:
        for sort_mode in (0, 2):
            response = requests.post(
                company["url"],
                data={
                    "startIndex": "0",
                    "maxResultSize": "50",
                    "jobKeyword": term,
                    "jobCountry": "India",
                    "jobLanguage": "en",
                    "countrySite": "in-en",
                    "sortBy": str(sort_mode),
                    "searchType": "vectorSearch",
                    "enableQueryBoost": "true",
                    "minScore": "0.6",
                    "getFeedbackJudgmentEnabled": "true",
                    "useCleanEmbedding": "true",
                    "score": "true",
                    "totalHits": "true",
                    "debugQuery": "false",
                    "jobFilters": json.dumps(filters),
                },
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            for item in response.json().get("data", []):
                job_id = str(item.get("guid") or item.get("requisitionId") or "")
                if not job_id or job_id in seen:
                    continue
                seen.add(job_id)
                url = str(item.get("jobDetailUrl") or "").replace("{0}", "in-en")
                description = bot.clean_text(
                    item.get("jobDescriptionClean")
                    or item.get("jobDescription")
                    or item.get("staticExtractiveSummary")
                )
                jobs.append(bot.Job(
                    company=company["name"],
                    title=bot.clean_text(item.get("title") or item.get("jobProfile")),
                    location=bot.flatten_location(item.get("location") or item.get("feedCity")),
                    url=url,
                    source="Official careers: Accenture",
                    description=description,
                    department=bot.flatten_location(
                        item.get("jobFamilyGroup") or item.get("areaOfInterest") or item.get("function")
                    ),
                    wlb_score=company.get("wlb_score", 4),
                ))
    return jobs


def parse_rippling_algolia(company: dict[str, Any]) -> list[bot.Job]:
    """Read every record in Rippling's public, search-only careers index."""
    app_id = company["algolia_app_id"]
    index = company["algolia_index"]
    url = f"https://{app_id}-dsn.algolia.net/1/indexes/{index}/query"
    headers = {
        **bot.HEADERS,
        "X-Algolia-Application-Id": app_id,
        "X-Algolia-API-Key": company["algolia_search_key"],
        "Content-Type": "application/json",
    }
    by_job_id: dict[str, bot.Job] = {}
    page = 0
    while page < max(1, int(company.get("max_pages", 12))):
        response = requests.post(
            url,
            json={"query": "", "hitsPerPage": 100, "page": page},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        for item in data.get("hits", []):
            job_id = str(item.get("jobId") or item.get("objectID") or "")
            if not job_id:
                continue
            locations = [bot.clean_text(value) for value in (item.get("locationNames") or []) if value]
            if item.get("isRemote") and not locations:
                locations = ["Remote"]
            if job_id in by_job_id:
                existing = by_job_id[job_id]
                merged = list(dict.fromkeys(filter(None, existing.location.split("; ") + locations)))
                existing.location = "; ".join(merged)
                continue
            by_job_id[job_id] = bot.Job(
                company=company["name"],
                title=bot.clean_text(item.get("name") or item.get("title")),
                location="; ".join(locations),
                url=str(item.get("url") or ""),
                source="Official careers: Rippling",
                description="",
                department=bot.clean_text(item.get("departmentName")),
                wlb_score=company.get("wlb_score", 3),
            )
        page += 1
        if page >= int(data.get("nbPages") or 0):
            break
    return list(by_job_id.values())


def fetch_company_jobs_with_custom(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "accenture": parse_accenture,
        "rippling_algolia": parse_rippling_algolia,
    }.get(company.get("ats"))
    if parser is None:
        return BASE_FETCH_COMPANY(company)
    try:
        jobs = parser(company)
        print(f"{company['name']}: {len(jobs)} raw jobs from {company['ats']}")
        return jobs
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        bot.SCAN_ERRORS.append(company["name"])
        return []
