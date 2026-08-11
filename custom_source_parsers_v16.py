"""Adapters for dynamic boards with reliable server-rendered fallbacks."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v15 as previous
import custom_source_parsers_v11 as jobs2web
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v15
HEADERS = {
    **bot.HEADERS,
    "Accept": "text/html,application/xhtml+xml",
}
API_HEADERS = {
    **bot.HEADERS,
    "Accept": "application/json",
}


def parse_applytojob_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read public ApplyToJob cards and enrich relevant local vacancies."""
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    settings = bot.load_config()["settings"]
    jobs: list[bot.Job] = []
    seen: set[str] = set()

    for card in soup.select("li.list-group-item"):
        link = card.select_one("a[href*='/apply/']")
        if link is None:
            continue
        href = urljoin(response.url, str(link.get("href") or ""))
        title = bot.clean_text(link.get_text(" "))
        if not href or not title or href in seen:
            continue
        seen.add(href)
        metadata = [
            bot.clean_text(node.get_text(" "))
            for node in card.select("ul.list-group-item-text li")
        ]
        location = metadata[0] if metadata else ""
        department = metadata[1] if len(metadata) > 1 else ""
        job = bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=href,
            source="Official careers: ApplyToJob",
            description=bot.clean_text(card.get_text(" ")),
            department=department,
            wlb_score=company.get("wlb_score", 3),
        )
        jobs.append(job)

    detail_budget = max(0, int(company.get("max_candidate_details", 25)))
    for job in jobs:
        if detail_budget <= 0:
            break
        if not (
            bot.is_target_title(job.title)
            and bot.has_location_match(job.location, settings)
        ):
            continue
        detail = requests.get(job.url, headers=HEADERS, timeout=30)
        detail.raise_for_status()
        detail_soup = BeautifulSoup(detail.text, "html.parser")
        description = detail_soup.select_one(
            ".job-description, #job-description, [class*='job-description']"
        )
        if description is None:
            description = detail_soup.find("main")
        if description is not None:
            job.description = bot.clean_text(description.get_text(" "))
        detail_budget -= 1
    return jobs


def _smart_apply_payload(page: str) -> dict[str, Any]:
    node = BeautifulSoup(page, "html.parser").find("code", id="smartApplyData")
    if node is None:
        raise ValueError("Eightfold smartApplyData payload is missing")
    payload = json.loads(node.get_text())
    if not isinstance(payload, dict):
        raise ValueError("Eightfold smartApplyData payload is not an object")
    return payload


def _matching_position(
    value: Any, position_id: str,
) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if str(value.get("id") or "") == position_id and (
            value.get("job_description") or value.get("description")
        ):
            return value
        for child in value.values():
            match = _matching_position(child, position_id)
            if match is not None:
                return match
    elif isinstance(value, list):
        for child in value:
            match = _matching_position(child, position_id)
            if match is not None:
                return match
    return None


def parse_eightfold_html(company: dict[str, Any]) -> list[bot.Job]:
    """Use Eightfold's server-rendered search when its JSON API blocks runners."""
    terms = company.get("search_terms") or [
        "data scientist", "data analyst", "data engineer", "machine learning",
        "AI", "analytics", "DevOps", "platform", "automation",
    ]
    locations = company.get("search_locations") or [
        "Bangalore, India", "Bengaluru, India", "Remote, India",
    ]
    career_url = company["career_site_url"].rstrip("/")
    jobs_by_id: dict[str, bot.Job] = {}
    for term in terms:
        for location_query in locations:
            response = requests.get(
                career_url,
                params={"query": term, "location": location_query},
                headers=HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            payload = _smart_apply_payload(response.text)
            for item in payload.get("positions") or []:
                job_id = str(item.get("id") or "")
                title = bot.clean_text(
                    item.get("posting_name") or item.get("name")
                )
                if not job_id or not title or job_id in jobs_by_id:
                    continue
                location = bot.flatten_location(
                    item.get("locations") or item.get("location")
                )
                jobs_by_id[job_id] = bot.Job(
                    company=company["name"],
                    title=title,
                    location=location,
                    url=str(item.get("canonicalPositionUrl") or (
                        f"{career_url}/job/{job_id}"
                    )),
                    source="Official careers: Eightfold HTML",
                    description=bot.clean_text(item.get("job_description")),
                    department=bot.flatten_location([
                        item.get("department"), item.get("business_unit"),
                    ]),
                    requisition_id=bot.clean_text(
                        item.get("display_job_id") or item.get("ats_job_id")
                    ),
                    wlb_score=company.get("wlb_score", 3),
                )

    settings = bot.load_config()["settings"]
    detail_budget = max(0, int(company.get("max_candidate_details", 30)))
    for job_id, job in jobs_by_id.items():
        if detail_budget <= 0:
            break
        if not (
            bot.is_target_title(job.title)
            and bot.has_location_match(job.location, settings)
        ):
            continue
        detail = requests.get(job.url, headers=HEADERS, timeout=30)
        detail.raise_for_status()
        info = _matching_position(_smart_apply_payload(detail.text), job_id)
        if info is not None:
            job.description = bot.clean_text(
                info.get("job_description") or info.get("description")
            ) or job.description
        detail_budget -= 1
    return list(jobs_by_id.values())


def parse_jobs2web_rss(company: dict[str, Any]) -> list[bot.Job]:
    """Read the official RSS search exposed by Jobs2Web/SAP boards."""
    terms = company.get("search_terms") or [
        "data", "machine learning", "AI", "analytics", "platform", "automation",
    ]
    location_query = company.get("search_location", "India")
    jobs_by_url: dict[str, bot.Job] = {}
    for term in terms:
        response = requests.get(
            company["url"],
            params={
                "locale": company.get("locale", "en_US"),
                "keywords": f"({term}) AND locationSearch:({location_query})",
            },
            headers={
                **HEADERS,
                "Accept": "application/rss+xml,application/xml,text/xml,*/*",
            },
            timeout=30,
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        for item in root.findall("./channel/item"):
            title = bot.clean_text(item.findtext("title"))
            url = bot.clean_text(item.findtext("link"))
            guid = bot.clean_text(item.findtext("guid"))
            if not title or not url or guid == "0" or title.casefold().startswith(
                "no jobs currently available"
            ):
                continue
            jobs_by_url.setdefault(url, bot.Job(
                company=company["name"],
                title=title,
                location="",
                url=url,
                source="Official careers: Jobs2Web RSS",
                description=bot.clean_text(item.findtext("description")),
                requisition_id=guid,
                wlb_score=company.get("wlb_score", 3),
            ))

    detail_budget = max(0, int(company.get("max_candidate_details", 30)))
    for job in jobs_by_url.values():
        if detail_budget <= 0:
            break
        if not bot.is_target_title(job.title):
            continue
        detail = requests.get(job.url, headers=HEADERS, timeout=30)
        detail.raise_for_status()
        soup = BeautifulSoup(detail.text, "html.parser")
        posting = None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                posting = jobs2web._find_jobposting(json.loads(script.string or ""))
            except (TypeError, json.JSONDecodeError):
                continue
            if posting:
                break
        if posting:
            job.title = bot.clean_text(posting.get("title")) or job.title
            job.location = jobs2web._schema_location(posting) or job.location
            job.description = bot.clean_text(posting.get("description")) or job.description
            job.url = str(posting.get("url") or job.url)
        else:
            description = soup.select_one(".jobdescription, .job-description")
            if description is not None:
                job.description = bot.clean_text(description.get_text(" "))
        detail_budget -= 1
    return list(jobs_by_url.values())


def parse_workday_multi(company: dict[str, Any]) -> list[bot.Job]:
    """Combine multiple first-party Workday tenants shown on one career site."""
    jobs_by_url: dict[str, bot.Job] = {}
    for source in company.get("sources") or []:
        label = bot.clean_text(source.get("label")) or "Workday"
        source_company = {
            **company,
            **source,
            "name": company["name"],
            "ats": "workday_search",
        }
        source_company.pop("sources", None)
        try:
            for job in bot.parse_workday_search(source_company):
                jobs_by_url.setdefault(job.url, job)
        except Exception as exc:
            print(f"WARN {company['name']} {label} Workday source failed: {exc}")
            bot.SCAN_ERRORS.append(f"{company['name']} ({label})")
    return list(jobs_by_url.values())


def parse_direct_job_html(company: dict[str, Any]) -> list[bot.Job]:
    """Enrich conservative first-party job links from their detail pages."""
    jobs = bot.parse_html_search(company)
    title_markers = [
        bot.clean_text(marker)
        for marker in company.get("title_cleanup_locations") or []
        if bot.clean_text(marker)
    ]
    for job in jobs:
        folded = job.title.casefold()
        positions = [
            folded.find(marker.casefold())
            for marker in title_markers
            if folded.find(marker.casefold()) > 0
        ]
        if positions:
            job.title = job.title[:min(positions)].rstrip(" -–—,|")
    detail_budget = max(0, int(company.get("max_candidate_details", 60)))
    for job in jobs:
        if detail_budget <= 0:
            break
        try:
            response = requests.get(job.url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            posting = None
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    posting = jobs2web._find_jobposting(
                        json.loads(script.string or "")
                    )
                except (TypeError, json.JSONDecodeError):
                    continue
                if posting:
                    break
            if posting:
                job.title = bot.clean_text(posting.get("title")) or job.title
                job.location = jobs2web._schema_location(posting) or job.location
                job.description = (
                    bot.clean_text(posting.get("description")) or job.description
                )
                job.url = str(posting.get("url") or job.url)
                identifier = posting.get("identifier")
                if isinstance(identifier, dict):
                    identifier = identifier.get("value") or identifier.get("name")
                job.requisition_id = bot.clean_text(identifier)
            else:
                heading = soup.select_one("main h1, h1")
                if heading is not None:
                    candidate_title = bot.clean_text(heading.get_text(" "))
                    if 2 <= len(candidate_title) <= 180:
                        job.title = candidate_title
                description = soup.select_one(
                    "[class*='job-description'], [id*='job-description'], main"
                )
                if description is not None:
                    detail = bot.clean_text(description.get_text(" "))
                    if len(detail) >= 100:
                        job.description = detail
        except Exception as exc:
            print(f"WARN {company['name']} direct detail failed: {exc}")
        detail_budget -= 1
    return jobs


def _enrich_candidate_pages(
    jobs: list[bot.Job], company: dict[str, Any],
) -> list[bot.Job]:
    settings = bot.load_config()["settings"]
    detail_budget = max(0, int(company.get("max_candidate_details", 30)))
    for job in jobs:
        if detail_budget <= 0:
            break
        if not (
            bot.is_target_title(job.title)
            and bot.has_location_match(job.location, settings)
        ):
            continue
        try:
            response = requests.get(job.url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            description = soup.select_one(
                "[class*='job-description'], [id*='job-description'], main"
            )
            if description is not None:
                detail = bot.clean_text(description.get_text(" "))
                if len(detail) >= 100:
                    job.description = detail
        except Exception as exc:
            print(f"WARN {company['name']} candidate detail failed: {exc}")
        detail_budget -= 1
    return jobs


def parse_freshteam_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read server-rendered Freshteam vacancy cards."""
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for card in soup.select("li.heading"):
        link = card.select_one("a.job-title[href]")
        if link is None:
            continue
        url = urljoin(response.url, str(link.get("href") or ""))
        if not url or url in seen:
            continue
        seen.add(url)
        location = card.select_one(".job-location .location-info")
        description = card.select_one(".job-list-info .job-desc")
        jobs.append(bot.Job(
            company=company["name"],
            title=bot.clean_text(link.get_text(" ")),
            location=bot.clean_text(
                location.get_text(" ") if location else ""
            ),
            url=url,
            source="Official careers: Freshteam",
            description=bot.clean_text(
                description.get_text(" ") if description else ""
            ),
            wlb_score=company.get("wlb_score", 3),
        ))
    return _enrich_candidate_pages(jobs, company)


def parse_trakstar_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read public Trakstar/Hire job cards with stable detail URLs."""
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for card in soup.select(".js-careers-page-job-list-item"):
        link = card.select_one("a[href*='/jobs/']")
        title_node = card.select_one(".js-job-list-opening-name")
        location_node = card.select_one(".js-job-list-opening-loc")
        if link is None or title_node is None:
            continue
        url = urljoin(response.url, str(link.get("href") or ""))
        if not url or url in seen:
            continue
        seen.add(url)
        location = bot.clean_text(
            location_node.get("title") if location_node else ""
        ) or bot.clean_text(
            location_node.get_text(" ") if location_node else ""
        )
        jobs.append(bot.Job(
            company=company["name"],
            title=bot.clean_text(title_node.get("title"))
            or bot.clean_text(title_node.get_text(" ")),
            location=location,
            url=url,
            source="Official careers: Trakstar",
            description=bot.clean_text(card.get_text(" ")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return _enrich_candidate_pages(jobs, company)


def parse_ripplehire(company: dict[str, Any]) -> list[bot.Job]:
    """Use RippleHire's public candidate search and detail endpoints."""
    base_url = company["url"].rstrip("/") + "/"
    token = str(company["token"])
    source = str(company.get("source") or "CAREERSITE")
    page_size = max(10, min(100, int(company.get("page_size", 100))))
    max_results = max(page_size, int(company.get("max_results", 500)))
    session = requests.Session()
    landing = session.get(
        company["career_site_url"], headers=HEADERS, timeout=30
    )
    landing.raise_for_status()
    language_response = session.get(
        urljoin(base_url, "getcompanylang"),
        params={"token": token, "source": source},
        headers=API_HEADERS,
        timeout=30,
    )
    language_response.raise_for_status()
    language = str(
        language_response.json().get("companyDefaultLang") or "en"
    )
    jobs_by_id: dict[str, bot.Job] = {}
    total = max_results
    page = 0
    while page * page_size < min(total, max_results):
        search_params = {
            "page": page,
            "search": "*:*",
            "token": token,
            "source": source,
            "pagesize": page_size,
        }
        response = session.post(
            urljoin(base_url, "candidatejobsearch"),
            data={
                "careerSiteUrlParams": json.dumps(search_params),
                "lang": language,
            },
            headers={**API_HEADERS, "Referer": landing.url},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        raw_jobs = payload.get("jobVoList") or []
        total = int(payload.get("totalJobCount") or len(raw_jobs))
        for item in raw_jobs:
            job_id = str(item.get("jobSeq") or item.get("jobId") or "")
            title = bot.clean_text(item.get("jobTitle"))
            if not job_id or not title or job_id in jobs_by_id:
                continue
            experience = bot.clean_text(item.get("jobReqExp"))
            description = (
                f"Experience required: {experience}." if experience else ""
            )
            jobs_by_id[job_id] = bot.Job(
                company=company["name"],
                title=title,
                location=bot.clean_text(
                    item.get("locations") or item.get("jobLocation")
                ),
                url=f"{company['career_site_url'].split('#', 1)[0]}#detail/job/{job_id}",
                source="Official careers: RippleHire",
                description=description,
                department=bot.clean_text(
                    item.get("bussinessUnit") or item.get("businessUnit")
                ),
                requisition_id=bot.clean_text(item.get("jobCode")) or job_id,
                wlb_score=company.get("wlb_score", 3),
            )
        if not raw_jobs or len(raw_jobs) < page_size:
            break
        page += 1

    settings = bot.load_config()["settings"]
    detail_budget = max(0, int(company.get("max_candidate_details", 30)))
    for job_id, job in jobs_by_id.items():
        if detail_budget <= 0:
            break
        if not (
            bot.is_target_title(job.title)
            and bot.has_location_match(job.location, settings)
        ):
            continue
        detail = session.get(
            urljoin(base_url, "candidatejobdetail"),
            params={
                "token": token, "jobSeq": job_id,
                "source": source, "lang": language,
            },
            headers=API_HEADERS,
            timeout=30,
        )
        detail.raise_for_status()
        info = detail.json().get("jobVO") or {}
        job.description = bot.clean_text(" ".join(filter(None, [
            job.description,
            str(info.get("jobDesc") or ""),
            str(info.get("jobPrimarySkills") or ""),
            str(info.get("jobSecondarySkills") or ""),
        ])))
        detail_budget -= 1
    return list(jobs_by_id.values())


def fetch_company_jobs_with_custom_v16(
    company: dict[str, Any],
) -> list[bot.Job]:
    parser = {
        "applytojob_html": parse_applytojob_html,
        "eightfold_html": parse_eightfold_html,
        "jobs2web_rss": parse_jobs2web_rss,
        "workday_multi": parse_workday_multi,
        "direct_job_html": parse_direct_job_html,
        "freshteam_html": parse_freshteam_html,
        "trakstar_html": parse_trakstar_html,
        "ripplehire": parse_ripplehire,
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
