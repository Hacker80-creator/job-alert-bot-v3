"""Reusable server-rendered Avature career-site adapter."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v14 as previous
import custom_source_parsers_v11 as jobs2web
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v14
HEADERS = {
    **bot.HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/json",
}


def _json_ld_posting(soup: BeautifulSoup) -> dict[str, Any] | None:
    for node in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(node.string or "")
        except (TypeError, ValueError):
            continue
        records = payload if isinstance(payload, list) else [payload]
        for record in records:
            if isinstance(record, dict) and record.get("@type") == "JobPosting":
                return record
    return None


def parse_avature_html(company: dict[str, Any]) -> list[bot.Job]:
    """Search compatible public Avature pages and enrich relevant local jobs."""
    settings = bot.load_config()["settings"]
    terms = company.get("search_terms") or [
        "data", "machine learning", "analytics", "AI", "platform", "automation",
    ]
    jobs_by_url: dict[str, bot.Job] = {}
    for term in terms:
        response = requests.post(
            company["url"],
            data={"listFilterMode": "true", "search": term},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.select(
            "a[href*='/JobDetail'], a[href*='/FolderDetail/']"
        ):
            title = bot.clean_text(link.get_text(" "))
            href = urljoin(response.url, str(link.get("href") or ""))
            if not title or title.casefold().startswith("share ") or href.startswith("mailto:"):
                continue
            container = link.find_parent(["article", "li", "tr", "div"])
            location_node = container.select_one(
                ".list-item-location, [class*='job-location'], [class*='location']"
            ) if container else None
            family_node = container.select_one(
                ".list-item-family, [class*='job-family'], [class*='department']"
            ) if container else None
            context = bot.clean_text(container.get_text(" ") if container else "")
            location = bot.clean_text(location_node.get_text(" ") if location_node else "")
            if not location and context.casefold().startswith(title.casefold()):
                remainder = context[len(title):].strip(" -•")
                location = bot.clean_text(remainder.split(" • ", 1)[0])
            if href and href not in jobs_by_url:
                jobs_by_url[href] = bot.Job(
                    company=company["name"], title=title, location=location,
                    url=href, source="Official careers: Avature",
                    description=context, department=bot.clean_text(
                        family_node.get_text(" ") if family_node else ""
                    ),
                    wlb_score=company.get("wlb_score", 3),
                )

    detail_budget = max(0, int(company.get("max_candidate_details", 60)))
    for job in jobs_by_url.values():
        if detail_budget <= 0:
            break
        if not bot.is_target_title(job.title):
            continue
        if job.location and not bot.has_location_match(job.location, settings):
            continue
        try:
            response = requests.get(job.url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            description = soup.select_one(
                "article.article--details .article__content, "
                ".article--details .article__content, [class*='job-description']"
            )
            detail = bot.clean_text(description.get_text(" ") if description else "")
            posting = _json_ld_posting(soup)
            if posting:
                job.title = bot.clean_text(posting.get("title")) or job.title
                job.location = jobs2web._schema_location(posting) or job.location
                identifier = posting.get("identifier")
                if isinstance(identifier, dict):
                    identifier = identifier.get("value") or identifier.get("name")
                job.requisition_id = bot.clean_text(identifier) or job.requisition_id
            if not job.location:
                location_nodes = soup.select(
                    ".posting-location .article__content__view__field__value, "
                    "[class*='posting-location'] [class*='field__value']"
                )
                job.location = bot.flatten_location([
                    node.get_text(" ") for node in location_nodes
                ])
            job.description = (
                detail
                or bot.clean_text(posting.get("description") if posting else "")
                or job.description
            )
        except Exception as exc:
            print(f"WARN {company['name']} Avature detail failed: {exc}")
        detail_budget -= 1
    return list(jobs_by_url.values())


def fetch_company_jobs_with_custom_v15(company: dict[str, Any]) -> list[bot.Job]:
    parser = {"avature_html": parse_avature_html}.get(company.get("ats"))
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
