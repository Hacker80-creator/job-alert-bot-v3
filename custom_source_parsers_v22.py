"""Adapters for Deel and Gem public recruiting boards."""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v21 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v21
HEADERS = {**bot.HEADERS, "Accept": "text/html,application/json,*/*"}


def _html_text(value: Any) -> str:
    return bot.clean_text(BeautifulSoup(str(value or ""), "html.parser").get_text(" "))


def _deel_postings(page: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(page, "html.parser")
    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        if "jobPostings" not in text:
            continue
        match = re.search(r"self\.__next_f\.push\((\[.*\])\)", text, re.DOTALL)
        if not match:
            continue
        envelope = json.loads(match.group(1))
        payload = envelope[1] if isinstance(envelope, list) and len(envelope) > 1 else ""
        marker = '"jobPostings":'
        index = str(payload).find(marker)
        if index < 0:
            continue
        value, _ = json.JSONDecoder().raw_decode(str(payload)[index + len(marker):])
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    raise ValueError("Deel page did not expose its public jobPostings payload")


def parse_deel_next(company: dict[str, Any]) -> list[bot.Job]:
    response = requests.get(company["url"], headers=HEADERS, timeout=40)
    response.raise_for_status()
    base = company["career_site_url"].rstrip("/") + "/"
    jobs: list[bot.Job] = []
    by_url: dict[str, bot.Job] = {}
    for item in _deel_postings(response.text):
        posting_id = bot.clean_text(item.get("id"))
        title = bot.clean_text(item.get("title"))
        if not posting_id or not title:
            continue
        info = item.get("job") or {}
        locations = []
        for wrapper in info.get("jobLocations") or []:
            place = wrapper.get("location") if isinstance(wrapper, dict) else None
            if isinstance(place, dict):
                locations.append(place.get("name"))
        departments = [
            wrapper.get("department", {}).get("name")
            for wrapper in info.get("jobDepartments") or []
            if isinstance(wrapper, dict) and isinstance(wrapper.get("department"), dict)
        ]
        teams = [
            wrapper.get("team", {}).get("name")
            for wrapper in info.get("jobTeams") or []
            if isinstance(wrapper, dict) and isinstance(wrapper.get("team"), dict)
        ]
        url = urljoin(base, f"job-details/{posting_id}/overview")
        job = bot.Job(
            company=company["name"],
            title=title,
            location=bot.flatten_location(locations),
            url=url,
            source="Official careers: Deel",
            description=bot.clean_text(" ".join(filter(None, departments + teams))),
            department=bot.flatten_location(departments),
            requisition_id=bot.clean_text(item.get("jobId")) or posting_id,
            wlb_score=company.get("wlb_score", 3),
        )
        jobs.append(job)
        by_url[url] = job

    settings = bot.load_config()["settings"]
    candidates = [
        job for job in jobs
        if bot.is_target_title(job.title) and bot.has_location_match(job.location, settings)
    ][:max(0, int(company.get("max_candidate_details", 30)))]
    for job in candidates:
        try:
            detail = requests.get(job.url, headers=HEADERS, timeout=30)
            detail.raise_for_status()
            soup = BeautifulSoup(detail.text, "html.parser")
            for node in soup.find_all("script", type="application/ld+json"):
                value = json.loads(node.string or node.get_text(), strict=False)
                if isinstance(value, dict) and str(value.get("@type")).casefold() == "jobposting":
                    job.description = _html_text(value.get("description"))
                    break
        except Exception as exc:
            print(f"WARN {company['name']} detail {job.requisition_id} failed: {exc}")
    return jobs


GEM_QUERY = """
query JobBoardList($boardId: String!) {
  oatsExternalJobPostings(boardId: $boardId) {
    jobPostings {
      id extId title descriptionHtml
      locations { id name city isoCountry isRemote extId }
      job {
        id locationType employmentType requisitionId teamDisplayName
        department { id name extId }
      }
    }
  }
}
"""


def parse_gem_public(company: dict[str, Any]) -> list[bot.Job]:
    endpoint = str(company.get("graphql_url") or "https://jobs.gem.com/api/public/graphql")
    slug = str(company["slug"])
    response = requests.post(
        endpoint,
        json={
            "operationName": "JobBoardList",
            "variables": {"boardId": slug},
            "query": GEM_QUERY,
        },
        headers={**HEADERS, "Origin": "https://jobs.gem.com", "Referer": company["career_site_url"]},
        timeout=40,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise ValueError(f"Gem returned GraphQL errors: {payload['errors']}")
    raw_jobs = (((payload.get("data") or {}).get("oatsExternalJobPostings") or {}).get("jobPostings") or [])
    jobs: list[bot.Job] = []
    for item in raw_jobs:
        ext_id = bot.clean_text(item.get("extId"))
        title = bot.clean_text(item.get("title"))
        if not ext_id or not title:
            continue
        locations = []
        for place in item.get("locations") or []:
            if not isinstance(place, dict):
                continue
            label = bot.flatten_location([place.get("name") or place.get("city"), place.get("isoCountry")])
            if place.get("isRemote") and "remote" not in label.casefold():
                label = f"Remote • {label}" if label else "Remote"
            locations.append(label)
        info = item.get("job") or {}
        department = info.get("department") or {}
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.flatten_location(locations),
            url=f"https://jobs.gem.com/{slug}/{ext_id}",
            source="Official careers: Gem",
            description=_html_text(item.get("descriptionHtml")),
            department=bot.clean_text(department.get("name") or info.get("teamDisplayName")),
            requisition_id=bot.clean_text(info.get("requisitionId")) or ext_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def fetch_company_jobs_with_custom_v22(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "deel_next": parse_deel_next,
        "gem_public": parse_gem_public,
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
