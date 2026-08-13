"""Adapters for the remaining verified v44 dynamic career sources."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v29 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v29
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
JSON_HEADERS = {
    **BROWSER_HEADERS,
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def _xml_meta(hit: ElementTree.Element, name: str) -> str:
    for meta in hit.findall(".//{*}Meta"):
        if meta.get("name") != name:
            continue
        values = [
            str(value.text or value.get("value") or value.get("name") or "").strip()
            for value in meta.findall("./{*}MetaString")
        ]
        return bot.clean_text(" ".join(filter(None, values)))
    return ""


def parse_dassault_xml(company: dict[str, Any]) -> list[bot.Job]:
    """Read Dassault Systemes' first-party XML career search API."""
    terms = company.get("search_terms") or [
        "data", "analytics", "machine learning", "AI", "automation",
    ]
    pages_per_term = max(1, int(company.get("max_pages_per_term", 3)))
    jobs_by_id: dict[str, bot.Job] = {}
    for term in terms:
        for page in range(pages_per_term):
            response = requests.get(
                company["url"],
                params={
                    "q": f"card_content_type:career {term}",
                    "start": page * 10,
                    "rows": 10,
                },
                headers={**BROWSER_HEADERS, "Accept": "application/xml,text/xml,*/*"},
                timeout=35,
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
            hits = root.findall(".//{*}Hit")
            for hit in hits:
                if _xml_meta(hit, "content_lang").casefold() not in {"", "en"}:
                    continue
                job_id = _xml_meta(hit, "card_id")
                title = _xml_meta(hit, "content_title")
                detail_url = _xml_meta(hit, "content_cta_1_url")
                apply_url = _xml_meta(hit, "content_cta_2_url")
                if not job_id or not title or not (detail_url or apply_url):
                    continue
                jobs_by_id.setdefault(job_id, bot.Job(
                    company=company["name"],
                    title=title,
                    location=_xml_meta(hit, "content_info_2_value"),
                    url=detail_url or apply_url,
                    source="Official careers: Dassault Systemes",
                    description=_xml_meta(hit, "content_summary"),
                    department=_xml_meta(hit, "content_type_display_text"),
                    requisition_id=job_id,
                    wlb_score=company.get("wlb_score", 3),
                ))
            if len(hits) < 10:
                break
    return list(jobs_by_id.values())


def parse_peoplestrong(company: dict[str, Any]) -> list[bot.Job]:
    """Read the public PeopleStrong jobs API used by MathCo."""
    limit = max(10, int(company.get("max_results", 100)))
    response = requests.post(
        company["url"],
        json={},
        headers=JSON_HEADERS,
        timeout=35,
    )
    response.raise_for_status()
    jobs: list[bot.Job] = []
    for item in response.json().get("response", [])[:limit]:
        job_id = bot.clean_text(item.get("requisitionId") or item.get("jobCode"))
        title = bot.clean_text(item.get("jobTitle") or item.get("designation"))
        url = str(item.get("jobDetailUrl") or "").strip()
        if not job_id or not title or not url:
            continue
        location = bot.clean_text(
            item.get("locationHierarchyComplete") or item.get("locationHierarchy")
        ).replace(">", ", ")
        skills = item.get("skills") or {}
        skill_names: list[str] = []
        if isinstance(skills, dict):
            for values in skills.values():
                if isinstance(values, list):
                    skill_names.extend(bot.clean_text(value) for value in values)
        description = " | ".join(filter(None, [
            bot.clean_text(item.get("designation")),
            bot.clean_text(item.get("organizationUnitComplete")),
            bot.clean_text(item.get("expRange")),
            ", ".join(filter(None, skill_names)),
        ]))
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=url,
            source="Official careers: PeopleStrong",
            description=description,
            department=bot.clean_text(
                item.get("functionalArea") or item.get("organizationUnit")
            ),
            salary_text=bot.clean_text(item.get("CTCRange")),
            requisition_id=job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_darwinbox_v2(company: dict[str, Any]) -> list[bot.Job]:
    """Read the public all-jobs API behind Darwinbox Candidate v2 boards."""
    parsed = urlparse(company["career_site_url"])
    origin = f"{parsed.scheme}://{parsed.netloc}"
    company_id = company.get("company_id", "main")
    headers = {
        **JSON_HEADERS,
        "Origin": origin,
        "Referer": company["career_site_url"],
    }
    response = requests.post(
        company["url"],
        json={
            "companyId": company_id,
            "page": 1,
            "sort_option": "new",
            "limit": max(10, int(company.get("max_results", 100))),
        },
        headers=headers,
        timeout=40,
    )
    response.raise_for_status()
    document = response.json()
    jobs: list[bot.Job] = []
    for item in document.get("data", []):
        job_id = bot.clean_text(
            item.get("id") or item.get("_id") or item.get("internal_job_code")
        )
        title = bot.clean_text(
            item.get("title") or item.get("designation_name")
        )
        if not job_id or not title:
            continue
        location = bot.clean_text(
            item.get("locations")
            or item.get("officelocation_show_arr")
            or item.get("country")
        )
        if item.get("is_remote"):
            location = f"Remote, {location}" if location else "Remote"
        details_url = (
            f"{origin}/ms/candidatev2/{company_id}/careers/jobDetails/{job_id}"
        )
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=details_url,
            source="Official careers: Darwinbox",
            description=" | ".join(filter(None, [
                bot.clean_text(item.get("jd_summary") or item.get("jd")),
                bot.clean_text(item.get("experience")),
                bot.clean_text(item.get("functional_area_name")),
            ])),
            department=bot.clean_text(item.get("department_name")),
            salary_text=bot.clean_text(item.get("salary_range")),
            requisition_id=bot.clean_text(item.get("internal_job_code")) or job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_tonbo_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read Tonbo's current role headings using its browser-compatible page."""
    response = requests.get(company["url"], headers=BROWSER_HEADERS, timeout=40)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for heading in soup.select("h4"):
        raw_title = bot.clean_text(heading.get_text(" "))
        if "actively hiring" not in raw_title.casefold():
            continue
        title = re.sub(
            r"\s*\|?\s*actively hiring\s*\|?\s*$", "", raw_title,
            flags=re.IGNORECASE,
        ).strip(" |-\u2013")
        if not title or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        context = heading.parent.get_text(" ") if heading.parent else raw_title
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=company.get("default_location", "Bengaluru, India"),
            url=f"{company['career_site_url']}#{re.sub(r'[^a-z0-9]+', '-', title.casefold()).strip('-')}",
            source="Official careers: Tonbo Imaging",
            description=bot.clean_text(context),
            requisition_id=re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-"),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_lululemon_avature(company: dict[str, Any]) -> list[bot.Job]:
    """Query lululemon's server-rendered Avature keyword search."""
    terms = company.get("search_terms") or ["data", "analytics", "AI"]
    jobs_by_id: dict[str, bot.Job] = {}
    for term in terms:
        response = requests.post(
            company["url"],
            data={"listFilterMode": "true", "search": term},
            headers=BROWSER_HEADERS,
            timeout=35,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.select('a[href*="/JobDetail/"]'):
            url = urljoin(response.url, str(anchor.get("href") or ""))
            match = re.search(r"/(\d+)(?:[/?#]|$)", urlparse(url).path)
            job_id = match.group(1) if match else ""
            title = bot.clean_text(anchor.get_text(" "))
            if not job_id or not title:
                continue
            card = anchor.find_parent(["article", "li", "div"])
            context = bot.clean_text(card.get_text(" ") if card else title)
            location = context[len(title):].strip(" |,-") if context.startswith(title) else context
            jobs_by_id.setdefault(job_id, bot.Job(
                company=company["name"],
                title=title,
                location=location,
                url=url,
                source="Official careers: lululemon Avature",
                description=context,
                requisition_id=job_id,
                wlb_score=company.get("wlb_score", 3),
            ))
    return list(jobs_by_id.values())


def fetch_company_jobs_with_custom_v30(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "dassault_xml": parse_dassault_xml,
        "peoplestrong": parse_peoplestrong,
        "darwinbox_v2": parse_darwinbox_v2,
        "tonbo_html": parse_tonbo_html,
        "lululemon_avature": parse_lululemon_avature,
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
