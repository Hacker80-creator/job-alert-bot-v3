"""Adapters for Enphase's JSON feed and Pegasystems' public search form."""
from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v17 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v17
HTML_HEADERS = {
    **bot.HEADERS,
    "Accept": "text/html,application/xhtml+xml",
}
API_HEADERS = {
    **bot.HEADERS,
    "Accept": "application/json,text/plain,*/*",
}


def _decode_nested_html(value: Any) -> str:
    decoded = html.unescape(html.unescape(str(value or "")))
    return bot.clean_text(BeautifulSoup(decoded, "html.parser").get_text(" "))


def parse_enphase_api(company: dict[str, Any]) -> list[bot.Job]:
    """Read Enphase's public first-party Jobvite-backed JSON endpoint."""
    response = requests.get(company["url"], headers=API_HEADERS, timeout=30)
    response.raise_for_status()
    jobs: list[bot.Job] = []
    for item in response.json().get("rows") or []:
        job_id = bot.clean_text(item.get("jid"))
        title = bot.clean_text(item.get("name"))
        if not job_id or not title:
            continue
        detail_template = str(
            company.get("detail_url_template")
            or "https://enphase.com/en-in/job/{job_id}"
        )
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.clean_text(item.get("location")),
            url=detail_template.format(job_id=job_id),
            source="Official careers: Enphase API",
            description=_decode_nested_html(item.get("description__value")),
            department=bot.clean_text(item.get("category")),
            requisition_id=(
                bot.clean_text(item.get("requisitionid")) or job_id
            ),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def _pega_job_card(card: Any, company: dict[str, Any], base_url: str) -> bot.Job | None:
    link = card.find("a", href=re.compile(r"/about/careers/\d+/"))
    if link is None:
        return None
    href = str(link.get("href") or "")
    heading = card.find("h3")
    title = bot.clean_text(
        heading.get_text(" ") if heading is not None else link.get_text(" ")
    )
    if not title or not href:
        return None
    context = bot.clean_text(card.get_text(" "))
    location = ""
    for paragraph in card.find_all("p"):
        value = bot.clean_text(paragraph.get_text(" "))
        if value.casefold().startswith("location:"):
            location = value.split(":", 1)[1].strip()
            break
    department = ""
    for node in card.find_all(["h2", "p"]):
        value = bot.clean_text(node.get_text(" "))
        if value.casefold().startswith("job category:"):
            department = value.split(":", 1)[1].strip()
            break
    match = re.search(r"/about/careers/(\d+)/", href)
    return bot.Job(
        company=company["name"],
        title=title,
        location=location,
        url=urljoin(base_url, href),
        source="Official careers: Pegasystems",
        description=context,
        department=department,
        requisition_id=match.group(1) if match else "",
        wlb_score=company.get("wlb_score", 3),
    )


def parse_pega_html(company: dict[str, Any]) -> list[bot.Job]:
    """Query Pegasystems' server-rendered search and enrich local target roles."""
    terms = company.get("search_terms") or [
        "data", "machine learning", "AI", "analytics", "DevOps",
        "automation", "platform",
    ]
    jobs_by_url: dict[str, bot.Job] = {}
    for term in terms:
        response = requests.post(
            company["url"],
            data={
                "q": str(term),
                "op": "Submit",
                "form_id": "pega_search_core_search_form",
            },
            headers=HTML_HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for card in soup.find_all("bolt-card-replacement"):
            job = _pega_job_card(card, company, response.url)
            if job is not None:
                jobs_by_url.setdefault(job.url, job)

    settings = bot.load_config()["settings"]
    detail_budget = max(0, int(company.get("max_candidate_details", 20)))
    for job in jobs_by_url.values():
        if detail_budget <= 0:
            break
        if not (
            bot.is_target_title(job.title)
            and bot.has_location_match(job.location, settings)
        ):
            continue
        detail = requests.get(job.url, headers=HTML_HEADERS, timeout=30)
        detail.raise_for_status()
        soup = BeautifulSoup(detail.text, "html.parser")
        description = soup.select_one(
            "[class*='job-description'], article main, main article, main"
        )
        if description is not None:
            value = bot.clean_text(description.get_text(" "))
            if len(value) >= 100:
                job.description = value
        detail_budget -= 1
    return list(jobs_by_url.values())


def fetch_company_jobs_with_custom_v18(
    company: dict[str, Any],
) -> list[bot.Job]:
    parser = {
        "enphase_api": parse_enphase_api,
        "pega_html": parse_pega_html,
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
