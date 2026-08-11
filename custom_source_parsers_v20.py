"""Adapters for structured job listings embedded in official career pages."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v11 as schema
import custom_source_parsers_v19 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v19
HEADERS = {
    **bot.HEADERS,
    "Accept": "text/html,application/xhtml+xml",
}


def _jobpostings(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        kind = value.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(str(item).casefold() == "jobposting" for item in kinds):
            yield value
        for child in value.values():
            yield from _jobpostings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _jobpostings(child)


def _posting_is_stale(posting: dict[str, Any], max_age_days: int) -> bool:
    now = datetime.now(timezone.utc)
    valid_through = bot.clean_text(posting.get("validThrough"))
    if valid_through:
        try:
            expiry = datetime.fromisoformat(valid_through.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry < now:
                return True
        except ValueError:
            pass
    date_posted = bot.clean_text(posting.get("datePosted"))
    if date_posted and max_age_days > 0:
        try:
            posted = datetime.fromisoformat(date_posted.replace("Z", "+00:00"))
            if posted.tzinfo is None:
                posted = posted.replace(tzinfo=timezone.utc)
            if posted < now - timedelta(days=max_age_days):
                return True
        except ValueError:
            pass
    return False


def parse_listing_jsonld(company: dict[str, Any]) -> list[bot.Job]:
    """Read every JobPosting object embedded in an official listing page."""
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for node in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(node.string or node.get_text(), strict=False)
        except (TypeError, json.JSONDecodeError):
            continue
        for posting in _jobpostings(payload):
            if _posting_is_stale(
                posting, max(0, int(company.get("max_posting_age_days", 0)))
            ):
                continue
            title = bot.clean_text(posting.get("title"))
            url = str(posting.get("url") or posting.get("sameAs") or "")
            if not title or not url or url in seen:
                continue
            seen.add(url)
            identifier = posting.get("identifier")
            if isinstance(identifier, dict):
                identifier = identifier.get("value") or identifier.get("name")
            department = posting.get("occupationalCategory")
            organization = posting.get("hiringOrganization")
            if isinstance(organization, dict):
                organization = organization.get("name")
            jobs.append(bot.Job(
                company=company["name"],
                title=title,
                location=schema._schema_location(posting),
                url=url,
                source="Official careers: structured job listing",
                description=bot.clean_text(posting.get("description")),
                department=bot.flatten_location([department, organization]),
                requisition_id=bot.clean_text(identifier),
                wlb_score=company.get("wlb_score", 3),
            ))
    return jobs


def fetch_company_jobs_with_custom_v20(
    company: dict[str, Any],
) -> list[bot.Job]:
    parser = {"listing_jsonld": parse_listing_jsonld}.get(company.get("ats"))
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
