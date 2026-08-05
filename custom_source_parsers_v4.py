"""Transport-compatible Tavant parser layered over the production custom feeds."""
from __future__ import annotations

import json
import time
from typing import Any

import requests

import custom_source_parsers_v3 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v3


def parse_tavant_zwayam(company: dict[str, Any]) -> list[bot.Job]:
    """Read Tavant's Zwayam feed with the narrow Accept header it requires."""
    page_size = 10
    max_results = max(page_size, int(company.get("max_results", 10)))
    portal_url = company["career_site_url"].rstrip("/")
    # Zwayam intermittently leaves the connection open when it receives the
    # generic HTML/XML Accept list used by the other career systems.
    headers = {
        "User-Agent": bot.HEADERS["User-Agent"],
        "Accept": "*/*",
        "Origin": f"https://{company['domain']}",
        "Referer": f"{portal_url}/",
    }
    jobs: list[bot.Job] = []

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
                    timeout=(10, int(company.get("read_timeout_seconds", 20))),
                )
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        if response is None:
            raise RuntimeError("Tavant careers request did not return a response")

        data = previous.decode_json_envelope(response).get("data") or {}
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
    return jobs


def fetch_company_jobs_with_custom_v4(company: dict[str, Any]) -> list[bot.Job]:
    if company.get("ats") != "tavant_zwayam":
        return BASE_CUSTOM_FETCH(company)
    try:
        jobs = parse_tavant_zwayam(company)
        print(f"{company['name']}: {len(jobs)} raw jobs from tavant_zwayam")
        return jobs
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        bot.SCAN_ERRORS.append(company["name"])
        return []
