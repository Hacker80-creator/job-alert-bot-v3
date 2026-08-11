"""Adapters for Param.ai, Dayforce Geo, and TurboHire public boards."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v16 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v16
HTML_HEADERS = {
    **bot.HEADERS,
    "Accept": "text/html,application/xhtml+xml",
}
API_HEADERS = {
    **bot.HEADERS,
    "Accept": "application/json,text/plain,*/*",
}


def _description_text(value: Any) -> str:
    return bot.clean_text(BeautifulSoup(str(value or ""), "html.parser").get_text(" "))


def parse_param_ai(company: dict[str, Any]) -> list[bot.Job]:
    """Read the public Param.ai career API used by its rendered job cards."""
    response = requests.get(company["url"], headers=API_HEADERS, timeout=30)
    response.raise_for_status()
    payload = response.json().get("data") or {}
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for department, group in payload.items():
        if not isinstance(group, dict):
            continue
        for item in group.get("jobs") or []:
            if item.get("published_on_career_page") is False:
                continue
            slug = bot.clean_text(item.get("slug"))
            title = bot.clean_text(item.get("title"))
            job_id = bot.clean_text(item.get("id"))
            if not title or not (slug or job_id):
                continue
            apply_url = bot.clean_text(item.get("apply_url"))
            url = apply_url if apply_url.startswith("http") else urljoin(
                company["career_site_url"].rstrip("/") + "/",
                f"{slug or job_id}",
            )
            if url in seen:
                continue
            seen.add(url)
            locations = item.get("locations") or []
            if isinstance(locations, str):
                locations = [locations]
            location = bot.flatten_location(locations)
            if item.get("is_remote"):
                location = f"Remote • {location}" if location else "Remote"
            minimum = item.get("min_exp")
            maximum = item.get("max_exp")
            experience = ""
            if minimum is not None or maximum is not None:
                experience = f"Experience required: {minimum or 0} - {maximum or minimum or 0} years."
            jobs.append(bot.Job(
                company=company["name"],
                title=title,
                location=location,
                url=url,
                source="Official careers: Param.ai",
                description=bot.clean_text(" ".join(filter(None, [
                    experience, _description_text(item.get("description")),
                ]))),
                department=bot.clean_text(
                    item.get("business_unit_name") or department
                ),
                requisition_id=bot.clean_text(item.get("req_id")) or job_id,
                wlb_score=company.get("wlb_score", 3),
            ))
    return jobs


def parse_dayforce_geo(company: dict[str, Any]) -> list[bot.Job]:
    """Use Dayforce's public Geo API with its standard CSRF handshake."""
    session = requests.Session()
    landing = session.get(
        company["career_site_url"], headers=HTML_HEADERS, timeout=30
    )
    landing.raise_for_status()
    origin = f"{urlparse(landing.url).scheme}://{urlparse(landing.url).netloc}"
    csrf = session.get(
        urljoin(origin, "/api/auth/csrf"),
        headers={**API_HEADERS, "Referer": landing.url},
        timeout=30,
    )
    csrf.raise_for_status()
    csrf_token = str(csrf.json().get("csrfToken") or "")
    if not csrf_token:
        raise ValueError("Dayforce did not issue a CSRF token")
    namespace = str(company["client_namespace"])
    job_board = str(company.get("job_board") or "candidateportal")
    culture = str(company.get("culture_code") or "en-US")
    page_size = max(25, min(100, int(company.get("page_size", 25))))
    max_results = max(page_size, int(company.get("max_results", 500)))
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    offset = 0
    total = max_results
    while offset < min(total, max_results):
        response = session.post(
            urljoin(origin, f"/api/geo/{namespace}/jobposting/search"),
            json={
                "clientNamespace": namespace,
                "jobBoardCode": job_board,
                "cultureCode": culture,
                "paginationStart": offset,
            },
            headers={
                **API_HEADERS,
                "Origin": origin,
                "Referer": landing.url,
                "X-CSRF-Token": csrf_token,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        raw_jobs = payload.get("jobPostings") or []
        total = int(payload.get("maxCount") or len(raw_jobs))
        for item in raw_jobs:
            job_id = bot.clean_text(item.get("jobPostingId"))
            title = bot.clean_text(item.get("jobTitle"))
            if not job_id or not title or job_id in seen:
                continue
            seen.add(job_id)
            locations = [
                place.get("formattedAddress")
                for place in item.get("postingLocations") or []
                if isinstance(place, dict) and place.get("formattedAddress")
            ]
            location = bot.flatten_location(locations)
            if item.get("hasVirtualLocation"):
                location = f"Virtual • {location}" if location else "Virtual"
            jobs.append(bot.Job(
                company=company["name"],
                title=title,
                location=location,
                url=urljoin(
                    origin,
                    f"/{culture}/{namespace}/{job_board}/jobs/{job_id}",
                ),
                source="Official careers: Dayforce",
                description=_description_text(item.get("jobDescription")),
                requisition_id=(
                    bot.clean_text(item.get("jobReqId")) or job_id
                ),
                wlb_score=company.get("wlb_score", 3),
            ))
        if not raw_jobs or len(raw_jobs) < page_size:
            break
        offset += len(raw_jobs)
    return jobs


def _turbohire_default_filter() -> dict[str, Any]:
    empty = {"Value": None, "FilterType": 0}
    return {
        "SortByV2": {"Key": "PostedDate", "Order": 2},
        "BunitIds": dict(empty),
        "Experience": dict(empty),
        "JobTypes": dict(empty),
        "JobTypeV2": dict(empty),
        "Locations": dict(empty),
        "CreatedDate": dict(empty),
        "Compensation": dict(empty),
        "Skills": dict(empty),
        "Keyword": "",
        "ClientIds": dict(empty),
        "Department": "",
        "CustomFields": {},
    }


def parse_turbohire_api(company: dict[str, Any]) -> list[bot.Job]:
    """Read TurboHire with its anonymous public token and career-page filter."""
    api_origin = str(company.get("api_origin") or "https://thapi.azurewebsites.net")
    portal_origin = company["career_site_url"].rstrip("/")
    origin = f"{urlparse(portal_origin).scheme}://{urlparse(portal_origin).netloc}"
    session = requests.Session()
    headers = {**API_HEADERS, "Origin": origin, "Referer": portal_origin + "/"}
    token_response = session.get(
        urljoin(api_origin, "/api/token/noauth"), headers=headers, timeout=30
    )
    token_response.raise_for_status()
    token = str(token_response.json().get("access_token") or "")
    if not token:
        raise ValueError("TurboHire did not issue an anonymous token")
    response = session.post(
        urljoin(api_origin, "/api/careerpagev2/filteredjobs"),
        params={
            "orgId": company["org_id"],
            "pageType": int(company.get("page_type", 0)),
        },
        json=_turbohire_default_filter(),
        headers={**headers, "Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    jobs: list[bot.Job] = []
    for item in response.json().get("Result") or []:
        job_id = bot.clean_text(item.get("JobId"))
        obfuscated = bot.clean_text(item.get("JobIdObfuscated"))
        title = bot.clean_text(item.get("JobTitle"))
        if not title or not (obfuscated or job_id):
            continue
        locations: list[str] = []
        raw_location = item.get("Location")
        try:
            decoded = json.loads(raw_location) if isinstance(raw_location, str) else raw_location
            locations = [
                str(place.get("Address"))
                for place in decoded or []
                if isinstance(place, dict) and place.get("Address")
            ]
        except (TypeError, ValueError):
            locations = [str(raw_location or "")]
        experience = item.get("Experience") or {}
        minimum = experience.get("MinExp") if isinstance(experience, dict) else None
        maximum = experience.get("MaxExp") if isinstance(experience, dict) else None
        experience_text = ""
        if minimum is not None or maximum is not None:
            experience_text = f"Experience required: {minimum or 0} - {maximum or minimum or 0} years."
        public_id = obfuscated or quote(job_id, safe="")
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.flatten_location(locations),
            url=f"{origin}/job/publicjobs/{public_id}",
            source="Official careers: TurboHire",
            description=bot.clean_text(" ".join(filter(None, [
                experience_text, _description_text(item.get("JobDescV2")),
                "Skills: " + ", ".join(item.get("Skills") or [])
                if item.get("Skills") else "",
            ]))),
            department=bot.clean_text(item.get("Department")),
            requisition_id=bot.clean_text(item.get("JobCode")) or job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def fetch_company_jobs_with_custom_v17(
    company: dict[str, Any],
) -> list[bot.Job]:
    parser = {
        "param_ai": parse_param_ai,
        "dayforce_geo": parse_dayforce_geo,
        "turbohire_api": parse_turbohire_api,
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
