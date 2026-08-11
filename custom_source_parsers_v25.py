"""Adapters for Urban Company, ShareChat, and River public careers APIs."""
from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v24 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v24
HEADERS = {**bot.HEADERS, "Accept": "application/json,text/plain,*/*"}


def _html_text(value: Any) -> str:
    return bot.clean_text(BeautifulSoup(str(value or ""), "html.parser").get_text(" "))


def parse_urban_company(company: dict[str, Any]) -> list[bot.Job]:
    response = requests.post(company["url"], json={}, headers=HEADERS, timeout=40)
    response.raise_for_status()
    payload = response.json()
    raw_jobs = payload.get("jobs") or []
    jobs: list[bot.Job] = []
    for item in raw_jobs:
        job_id = bot.clean_text(item.get("job_id"))
        title = bot.clean_text(item.get("job_title"))
        if not job_id or not title:
            continue
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.flatten_location(item.get("location") or item.get("location_city")),
            url=bot.clean_text(item.get("apply_url")) or f"https://careers.urbancompany.com/jobDetail?id={job_id}",
            source="Official careers: Urban Company",
            description=_html_text(item.get("job_description")),
            department=bot.clean_text(item.get("parent_department")),
            requisition_id=bot.clean_text(item.get("job_code")) or job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def _mynexthire_url(item: dict[str, Any]) -> str:
    value = {
        "pageType": "jd",
        "cvSource": "careers",
        "reqId": item.get("requisitionId"),
        "requester": {"id": "", "code": "", "name": ""},
        "page": "careers",
        "bufilter": -1,
        "customFields": {},
    }
    encoded = base64.b64encode(
        json.dumps(value, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return f"https://sharechat.mynexthire.com/employer/jobs?src=careers&p={encoded}"


def parse_sharechat_careers(company: dict[str, Any]) -> list[bot.Job]:
    url = company["url"]
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    offset = ""
    while True:
        params: dict[str, Any] = {"limit": 100}
        if offset:
            params["offsetToken"] = offset
        response = requests.get(url, params=params, headers=HEADERS, timeout=40)
        response.raise_for_status()
        data = response.json().get("data") or {}
        for group in data.get("careersList") or []:
            for item in group.get("data") or []:
                job_id = bot.clean_text(item.get("requisitionId"))
                title = bot.clean_text(item.get("requisitionTitle") or item.get("designation"))
                if not job_id or not title or job_id in seen:
                    continue
                seen.add(job_id)
                jobs.append(bot.Job(
                    company=company["name"],
                    title=title,
                    location=bot.flatten_location(item.get("officeLocationNames")),
                    url=_mynexthire_url(item),
                    source="Official careers: ShareChat",
                    description=bot.clean_text(item.get("jobDescription")),
                    department=bot.clean_text(item.get("orgUnitName") or group.get("title")),
                    requisition_id=job_id,
                    wlb_score=company.get("wlb_score", 3),
                ))
        if not data.get("hasNext") or not data.get("offsetToken"):
            break
        offset = str(data["offsetToken"])
    return jobs


def parse_river_careers(company: dict[str, Any]) -> list[bot.Job]:
    response = requests.get(company["url"], headers=HEADERS, timeout=40)
    response.raise_for_status()
    groups = response.json().get("data") or {}
    jobs: list[bot.Job] = []
    for department, records in groups.items():
        for item in records or []:
            job_id = bot.clean_text(item.get("requisitionId"))
            title = bot.clean_text(item.get("requisitionTitle") or item.get("designation"))
            if not job_id or not title:
                continue
            location = bot.flatten_location(item.get("officeLocationNames"))
            query = urlencode({
                "location": location,
                "department": department,
                "title": title,
            })
            jobs.append(bot.Job(
                company=company["name"],
                title=title,
                location=location,
                url=f"https://www.rideriver.com/careers/current-openings/{job_id}?{query}",
                source="Official careers: River",
                description=bot.clean_text(item.get("jobDescription")),
                department=bot.clean_text(item.get("orgUnitName") or department),
                requisition_id=job_id,
                wlb_score=company.get("wlb_score", 3),
            ))
    return jobs


def fetch_company_jobs_with_custom_v25(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "urban_company": parse_urban_company,
        "sharechat_careers": parse_sharechat_careers,
        "river_careers": parse_river_careers,
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
