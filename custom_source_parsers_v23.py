"""Adapters for Goldman Sachs Higher and the v22 public recruiting boards."""
from __future__ import annotations

import json
from typing import Any

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v22 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v22
HEADERS = {**bot.HEADERS, "Accept": "text/html,application/json,*/*"}

GOLDMAN_QUERY = """
query GetRoles($searchQueryInput: RoleSearchQueryInput!) {
  roleSearch(searchQueryInput: $searchQueryInput) {
    totalCount
    items {
      roleId corporateTitle jobTitle jobFunction
      locations { primary state country city }
      status division skills
      jobType { code description }
      externalSource { sourceId }
    }
  }
}
"""


def _goldman_location(locations: Any) -> str:
    labels: list[str] = []
    for place in locations or []:
        if not isinstance(place, dict):
            continue
        label = bot.flatten_location(
            [place.get("city"), place.get("state"), place.get("country")]
        )
        if label:
            labels.append(label)
    return bot.flatten_location(labels)


def _goldman_department(item: dict[str, Any]) -> str:
    return bot.flatten_location([item.get("division"), item.get("jobFunction")])


def parse_goldman_higher(company: dict[str, Any]) -> list[bot.Job]:
    """Read the public Goldman Sachs Higher GraphQL feed for Bengaluru."""
    endpoint = company["url"]
    page_size = max(1, min(20, int(company.get("page_size", 20))))
    max_results = max(page_size, int(company.get("max_results", 300)))
    page_number = 1
    jobs: list[bot.Job] = []
    by_id: dict[str, bot.Job] = {}

    while len(jobs) < max_results:
        variables = {
            "searchQueryInput": {
                "page": {"pageSize": page_size, "pageNumber": page_number},
                "sort": {"sortStrategy": "POSTED_DATE", "sortOrder": "DESC"},
                "filters": [{
                    "filterCategoryType": "LOCATION",
                    "filters": [{
                        "filter": "India",
                        "subFilters": [{
                            "filter": "Karnataka",
                            "subFilters": [{
                                "filter": "Bengaluru",
                                "subFilters": [],
                            }],
                        }],
                    }],
                }],
                "experiences": ["EARLY_CAREER", "PROFESSIONAL"],
                "searchTerm": "",
            }
        }
        response = requests.post(
            endpoint,
            json={"query": GOLDMAN_QUERY, "variables": variables},
            headers={
                **HEADERS,
                "Content-Type": "application/json",
                "Origin": "https://higher.gs.com",
                "Referer": company["career_site_url"],
            },
            timeout=40,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise ValueError(f"Goldman Higher returned GraphQL errors: {payload['errors']}")
        search = ((payload.get("data") or {}).get("roleSearch") or {})
        raw_jobs = search.get("items") or []
        if not raw_jobs:
            break
        for item in raw_jobs:
            source = item.get("externalSource") or {}
            job_id = bot.clean_text(source.get("sourceId") or item.get("roleId"))
            title = bot.clean_text(item.get("jobTitle") or item.get("corporateTitle"))
            if not job_id or not title or job_id in by_id:
                continue
            url = f"https://higher.gs.com/roles/{job_id}"
            job = bot.Job(
                company=company["name"],
                title=title,
                location=_goldman_location(item.get("locations")),
                url=url,
                source="Official careers: Goldman Sachs Higher",
                description=bot.flatten_location(item.get("skills") or []),
                department=_goldman_department(item),
                requisition_id=job_id,
                wlb_score=company.get("wlb_score", 3),
            )
            jobs.append(job)
            by_id[job_id] = job
        total = int(search.get("totalCount") or 0)
        if len(raw_jobs) < page_size or (total and page_number * page_size >= total):
            break
        page_number += 1

    settings = bot.load_config()["settings"]
    candidates = [
        job for job in jobs
        if bot.is_target_title(job.title) and bot.has_location_match(job.location, settings)
    ][:max(0, int(company.get("max_candidate_details", 50)))]
    for job in candidates:
        try:
            detail = requests.get(job.url, headers=HEADERS, timeout=30)
            detail.raise_for_status()
            soup = BeautifulSoup(detail.text, "html.parser")
            node = soup.find("script", id="__NEXT_DATA__")
            if node is None:
                raise ValueError("detail page did not expose __NEXT_DATA__")
            role = json.loads(node.string or node.get_text())["props"]["pageProps"]["role"]
            job.description = bot.clean_text(
                BeautifulSoup(str(role.get("descriptionHtml") or ""), "html.parser").get_text(" ")
            ) or job.description
            job.department = _goldman_department(role) or job.department
            source_id = bot.clean_text((role.get("externalSource") or {}).get("sourceId"))
            if source_id:
                job.requisition_id = source_id
        except Exception as exc:
            print(f"WARN {company['name']} detail {job.requisition_id} failed: {exc}")
    return jobs


def fetch_company_jobs_with_custom_v23(company: dict[str, Any]) -> list[bot.Job]:
    parser = {"goldman_higher": parse_goldman_higher}.get(company.get("ats"))
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
