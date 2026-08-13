"""Adapters for the remaining verified v44 dynamic career sources."""
from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
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
    session = requests.Session() if company.get("bootstrap_url") else requests
    if company.get("bootstrap_url"):
        bootstrap = session.get(
            company["bootstrap_url"], headers=BROWSER_HEADERS, timeout=35,
        )
        bootstrap.raise_for_status()
    payload = (
        {
            "bandList": None,
            "gradeList": None,
            "bandIDList": None,
            "gradeIDList": None,
            "employeeCategoryLabelList": None,
        }
        if company.get("bootstrap_url")
        else {}
    )
    raw_jobs: list[dict[str, Any]] = []
    for term in company.get("search_terms") or [None]:
        response = session.post(
            company["url"],
            params={"searchString": term} if term else None,
            json=payload,
            headers=JSON_HEADERS,
            timeout=35,
        )
        response.raise_for_status()
        raw_jobs.extend(response.json().get("response", [])[:limit])
    jobs_by_id: dict[str, bot.Job] = {}
    for item in raw_jobs:
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
        jobs_by_id.setdefault(job_id, bot.Job(
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
    return list(jobs_by_id.values())


def parse_darwinbox_v2(company: dict[str, Any]) -> list[bot.Job]:
    """Read the public all-jobs API behind Darwinbox Candidate v2 boards."""
    parsed = urlparse(company["career_site_url"])
    origin = f"{parsed.scheme}://{parsed.netloc}"
    company_id = company.get("company_id", "main")
    headers = {
        **JSON_HEADERS,
        "Origin": origin,
        "Referer": company["career_site_url"],
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    payload = {
        "companyId": company_id,
        "page": 1,
        "sort_option": "new",
        "limit": max(10, int(company.get("max_results", 100))),
    }
    if company.get("bootstrap_required"):
        session = requests.Session()
        bootstrap_url = (
            f"{origin}/ms/candidatev2/{company_id}/careers/allJobs"
        )
        bootstrap = session.get(
            bootstrap_url,
            headers={
                **BROWSER_HEADERS,
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Upgrade-Insecure-Requests": "1",
            },
            timeout=40,
        )
        bootstrap.raise_for_status()
        headers["Referer"] = bootstrap_url
        response = session.post(
            company["url"], json=payload, headers=headers, timeout=40,
        )
    else:
        response = requests.post(
            company["url"], json=payload, headers=headers, timeout=40,
        )
    response.raise_for_status()
    document = response.json()
    jobs: list[bot.Job] = []
    for item in document.get("data", []):
        job_id = bot.clean_text(
            item.get("id") or item.get("_id") or item.get("internal_job_code")
        )
        title = bot.clean_text(
            item.get("title")
            or item.get("designation_name")
            or item.get("designation_display_name")
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


def parse_icims_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read the server-rendered vacancy cards in public iCIMS portals."""
    max_pages = max(1, int(company.get("max_pages", 30)))
    jobs_by_id: dict[str, bot.Job] = {}
    for page in range(max_pages):
        response = requests.get(
            company["url"],
            params={"ss": 1, "pr": page, "in_iframe": 1},
            headers=BROWSER_HEADERS,
            timeout=40,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select("li.iCIMS_JobCardItem")
        added = 0
        for card in cards:
            link = card.select_one('a[href*="/jobs/"][href*="/job"]')
            title_node = card.select_one(".title h3")
            if link is None or title_node is None:
                continue
            url = urljoin(response.url, str(link.get("href") or ""))
            match = re.search(r"/jobs/(\d+)/", urlparse(url).path)
            job_id = match.group(1) if match else ""
            title = bot.clean_text(title_node.get_text(" "))
            if not job_id or not title or job_id in jobs_by_id:
                continue
            fields: dict[str, str] = {}
            for group in card.select(".iCIMS_JobHeaderTag"):
                key = group.select_one("dt")
                value = group.select_one("dd")
                if key is not None and value is not None:
                    fields[bot.clean_text(key.get_text(" ")).casefold()] = (
                        bot.clean_text(value.get_text(" "))
                    )
            location_node = card.select_one(".header.left span:not(.sr-only)")
            location = bot.clean_text(
                location_node.get_text(" ") if location_node else ""
            )
            if not location:
                for key, value in fields.items():
                    if "location" in key:
                        location = value
                        break
            description_node = card.select_one(".description")
            jobs_by_id[job_id] = bot.Job(
                company=company["name"],
                title=title,
                location=location,
                url=url,
                source="Official careers: iCIMS",
                description=bot.clean_text(
                    description_node.get_text(" ") if description_node else ""
                ),
                department=fields.get("category", ""),
                requisition_id=(
                    fields.get("id")
                    or fields.get("job id")
                    or fields.get("req. #")
                    or job_id
                ),
                wlb_score=company.get("wlb_score", 3),
            )
            added += 1
        if not cards or added == 0:
            break
    return list(jobs_by_id.values())


def parse_jobvite_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read Jobvite's public, server-rendered careers iframe."""
    response = requests.get(company["url"], headers=BROWSER_HEADERS, timeout=40)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for link in soup.select('.jv-job-list a[href*="/job/"]'):
        url = urljoin(response.url, str(link.get("href") or ""))
        job_id = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        title_node = link.select_one(".jv-job-list-name")
        location_node = link.select_one(".jv-job-list-location")
        title = bot.clean_text(title_node.get_text(" ") if title_node else "")
        if not job_id or not title or job_id in seen:
            continue
        seen.add(job_id)
        requisition_match = re.search(r"\(([^()]*(?:AI|REQ)[^()]*)\)\s*$", title, re.I)
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.clean_text(
                location_node.get_text(" ") if location_node else ""
            ),
            url=url,
            source="Official careers: Jobvite",
            description="",
            requisition_id=(
                requisition_match.group(1) if requisition_match else job_id
            ),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_recruiterflow_html(company: dict[str, Any]) -> list[bot.Job]:
    """Decode the public jobs payload embedded by Recruiterflow boards."""
    response = requests.get(company["url"], headers=BROWSER_HEADERS, timeout=40)
    response.raise_for_status()
    match = re.search(
        r"window\.jobsList\s*=\s*(\{.*?\})\s*;",
        response.text,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("Recruiterflow page did not expose its public jobs payload")
    document = json.loads(match.group(1))
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for department in document.get("department") or []:
        if not isinstance(department, list) or len(department) < 2:
            continue
        department_name, items = department[0], department[1]
        for item in items or []:
            if not isinstance(item, dict):
                continue
            job_id = bot.clean_text(item.get("job_id"))
            title = bot.clean_text(item.get("job_name"))
            if not job_id or not title or job_id in seen:
                continue
            seen.add(job_id)
            jobs.append(bot.Job(
                company=company["name"],
                title=title,
                location=bot.clean_text(item.get("details")),
                url=urljoin(response.url, str(item.get("apply_link") or "")),
                source="Official careers: Recruiterflow",
                description=bot.clean_text(" | ".join(filter(None, [
                    str(item.get("employment_type") or ""),
                    str(item.get("remote_type") or ""),
                ]))),
                department=bot.clean_text(department_name),
                requisition_id=job_id,
                wlb_score=company.get("wlb_score", 3),
            ))
    return jobs


def parse_gnani_api(company: dict[str, Any]) -> list[bot.Job]:
    """Read Gnani.ai's first-party public jobs endpoint."""
    response = requests.get(
        company["url"], headers={**BROWSER_HEADERS, "Accept": "application/json"},
        timeout=40,
    )
    response.raise_for_status()
    raw_jobs = ((response.json().get("data") or {}).get("jobs") or [])
    jobs: list[bot.Job] = []
    for item in raw_jobs:
        code = bot.clean_text(item.get("code"))
        title = bot.clean_text(item.get("title"))
        if not code or not title:
            continue
        skills = ", ".join(
            bot.clean_text(skill) for skill in item.get("skills") or [] if skill
        )
        experience = ""
        if item.get("minExperience") is not None or item.get("maxExperience") is not None:
            experience = (
                f"Experience: {item.get('minExperience', '')}-"
                f"{item.get('maxExperience', '')} years"
            )
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.flatten_location(item.get("location") or []),
            url=urljoin(response.url, f"/apply/{code}"),
            source="Official careers: Gnani.ai",
            description=" | ".join(filter(None, [experience, skills])),
            department=bot.clean_text(item.get("department")),
            requisition_id=code,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_hrone_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read the anonymous career-position API behind HROne portals."""
    session = requests.Session()
    listing = session.get(
        company["career_site_url"], headers=BROWSER_HEADERS, timeout=40,
    )
    listing.raise_for_status()
    params = {
        key: values[0]
        for key, values in parse_qs(urlparse(listing.url).query).items()
        if values
    }
    required = {"appId", "dc", "rqt", "cc"}
    if not required.issubset(params):
        raise ValueError("HROne portal redirect omitted required public identifiers")
    payload = {
        "departmentCode": "", "companyCode": params["cc"],
        "careerPortalType": params["rqt"], "jobTitle": "",
        "employmentType": "", "seniorityName": "", "jobFunction": "",
        "company": "", "businessUnitCode": "", "department": "",
        "subDepartment": "", "gradeCode": "", "designationCode": "",
        "levelCode": "", "branchCode": "", "subBranchCode": "",
        "regionCode": "", "locationId": "", "experience": "",
        "qualification": "", "skillsName": "", "urgentOpening": "",
        "jobPosted": "0", "isShortUrl": False,
        "pagination": {
            "pageNumber": 1,
            "pageSize": max(15, int(company.get("max_results", 100))),
        },
        "nationality": "", "preferredLocationId": "",
    }
    response = session.post(
        company["url"],
        json=payload,
        headers={
            **JSON_HEADERS,
            "domainCode": params["dc"],
            "apiKey": params["appId"],
            "AccessMode": "W",
            "Origin": f"{urlparse(listing.url).scheme}://{urlparse(listing.url).netloc}",
            "Referer": listing.url,
        },
        timeout=40,
    )
    response.raise_for_status()
    jobs: list[bot.Job] = []
    for item in response.json():
        job_id = bot.clean_text(item.get("jobCode") or item.get("positionId"))
        title = bot.clean_text(item.get("jobTitle"))
        if not job_id or not title:
            continue
        apply_params = {
            **params,
            "pid": item.get("encryptedPositionId") or "",
            "dptc": item.get("departmentCode") or "",
            "st": item.get("sourceType") or "",
            "fm": "CR",
        }
        apply_url = listing.url.split("?", 1)[0].replace(
            "/career-portal", "/apply-job"
        ) + "?" + urlencode(apply_params)
        experience = ""
        if item.get("experienceFrom") is not None or item.get("experienceTo") is not None:
            experience = (
                f"Experience: {item.get('experienceFrom', '')}-"
                f"{item.get('experienceTo', '')} years"
            )
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=bot.clean_text(item.get("preferredLocation")),
            url=str(item.get("jobApplicationPath") or apply_url),
            source="Official careers: HROne",
            description=experience,
            department=bot.clean_text(item.get("seniorityName")),
            requisition_id=job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_tonbo_html(company: dict[str, Any]) -> list[bot.Job]:
    """Read Tonbo's current roles from its GitHub-compatible WordPress API."""
    response = requests.get(
        company["url"],
        headers={**BROWSER_HEADERS, "Accept": "application/json"},
        timeout=40,
    )
    response.raise_for_status()
    document = response.json()
    page = str((document.get("content") or {}).get("rendered") or "")
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    matches = list(re.finditer(
        r"\[vc_tta_section\s+title=(?:&#8221;|[\"\u201c\u201d])"
        r"(.+?)(?:&#8221;|[\"\u201c\u201d])\s+tab_id=",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    ))
    for index, match in enumerate(matches):
        raw_title = bot.clean_text(unescape(match.group(1)))
        if "actively hiring" not in raw_title.casefold():
            continue
        title = re.sub(
            r"\s*\|?\s*actively hiring\s*\|?\s*$", "", raw_title,
            flags=re.IGNORECASE,
        ).strip(" |-\u2013")
        if not title or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(page)
        section = unescape(page[match.end():next_start])
        context = BeautifulSoup(section, "html.parser").get_text(" ")
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


def parse_kaleideo_wordpress(company: dict[str, Any]) -> list[bot.Job]:
    """Read KaleidEO's live role cards through its first-party WordPress API."""
    response = requests.get(
        company["url"],
        headers={**BROWSER_HEADERS, "Accept": "application/json"},
        timeout=40,
    )
    response.raise_for_status()
    documents = response.json()
    if isinstance(documents, dict):
        documents = [documents]
    page = " ".join(
        str((document.get("content") or {}).get("rendered") or "")
        for document in documents
        if isinstance(document, dict)
    )
    soup = BeautifulSoup(page, "html.parser")
    jobs: list[bot.Job] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href*='/careers-at-kaleideo/']"):
        href = urljoin(company["career_site_url"], anchor.get("href") or "")
        path = urlparse(href).path.rstrip("/")
        slug = path.rsplit("/", 1)[-1]
        if not slug or slug == "careers-at-kaleideo":
            continue
        heading = anchor.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        title = bot.clean_text(heading.get_text(" ") if heading else "")
        if not title or slug in seen:
            continue
        seen.add(slug)
        context = bot.clean_text(anchor.get_text(" "))
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=company.get("default_location", "Bengaluru, India"),
            url=href,
            source="Official careers: KaleidEO",
            description=context,
            requisition_id=slug,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_wordpress_post_type(company: dict[str, Any]) -> list[bot.Job]:
    """Map a first-party WordPress careers post type to stable job records."""
    response = requests.get(
        company["url"],
        headers={**BROWSER_HEADERS, "Accept": "application/json"},
        timeout=40,
    )
    response.raise_for_status()
    documents = response.json()
    if isinstance(documents, dict):
        documents = [documents]
    jobs: list[bot.Job] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        title = bot.clean_text(unescape(str(
            (document.get("title") or {}).get("rendered") or ""
        )))
        url = str(document.get("link") or "").strip()
        job_id = str(document.get("id") or document.get("slug") or "").strip()
        if not title or not url or not job_id:
            continue
        description_html = str(
            (document.get("content") or {}).get("rendered") or ""
        )
        jobs.append(bot.Job(
            company=company["name"],
            title=title,
            location=company.get("default_location", "Bengaluru, India"),
            url=url,
            source="Official careers: WordPress",
            description=bot.clean_text(
                BeautifulSoup(description_html, "html.parser").get_text(" ")
            ),
            requisition_id=job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_signalchip_wordpress(company: dict[str, Any]) -> list[bot.Job]:
    """Read Signalchip's current-position sections from its WordPress API."""
    response = requests.get(
        company["url"],
        headers={**BROWSER_HEADERS, "Accept": "application/json"},
        timeout=40,
    )
    response.raise_for_status()
    documents = response.json()
    if isinstance(documents, dict):
        documents = [documents]
    page = " ".join(
        str((document.get("content") or {}).get("rendered") or "")
        for document in documents
        if isinstance(document, dict)
    )
    soup = BeautifulSoup(page, "html.parser")
    jobs: list[bot.Job] = []
    for panel in soup.select(".sow-accordion-panel"):
        title_node = panel.select_one(".sow-accordion-title")
        text = bot.clean_text(title_node.get_text(" ") if title_node else "")
        if not text:
            continue
        job_id = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
        if not job_id:
            continue
        detail_node = panel.select_one(".sow-accordion-panel-content")
        jobs.append(bot.Job(
            company=company["name"],
            title=text,
            location=company.get("default_location", "Bengaluru, India"),
            url=f"{company['career_site_url']}#{job_id}",
            source="Official careers: Signalchip",
            description=bot.clean_text(
                detail_node.get_text(" ") if detail_node else ""
            ),
            requisition_id=job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_ameriprise_html(company: dict[str, Any]) -> list[bot.Job]:
    """Query Ameriprise's first-party, server-rendered job search."""
    terms = company.get("search_terms") or ["data", "analytics", "AI"]
    max_pages = max(1, int(company.get("max_pages_per_term", 2)))
    jobs_by_id: dict[str, bot.Job] = {}
    for term in terms:
        for page_number in range(1, max_pages + 1):
            response = requests.get(
                company["url"],
                params={"k": term, "p": page_number},
                headers=BROWSER_HEADERS,
                timeout=35,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select(".card-job")
            for card in cards:
                link = card.select_one("a.js-view-job[href]")
                action = card.select_one(".card-job-actions[data-id]")
                if link is None:
                    continue
                job_id = bot.clean_text(action.get("data-id") if action else "")
                title = bot.clean_text(link.get_text(" "))
                url = urljoin(response.url, str(link.get("href") or ""))
                if not job_id:
                    match = re.search(r"/(r\d+_\d+)(?:[/?#]|$)", urlparse(url).path)
                    job_id = match.group(1) if match else ""
                if not job_id or not title or not url:
                    continue
                metadata = [
                    bot.clean_text(item.get_text(" "))
                    for item in card.select(".job-meta .list-inline-item")
                ]
                jobs_by_id.setdefault(job_id, bot.Job(
                    company=company["name"],
                    title=title,
                    location=metadata[0] if metadata else "",
                    url=url,
                    source="Official careers: Ameriprise Financial",
                    description=" | ".join(metadata),
                    department=metadata[1] if len(metadata) > 1 else "",
                    requisition_id=job_id,
                    wlb_score=company.get("wlb_score", 3),
                ))
            if len(cards) < 20:
                break
    return list(jobs_by_id.values())


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
        "icims_html": parse_icims_html,
        "jobvite_html": parse_jobvite_html,
        "recruiterflow_html": parse_recruiterflow_html,
        "gnani_api": parse_gnani_api,
        "hrone_html": parse_hrone_html,
        "tonbo_html": parse_tonbo_html,
        "kaleideo_wordpress": parse_kaleideo_wordpress,
        "wordpress_post_type": parse_wordpress_post_type,
        "signalchip_wordpress": parse_signalchip_wordpress,
        "ameriprise_html": parse_ameriprise_html,
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
