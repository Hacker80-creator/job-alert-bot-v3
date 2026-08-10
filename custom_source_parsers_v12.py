"""Parsers for Kula, Paylocity, and Cohesity first-party job feeds."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v11 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v11
HEADERS = previous.HEADERS


def _kula_card(link):
    for parent in link.parents:
        if getattr(parent, "name", None) not in {"div", "li", "article"}:
            continue
        paragraphs = parent.find_all("p")
        text = bot.clean_text(parent.get_text(" "))
        if len(paragraphs) >= 2 and len(text) < 1500:
            return parent
    return link.parent


def parse_kula_html(company: dict) -> list[bot.Job]:
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    slug = next(
        (part for part in urlparse(company["url"]).path.split("/") if part), ""
    )
    jobs_by_url: dict[str, bot.Job] = {}
    for link in soup.select("a[href]"):
        href = str(link.get("href") or "")
        if not re.fullmatch(rf"/?{re.escape(slug)}/\d+/?", href):
            continue
        url = urljoin(company["url"], href)
        if url in jobs_by_url:
            continue
        card = _kula_card(link)
        paragraphs = card.find_all("p") if card else []
        title = bot.clean_text(paragraphs[0].get_text(" ")) if paragraphs else ""
        metadata = (
            bot.clean_text(paragraphs[1].get_text(" "))
            if len(paragraphs) > 1 else ""
        )
        parts = [part.strip() for part in metadata.split("•") if part.strip()]
        department = parts[0] if parts else ""
        location = parts[1] if len(parts) > 1 else metadata
        jobs_by_url[url] = bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=url,
            source="Official careers: Kula",
            department=department,
            description=" ".join(parts[2:]),
            wlb_score=company.get("wlb_score", 3),
        )

    settings = bot.load_config()["settings"]
    detail_budget = max(0, int(company.get("max_candidate_details", 30)))
    for job in jobs_by_url.values():
        if detail_budget <= 0:
            break
        if not bot.is_target_title(job.title):
            continue
        if not bot.has_location_match(job.location, settings):
            continue
        detail = requests.get(job.url, headers=HEADERS, timeout=30)
        detail.raise_for_status()
        detail_soup = BeautifulSoup(detail.text, "html.parser")
        main = detail_soup.select_one("main") or detail_soup.body
        if main:
            job.description = bot.clean_text(main.get_text(" "))
        detail_budget -= 1
    return list(jobs_by_url.values())


def parse_paylocity_feed(company: dict) -> list[bot.Job]:
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    raw_jobs = response.json().get("jobs") or []
    jobs: list[bot.Job] = []
    for item in raw_jobs:
        location = item.get("jobLocation") or {}
        jobs.append(bot.Job(
            company=company["name"],
            title=bot.clean_text(item.get("title")),
            location=bot.flatten_location([
                location.get("locationDisplayName") if isinstance(location, dict) else location,
                location.get("city") if isinstance(location, dict) else "",
                location.get("state") if isinstance(location, dict) else "",
            ]),
            url=str(
                item.get("applyUrl")
                or item.get("displayUrl")
                or f"https://recruiting.paylocity.com/recruiting/jobs/Details/{item.get('jobId', '')}"
            ),
            source="Official careers: Paylocity",
            description=bot.clean_text([
                item.get("description"),
                item.get("requirements"),
                item.get("salaryDescription"),
            ]),
            department=bot.clean_text(item.get("hiringDepartment")),
            salary_text=bot.clean_text(item.get("salaryDescription")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def _cohesity_detail_url(job_url: str) -> str:
    parsed = urlparse(job_url)
    marker = "/Cohesity_Careers"
    if marker not in parsed.path:
        return ""
    suffix = parsed.path.split(marker, 1)[1]
    suffix = re.sub(r"/apply/?$", "", suffix)
    return (
        f"{parsed.scheme}://{parsed.netloc}"
        "/wday/cxs/cohesity/Cohesity_Careers"
        + suffix
    )


def parse_cohesity_feed(company: dict) -> list[bot.Job]:
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    grouped = response.json().get("job_data") or {}
    jobs_by_id: dict[str, bot.Job] = {}
    detail_urls: dict[str, str] = {}
    for values in grouped.values():
        for item in values if isinstance(values, list) else []:
            job_id = str(item.get("JobID") or item.get("req_id") or "")
            if not job_id or job_id in jobs_by_id:
                continue
            public_url = str(item.get("jobUrl") or "").removesuffix("/apply")
            jobs_by_id[job_id] = bot.Job(
                company=company["name"],
                title=bot.clean_text(item.get("title")),
                location=bot.flatten_location([
                    item.get("primaryLocation"),
                    item.get("AdditionalLocations"),
                    item.get("country"),
                ]),
                url=public_url,
                source="Official careers: Cohesity",
                description=" ".join(filter(None, [
                    f"Employment: {bot.clean_text(item.get('categories'))}."
                    if item.get("categories") else "",
                    f"Job type: {bot.clean_text(item.get('jobType'))}."
                    if item.get("jobType") else "",
                ])),
                department=bot.clean_text(
                    item.get("careerSiteDept") or item.get("Cost_Center")
                ),
                wlb_score=company.get("wlb_score", 3),
            )
            detail_urls[job_id] = _cohesity_detail_url(str(item.get("jobUrl") or ""))

    settings = bot.load_config()["settings"]
    detail_budget = max(0, int(company.get("max_candidate_details", 40)))
    for job_id, job in jobs_by_id.items():
        if detail_budget <= 0:
            break
        if not bot.is_target_title(job.title):
            continue
        if not bot.has_location_match(job.location, settings):
            continue
        detail_url = detail_urls.get(job_id, "")
        if not detail_url:
            continue
        try:
            data = bot.get_json(detail_url)
            info = data.get("jobPostingInfo") or {}
            job.description = (
                bot.clean_text(info.get("jobDescription")) or job.description
            )
            if info.get("externalUrl"):
                job.url = str(info["externalUrl"])
            detail_budget -= 1
        except Exception as exc:
            print(f"WARN Cohesity detail failed: {exc}")
    return list(jobs_by_id.values())


def fetch_company_jobs_with_custom_v12(company: dict) -> list[bot.Job]:
    parser = {
        "kula_html": parse_kula_html,
        "paylocity_feed": parse_paylocity_feed,
        "cohesity_feed": parse_cohesity_feed,
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