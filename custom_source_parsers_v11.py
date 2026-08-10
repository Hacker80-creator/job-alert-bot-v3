"""Reusable verified parsers for the first user-supplied careers-link batches."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v10 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v10
HEADERS = previous.HEADERS


def _find_jobposting(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        kind = value.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            return value
        for child in value.values():
            found = _find_jobposting(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_jobposting(child)
            if found:
                return found
    return None


def _schema_location(posting: dict[str, Any]) -> str:
    values: list[str] = []
    locations = posting.get("jobLocation") or []
    locations = [locations] if isinstance(locations, dict) else locations
    for location in locations:
        if not isinstance(location, dict):
            values.append(str(location or ""))
            continue
        address = location.get("address") or {}
        if isinstance(address, dict):
            values.extend(str(address.get(key) or "") for key in (
                "addressLocality", "addressRegion", "addressCountry",
            ))
    if str(posting.get("jobLocationType") or "").casefold() == "telecommute":
        values.append("Remote")
        allowed = posting.get("applicantLocationRequirements") or []
        allowed = [allowed] if isinstance(allowed, dict) else allowed
        values.extend(
            str(item.get("name") or "") for item in allowed if isinstance(item, dict)
        )
    return bot.flatten_location([value for value in values if value])


def _workday_location_facet(facets: Any) -> tuple[str, str] | None:
    candidates: list[tuple[int, str, str]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            parameter = str(value.get("facetParameter") or "")
            for item in value.get("values") or []:
                if isinstance(item, dict):
                    descriptor = bot.normalize_match_text(str(item.get("descriptor") or ""))
                    identifier = str(item.get("id") or "")
                    if descriptor == "india" and identifier and parameter:
                        priority = 0 if "country" in parameter.casefold() else 2
                        candidates.append((priority, parameter, identifier))
                    elif descriptor in {"karnataka", "karnataka india"} and identifier and parameter:
                        candidates.append((1, parameter, identifier))
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(facets)
    if not candidates:
        return None
    _, parameter, identifier = sorted(candidates)[0]
    return parameter, identifier


def parse_workday_india(company: dict[str, Any]) -> list[bot.Job]:
    """Discover the current India facet, scan it, and enrich relevant details."""
    seed = bot.get_json(
        company["url"],
        method="POST",
        payload={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""},
    )
    location_facet = _workday_location_facet(seed.get("facets") or [])
    if not location_facet:
        print(f"{company['name']}: no current India Workday facet")
        return []

    parameter, identifier = location_facet
    facets = {parameter: [identifier]}
    terms = company.get("search_terms") or [
        "data", "machine learning", "AI", "DevOps", "platform", "automation",
    ]
    page_size = 20
    max_results = max(page_size, int(company.get("max_results_per_term", 60)))
    career_url = company["career_site_url"].rstrip("/")
    jobs_by_path: dict[str, bot.Job] = {}

    for term in terms:
        for offset in range(0, max_results, page_size):
            data = bot.get_json(
                company["url"],
                method="POST",
                payload={
                    "appliedFacets": facets,
                    "limit": page_size,
                    "offset": offset,
                    "searchText": term,
                },
            )
            raw_jobs = data.get("jobPostings") or []
            if not raw_jobs:
                break
            for item in raw_jobs:
                path = str(item.get("externalPath") or item.get("url") or "")
                if not path or path in jobs_by_path:
                    continue
                location = bot.flatten_location(
                    item.get("locationsText") or item.get("location")
                )
                if re.fullmatch(r"\d+\s+locations?", location.casefold()):
                    location = "India (multi-location)"
                jobs_by_path[path] = bot.Job(
                    company=company["name"],
                    title=bot.clean_text(item.get("title")),
                    location=location,
                    url=career_url + path if path.startswith("/") else path,
                    source="Official careers: Workday India facet",
                    description=bot.clean_text(
                        item.get("bulletFields") or item.get("jobDescription")
                    ),
                    department=bot.clean_text(item.get("jobFamily")),
                    wlb_score=company.get("wlb_score", 3),
                )
            total = int(data.get("total") or 0)
            if len(raw_jobs) < page_size or (total and offset + len(raw_jobs) >= total):
                break

    detail_budget = max(0, int(company.get("max_candidate_details", 12)))
    detail_base = company["url"].rsplit("/jobs", 1)[0]
    settings = bot.load_config()["settings"]
    for path, job in jobs_by_path.items():
        if detail_budget <= 0:
            break
        if not bot.is_target_title(job.title):
            continue
        if not bot.has_location_match(job.location, settings):
            continue
        try:
            detail = bot.get_json(detail_base + path)
            info = detail.get("jobPostingInfo") or {}
            job.description = bot.clean_text(info.get("jobDescription")) or job.description
            job.department = bot.clean_text(
                info.get("jobFamily") or info.get("jobRequisitionLocation")
            ) or job.department
            detail_location = bot.flatten_location([
                info.get("location"),
                info.get("jobRequisitionLocation"),
                info.get("additionalLocations"),
            ])
            if detail_location:
                job.location = detail_location
            public_url = str(info.get("externalUrl") or "")
            if public_url:
                job.url = public_url
            detail_budget -= 1
        except Exception as exc:
            print(f"WARN {company['name']} Workday detail failed: {exc}")
    return list(jobs_by_path.values())


def _nearest_job_card(link: Any) -> Any:
    for parent in link.parents:
        if getattr(parent, "name", None) == "li":
            return parent
        classes = " ".join(parent.get("class") or []) if hasattr(parent, "get") else ""
        if re.search(r"(?:job-card|list-item|search-result)", classes, re.IGNORECASE):
            return parent
    return link.parent


def _talentbrew_title(link: Any) -> str:
    heading = link.select_one("h1, h2, h3, strong")
    return bot.clean_text(heading.get_text(" ") if heading else link.get_text(" "))


def parse_talentbrew_html(company: dict[str, Any]) -> list[bot.Job]:
    """Search TalentBrew pages and enrich relevant jobs from JobPosting JSON-LD."""
    terms = company.get("search_terms") or [
        "data", "machine learning", "DevOps", "platform", "automation",
    ]
    required = bot.clean_text(company.get("required_keyword"))
    max_pages = max(1, int(company.get("max_pages_per_term", 3)))
    jobs_by_url: dict[str, bot.Job] = {}

    for term in terms:
        query = f"{required} {term}".strip()
        seen_page_urls: set[str] = set()
        for page in range(1, max_pages + 1):
            response = requests.get(
                company["url"],
                params={"k": query, "p": page},
                headers=HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_urls: set[str] = set()
            for link in soup.select('a[data-job-id][href*="/job/"]'):
                url = urljoin(company["url"], str(link.get("href") or ""))
                if not url:
                    continue
                page_urls.add(url)
                if url in jobs_by_url:
                    continue
                card = _nearest_job_card(link)
                location_node = card.select_one(
                    ".job-location, .location, [class*='job-location']"
                ) if card else None
                department_node = card.select_one(
                    ".category, .job-category, [class*='job-category']"
                ) if card else None
                jobs_by_url[url] = bot.Job(
                    company=company["name"],
                    title=_talentbrew_title(link),
                    location=bot.clean_text(
                        location_node.get_text(" ") if location_node else ""
                    ),
                    url=url,
                    source="Official careers: TalentBrew",
                    department=bot.clean_text(
                        department_node.get_text(" ") if department_node else ""
                    ),
                    wlb_score=company.get("wlb_score", 3),
                )
            if not page_urls or page_urls.issubset(seen_page_urls):
                break
            seen_page_urls.update(page_urls)

    settings = bot.load_config()["settings"]
    detail_budget = max(0, int(company.get("max_candidate_details", 25)))
    for job in jobs_by_url.values():
        if detail_budget <= 0:
            break
        if not bot.is_target_title(job.title):
            continue
        if not bot.has_location_match(job.location, settings):
            continue
        detail = requests.get(job.url, headers=HEADERS, timeout=30)
        detail.raise_for_status()
        soup = BeautifulSoup(detail.text, "html.parser")
        posting = None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                posting = _find_jobposting(json.loads(script.string or ""))
            except (TypeError, json.JSONDecodeError):
                continue
            if posting:
                break
        if posting:
            job.title = bot.clean_text(posting.get("title")) or job.title
            job.description = bot.clean_text(posting.get("description"))
            job.location = _schema_location(posting) or job.location
            job.url = str(posting.get("url") or job.url)
            identifier = posting.get("identifier")
            if isinstance(identifier, dict):
                identifier = identifier.get("value") or identifier.get("name")
            job.requisition_id = bot.clean_text(identifier)
        else:
            description = soup.select_one(".job-description, .job-description__content")
            if description:
                job.description = bot.clean_text(description.get_text(" "))
        detail_budget -= 1
    return list(jobs_by_url.values())


def parse_successfactors_search(company: dict[str, Any]) -> list[bot.Job]:
    """Search a Jobs2Web/SAP SuccessFactors board with bounded India queries."""
    terms = company.get("search_terms") or [
        "data", "machine learning", "AI", "DevOps", "platform", "automation",
    ]
    max_pages = max(1, int(company.get("max_pages_per_term", 2)))
    page_size = 25
    jobs_by_url: dict[str, bot.Job] = {}
    for term in terms:
        for page in range(max_pages):
            response = requests.get(
                company["url"],
                params={
                    "q": term,
                    "locationsearch": company.get("search_location", "India"),
                    "startrow": page * page_size,
                },
                headers=HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            rows = soup.select("tr.data-row")
            for row in rows:
                link = row.select_one("span.jobTitle.hidden-phone a.jobTitle-link")
                if link is None:
                    link = row.select_one("a.jobTitle-link")
                if link is None:
                    continue
                url = urljoin(company["url"], str(link.get("href") or ""))
                if not url or url in jobs_by_url:
                    continue
                location_node = row.select_one("td.colLocation span.jobLocation")
                department_node = row.select_one("td.colFacility span.jobFacility")
                jobs_by_url[url] = bot.Job(
                    company=company["name"],
                    title=bot.clean_text(link.get_text(" ")),
                    location=bot.clean_text(
                        location_node.get_text(" ") if location_node else ""
                    ),
                    url=url,
                    source="Official careers: SAP SuccessFactors",
                    department=bot.clean_text(
                        department_node.get_text(" ") if department_node else ""
                    ),
                    wlb_score=company.get("wlb_score", 3),
                )
            if len(rows) < page_size:
                break

    settings = bot.load_config()["settings"]
    detail_budget = max(0, int(company.get("max_candidate_details", 25)))
    for job in jobs_by_url.values():
        if detail_budget <= 0:
            break
        if not bot.is_target_title(job.title):
            continue
        if not bot.has_location_match(job.location, settings):
            continue
        detail = requests.get(job.url, headers=HEADERS, timeout=30)
        detail.raise_for_status()
        description = BeautifulSoup(detail.text, "html.parser").select_one(
            ".jobdescription"
        )
        if description:
            job.description = bot.clean_text(description.get_text(" "))
        detail_budget -= 1
    return list(jobs_by_url.values())


def parse_sensehq_next_data(company: dict[str, Any]) -> list[bot.Job]:
    """Read SenseHQ's server-rendered job records, including experience ranges."""
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    script = BeautifulSoup(response.text, "html.parser").find(
        "script", id="__NEXT_DATA__"
    )
    if not script or not script.string:
        raise ValueError("SenseHQ __NEXT_DATA__ job payload is missing")
    page_props = json.loads(script.string).get("props", {}).get("pageProps", {})
    raw_jobs = (page_props.get("jobsData") or {}).get("rows") or []
    jobs: list[bot.Job] = []
    for item in raw_jobs:
        if str(item.get("job_status") or "").casefold() != "open":
            continue
        job_id = str(item.get("id") or "")
        if not job_id:
            continue
        location = bot.clean_text(item.get("location"))
        workplace = bot.clean_text(item.get("workplace_type"))
        if workplace.casefold() == "remote" and "remote" not in location.casefold():
            location = "; ".join(filter(None, [location, "Remote - India"]))
        minimum, maximum = item.get("experience_start"), item.get("experience_end")
        experience = (
            f"Experience required: {minimum} to {maximum} years."
            if minimum is not None and maximum is not None else ""
        )
        jobs.append(bot.Job(
            company=company["name"],
            title=bot.clean_text(item.get("title")),
            location=location,
            url=f"{company['career_site_url'].rstrip('/')}?jobId={job_id}",
            source="Official careers: SenseHQ",
            description=" ".join(filter(None, [
                experience,
                f"Workplace: {workplace}." if workplace else "",
                bot.clean_text(item.get("description_external")),
            ])),
            department=bot.clean_text(item.get("department")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_trakstar_rss(company: dict[str, Any]) -> list[bot.Job]:
    """Read Trakstar RSS while refusing abandoned, years-old job records."""
    response = requests.get(company["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=max(1, int(company.get("max_age_days", 180)))
    )
    namespace = "{https://recruiterbox.com/rss/job/}"
    jobs: list[bot.Job] = []
    stale = 0
    for item in root.findall("./channel/item"):
        published_text = bot.clean_text(item.findtext("pubDate"))
        if published_text:
            try:
                published = parsedate_to_datetime(published_text)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                if published < cutoff:
                    stale += 1
                    continue
            except (TypeError, ValueError, OverflowError):
                pass
        link = bot.clean_text(item.findtext("link"))
        if link.startswith("http://"):
            link = "https://" + link[len("http://"):]
        jobs.append(bot.Job(
            company=company["name"],
            title=bot.clean_text(item.findtext("title")),
            location=bot.flatten_location([
                item.findtext(namespace + "locationCity"),
                item.findtext(namespace + "locationState"),
                item.findtext(namespace + "locationCountry"),
            ]),
            url=link,
            source="Official careers: Trakstar RSS",
            description=bot.clean_text(item.findtext("description")),
            department=bot.clean_text(item.findtext(namespace + "team")),
            wlb_score=company.get("wlb_score", 3),
        ))
    if stale:
        print(f"{company['name']}: ignored {stale} stale Trakstar records")
    return jobs


def fetch_company_jobs_with_custom_v11(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "workday_india": parse_workday_india,
        "talentbrew_html": parse_talentbrew_html,
        "successfactors_search": parse_successfactors_search,
        "sensehq_next_data": parse_sensehq_next_data,
        "trakstar_rss": parse_trakstar_rss,
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