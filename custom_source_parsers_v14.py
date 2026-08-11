"""Official HTML adapters for Google Careers and CGI Njoyn."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

import custom_source_parsers_v13 as previous
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v13


def _title_from_google_path(url: str) -> str:
    match = re.search(r"/jobs/results/[0-9]+-(.+?)(?:/)?$", urlparse(url).path)
    if not match:
        return ""
    words = match.group(1).replace("-", " ").split()
    acronyms = {
        "ai": "AI", "ml": "ML", "aiml": "AI/ML", "bi": "BI",
        "sql": "SQL", "etl": "ETL",
    }
    return " ".join(acronyms.get(word.casefold(), word.capitalize()) for word in words)


def parse_google_careers_html(company: dict[str, Any]) -> list[bot.Job]:
    """Search Google's server-rendered first-party careers results."""
    terms = company.get("search_terms") or [
        "data", "machine learning", "analytics", "AI", "DevOps"
    ]
    location = company.get("search_location") or "Bengaluru, Karnataka, India"
    max_pages = max(1, int(company.get("max_pages_per_term", 2)))
    by_id: dict[str, bot.Job] = {}
    session = requests.Session()

    for term in terms:
        previous_count = -1
        for page in range(1, max_pages + 1):
            params = {"location": location, "q": term}
            if page > 1:
                params["page"] = page
            response = session.get(
                company["url"], params=params, headers=bot.HEADERS, timeout=30
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            base = soup.find("base", href=True)
            join_base = (
                urljoin(response.url, str(base.get("href")))
                if base is not None
                else response.url
            )
            for link in soup.select('a[href*="jobs/results/"]'):
                href = urljoin(join_base, str(link.get("href") or ""))
                match = re.search(
                    r"/jobs/results/([0-9]+)-", urlparse(href).path
                )
                if not match:
                    continue
                job_id = match.group(1)
                if job_id in by_id:
                    continue
                title = _title_from_google_path(href)
                if not title:
                    continue
                parsed = urlsplit(href)
                direct_url = urlunsplit(
                    (parsed.scheme, parsed.netloc, parsed.path, "", "")
                )
                by_id[job_id] = bot.Job(
                    company=company["name"],
                    title=title,
                    location=location,
                    url=direct_url,
                    source="Official careers: Google",
                    wlb_score=company.get("wlb_score", 4),
                )
            if len(by_id) == previous_count:
                break
            previous_count = len(by_id)

    candidates = [
        job for job in by_id.values() if bot.is_target_title(job.title)
    ]
    detail_limit = max(0, int(company.get("max_details", 200)))
    candidates = candidates[:detail_limit]
    detail_workers = max(
        1, min(8, int(company.get("detail_workers", 8)))
    )

    def enrich(job: bot.Job) -> bot.Job | None:
        try:
            response = requests.get(
                job.url, headers=bot.HEADERS, timeout=30
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            main = soup.find("main") or soup.body
            description = bot.clean_text(main.get_text(" ")) if main else ""
            if len(description) < 200:
                return None
            job.description = description
            return job
        except Exception:
            return None

    enriched: list[bot.Job] = []
    with ThreadPoolExecutor(max_workers=detail_workers) as pool:
        futures = [pool.submit(enrich, job) for job in candidates]
        for future in as_completed(futures):
            job = future.result()
            if job is not None:
                enriched.append(job)

    enriched.sort(key=lambda item: item.title.casefold())
    failed_details = len(candidates) - len(enriched)
    if failed_details:
        print(
            f"WARN {company['name']} skipped {failed_details} jobs "
            "whose official descriptions could not be verified"
        )
    return enriched

def parse_njoyn_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read official Njoyn table rows used by CGI."""
    response = requests.get(
        company["url"], headers=bot.HEADERS, timeout=30
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for link in soup.select('a[href*="JobDetails"], a[href*="jobdetails"]'):
        row = link.find_parent("tr")
        if row is None:
            continue
        cells = [bot.clean_text(cell.get_text(" ")) for cell in row.find_all("td")]
        if len(cells) < 4:
            continue
        href = urljoin(response.url, str(link.get("href") or ""))
        if not href or href in seen:
            continue
        seen.add(href)
        title = cells[1] if len(cells) > 1 else bot.clean_text(link.get_text(" "))
        department = cells[2] if len(cells) > 2 else ""
        city = cells[3] if len(cells) > 3 else ""
        country = cells[4] if len(cells) > 4 else "India"
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.clean_text(f"{city}, {country}"),
            url=href,
            source="Official careers: Njoyn",
            description=bot.clean_text(" ".join(cells)),
            department=department,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def _slugify(value: str) -> str:
    value = bot.normalize_match_text(value).replace(" ", "-")
    return re.sub(r"-+", "-", value).strip("-") or "job"


def parse_makemytrip_api(company: dict[str, Any]) -> list[bot.Job]:
    """Read MakeMyTrip's first-party job list and candidate detail API."""
    response = requests.get(company["url"], headers=bot.HEADERS, timeout=30)
    response.raise_for_status()
    raw_jobs = response.json().get("allJobs") or []
    career_url = company["career_site_url"].rstrip("/")
    detail_url = company.get("detail_url") or f"{career_url}/api/jobDetails"
    settings = bot.load_config()["settings"]
    jobs: list[bot.Job] = []
    candidates: list[tuple[bot.Job, str]] = []

    for item in raw_jobs:
        job_id = str(item.get("job_id") or "")
        title = bot.clean_text(item.get("job_title"))
        if not job_id or not title:
            continue
        location = bot.flatten_location(
            item.get("location")
            or [item.get("location_city"), item.get("location_country")]
        )
        experience_from = bot.clean_text(item.get("experience_from"))
        experience_to = bot.clean_text(item.get("experience_to"))
        description = bot.clean_text(" ".join(filter(None, [
            f"Minimum {experience_from} years experience."
            if experience_from else "",
            f"Experience range {experience_from} to {experience_to} years."
            if experience_from and experience_to else "",
            str(item.get("parent_department") or ""),
            str(item.get("department") or ""),
            str(item.get("business_unit") or ""),
        ])))
        public_url = (
            f"{career_url}/prod/opportunity/{job_id}/{_slugify(title)}"
        )
        job = bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=public_url,
            source="Official careers: MakeMyTrip",
            description=description,
            department=bot.clean_text(item.get("department")),
            wlb_score=company.get("wlb_score", 3),
        )
        jobs.append(job)
        if bot.is_target_title(title) and bot.has_location_match(location, settings):
            candidates.append((job, job_id))

    detail_limit = max(0, int(company.get("max_candidate_details", 30)))
    for job, job_id in candidates[:detail_limit]:
        try:
            detail = requests.get(
                detail_url,
                params={"jobId": job_id},
                headers=bot.HEADERS,
                timeout=30,
            )
            detail.raise_for_status()
            info = detail.json().get("data") or {}
            job.description = bot.clean_text(" ".join(filter(None, [
                job.description,
                str(info.get("job_decription") or info.get("job_description") or ""),
            ])))
            if info.get("applyUrl"):
                job.url = str(info["applyUrl"])
        except Exception as exc:
            print(f"WARN {company['name']} detail {job_id} failed: {exc}")
    return jobs


def parse_zoho_careers_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read the official Zoho Recruit JSON embedded in its careers page."""
    response = requests.get(company["url"], headers=bot.HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    payload = soup.find(id="jobs")
    if payload is None or not payload.get("value"):
        raise ValueError("official careers page did not expose its jobs payload")
    raw_jobs = json.loads(str(payload.get("value")))
    career_url = company.get("career_site_url") or company["url"]
    jobs: list[bot.Job] = []
    for item in raw_jobs:
        job_id = str(item.get("id") or "")
        title = bot.clean_text(
            item.get("Posting_Title") or item.get("Job_Opening_Name")
        )
        if not job_id or not title or not item.get("Publish", True):
            continue
        location = bot.flatten_location([
            item.get("City"), item.get("State"), item.get("Country1"),
            "Remote India" if item.get("Remote_Job") else "",
        ])
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=location,
            url=f"{career_url.rstrip('/')}/{job_id}",
            source="Official careers: Zoho Recruit",
            description=bot.clean_text(item.get("Job_Description")),
            department=bot.clean_text(item.get("Job_Type")),
            wlb_score=company.get("wlb_score", 4),
        ))
    return jobs

def parse_jibe_api(company: dict[str, Any]) -> list[bot.Job]:
    """Read the public Jibe/iCIMS JSON used by Booking.com."""
    page_size = max(1, min(100, int(company.get("page_size", 100))))
    max_results = max(page_size, int(company.get("max_results", 500)))
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    offset = 0
    while offset < max_results:
        params = dict(company.get("query_params") or {})
        params.update({
            "limit": page_size,
            "page": offset // page_size + 1,
        })
        response = requests.get(
            company["url"],
            params=params,
            headers=bot.HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        raw_jobs = data.get("jobs") or []
        for wrapper in raw_jobs:
            item = wrapper.get("data") if isinstance(wrapper, dict) else {}
            item = item or {}
            job_id = str(item.get("req_id") or item.get("slug") or "")
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            salary = ""
            if item.get("salary_min_value") or item.get("salary_max_value"):
                salary = " - ".join(str(value) for value in (
                    item.get("salary_min_value"), item.get("salary_max_value")
                ) if value is not None)
            jobs.append(bot.Job(
                company=company["name"],
                title=bot.clean_text(item.get("title")),
                location=bot.flatten_location(
                    item.get("full_location")
                    or [item.get("city"), item.get("state"), item.get("country")]
                ),
                url=str(item.get("apply_url") or (
                    f"{company['career_site_url'].rstrip('/')}/{job_id}"
                )),
                source="Official careers: Jibe/iCIMS",
                description=bot.clean_text(item.get("description")),
                department=bot.flatten_location(
                    item.get("department") or item.get("category")
                ),
                salary_text=salary,
                wlb_score=company.get("wlb_score", 4),
            ))
        total = int(data.get("totalCount") or data.get("count") or len(raw_jobs))
        offset += len(raw_jobs)
        if not raw_jobs or offset >= total:
            break
    return jobs


def _ukg_location(item: dict[str, Any]) -> str:
    parts: list[Any] = []
    for location in item.get("Locations") or []:
        if not isinstance(location, dict):
            parts.append(location)
            continue
        address = location.get("Address") or {}
        state = address.get("State") or {}
        country = address.get("Country") or {}
        parts.append([
            location.get("LocalizedName"),
            location.get("LocalizedDescription"),
            address.get("City"),
            state.get("Name") if isinstance(state, dict) else state,
            country.get("Name") if isinstance(country, dict) else country,
        ])
    return bot.flatten_location(parts)


def parse_ukg_jobboard(company: dict[str, Any]) -> list[bot.Job]:
    """Read the public UKG/UltiPro search endpoint used by OneStream."""
    page_size = max(1, min(50, int(company.get("page_size", 50))))
    max_results = max(page_size, int(company.get("max_results", 300)))
    base_url = company["career_site_url"].rstrip("/")
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    offset = 0
    while offset < max_results:
        payload = {"opportunitySearch": {
            "QueryString": "",
            "Filters": [],
            "Top": page_size,
            "Skip": offset,
            "OrderBy": [{
                "Value": "postedDateDesc",
                "PropertyName": "PostedDate",
                "Ascending": False,
            }],
        }}
        response = requests.post(
            company["url"],
            json=payload,
            headers={**bot.HEADERS, "Referer": base_url + "/"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        raw_jobs = data.get("opportunities") or []
        for item in raw_jobs:
            job_id = str(item.get("Id") or "")
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            jobs.append(bot.Job(
                company=company["name"],
                title=bot.clean_text(item.get("Title")),
                location=_ukg_location(item),
                url=f"{base_url}/OpportunityDetail?opportunityId={job_id}",
                source="Official careers: UKG",
                description=bot.clean_text(item.get("BriefDescription")),
                department=bot.clean_text(item.get("JobCategoryName")),
                wlb_score=company.get("wlb_score", 3),
            ))
        total = int(data.get("totalCount") or len(raw_jobs))
        offset += len(raw_jobs)
        if not raw_jobs or offset >= total:
            break
    return jobs

def parse_walmart_graphql(company: dict[str, Any]) -> list[bot.Job]:
    """Search Walmart's first-party persisted GraphQL career queries."""
    terms = company.get("search_terms") or [
        "data", "machine learning", "AI", "analytics", "DevOps", "platform"
    ]
    max_results = max(10, int(company.get("max_results_per_term", 40)))
    search_query_id = company["search_query_id"]
    detail_query_id = company["detail_query_id"]
    career_url = company["career_site_url"].rstrip("/")
    headers = {
        **bot.HEADERS,
        "Content-Type": "application/json",
        "Referer": career_url + "/results",
    }
    jobs_by_id: dict[str, bot.Job] = {}
    candidate_ids: set[str] = set()
    settings = bot.load_config()["settings"]

    for term in terms:
        for offset in range(0, max_results, 20):
            response = requests.post(
                company["url"],
                json={
                    "queryId": search_query_id,
                    "variables": {"jobSearchRequest": {
                        "searchString": term,
                        "from": offset,
                        "size": min(20, max_results - offset),
                    }},
                    "headers": None,
                },
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            search = (response.json().get("data") or {}).get("jobSearch") or {}
            raw_jobs = search.get("searchResults") or []
            if not raw_jobs:
                break
            for item in raw_jobs:
                job_id = str(item.get("jobId") or "")
                if not job_id or job_id in jobs_by_id:
                    continue
                title = bot.clean_text(item.get("jobTitle"))
                location = bot.flatten_location([
                    location.get("storeName")
                    for location in item.get("location") or []
                    if isinstance(location, dict)
                ])
                job = bot.Job(
                    company=company["name"],
                    title=title,
                    location=location,
                    url=f"{career_url}/job/{job_id}",
                    source="Official careers: Walmart GraphQL",
                    description="",
                    department=bot.clean_text(item.get("brand")),
                    wlb_score=company.get("wlb_score", 4),
                )
                jobs_by_id[job_id] = job
                if bot.is_target_title(title) and bot.has_location_match(location, settings):
                    candidate_ids.add(job_id)
            if len(raw_jobs) < 20:
                break

    invalid_candidates: set[str] = set()
    ids = sorted(candidate_ids)
    for start in range(0, len(ids), 40):
        batch = ids[start:start + 40]
        try:
            response = requests.post(
                company["url"],
                json={
                    "queryId": detail_query_id,
                    "variables": {
                        "jobIds": ",".join(batch),
                        "languageCode": "en_us",
                        "isExternal": True,
                    },
                    "headers": None,
                },
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            details = (
                (response.json().get("data") or {}).get("bulkUnifiedJobDetails")
                or []
            )
            returned: set[str] = set()
            for item in details:
                job_id = str(item.get("jobId") or "")
                if not job_id or job_id not in jobs_by_id:
                    continue
                returned.add(job_id)
                if item.get("active") is False:
                    invalid_candidates.add(job_id)
                    continue
                job = jobs_by_id[job_id]
                job.description = bot.clean_text(item.get("description"))
                job.title = bot.clean_text(
                    item.get("jobPostingTitle") or item.get("title") or job.title
                )
                job.salary_text = bot.clean_text(
                    item.get("payRange") or item.get("salaryRange")
                )
            invalid_candidates.update(set(batch) - returned)
        except Exception as exc:
            print(f"WARN {company['name']} detail batch failed: {exc}")
            invalid_candidates.update(batch)

    return [
        job for job_id, job in jobs_by_id.items()
        if job_id not in invalid_candidates
    ]

def fetch_company_jobs_with_custom_v14(
    company: dict[str, Any],
) -> list[bot.Job]:
    parser = {
        "google_careers_html": parse_google_careers_html,
        "njoyn_html": parse_njoyn_html,
        "makemytrip_api": parse_makemytrip_api,
        "zoho_careers_html": parse_zoho_careers_html,
        "jibe_api": parse_jibe_api,
        "ukg_jobboard": parse_ukg_jobboard,
        "walmart_graphql": parse_walmart_graphql,
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
