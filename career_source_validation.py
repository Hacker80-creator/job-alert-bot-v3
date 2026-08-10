"""Validate user-supplied official careers URLs without guessing feeds."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

import source_discovery


ROOT = Path(__file__).parent
MAPPINGS_FILE = ROOT / "career_source_mappings.txt"
ALLOWLIST_FILE = ROOT / "company_allowlist.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JobAlertRuntimeValidator/1.0; +https://github.com/)",
    "Accept": "text/html,application/json,application/xml,text/xml,*/*",
}
TIMEOUT = (7, 20)
NO_PUBLIC_TEXT = "NO PUBLIC OFFICIAL LIVE JOB BOARD FOUND"
SUPPORTED_ATS = {
    "greenhouse", "lever", "ashby", "workday_india", "workday_search",
    "oracle_hcm", "phenom", "successfactors_search", "talentbrew_html",
    "kula_html", "paylocity_feed", "cohesity_feed",
}
KNOWN_RESOLUTIONS: dict[str, dict[str, str]] = {
    "Chronosphere": {
        "provider": "ashby", "slug": "chronospherejobs",
        "resolved_url": "https://jobs.ashbyhq.com/chronospherejobs",
    },
    "CleverTap": {
        "provider": "kula", "resolved_url": "https://careers.kula.ai/clevertap",
    },
    "CloudBees": {
        "provider": "paylocity",
        "resolved_url": "https://recruiting.paylocity.com/recruiting/v2/api/feed/jobs/982bc369-6352-4fa4-942d-7c76bfca29b4",
    },
    "Cohesity": {
        "provider": "cohesity",
        "resolved_url": "https://www.cohesity.com/bin/cohesity/open-positions",
    },
    "Couchbase": {
        "provider": "greenhouse", "slug": "couchbaseinc",
        "resolved_url": "https://boards.greenhouse.io/couchbaseinc",
    },
}


def normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_value.casefold())


def repair_mojibake(value: str) -> str:
    if not any(marker in value for marker in ("Ã", "Â", "â")):
        return value
    try:
        return value.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def canonical_allowlist() -> dict[str, str]:
    names = [
        line.strip()
        for line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return {normalize(name): name for name in names}


def read_mappings() -> list[dict[str, Any]]:
    canonical = canonical_allowlist()
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(
        MAPPINGS_FILE.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        if ": " not in line:
            raise ValueError(f"Malformed mapping at line {line_number}: {line}")
        submitted_name, value = line.split(": ", 1)
        repaired = repair_mojibake(submitted_name.strip())
        name = canonical.get(normalize(repaired), repaired)
        if name.casefold() in seen:
            raise ValueError(f"Duplicate company mapping: {name}")
        seen.add(name.casefold())
        value = value.strip()
        if value == NO_PUBLIC_TEXT:
            records.append({
                "name": name, "submitted_name": submitted_name.strip(),
                "declared_no_public_board": True,
            })
        elif value.startswith(("https://", "http://")):
            records.append({
                "name": name, "submitted_name": submitted_name.strip(),
                "source_url": value, "declared_no_public_board": False,
            })
        else:
            raise ValueError(f"Unsupported mapping value for {name}: {value}")
    return records


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "get_text"):
        value = value.get_text(" ")
    return re.sub(r"\s+", " ", str(value)).strip()


def response_json(session: requests.Session, url: str) -> Any:
    response = session.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def source_result(
    status: str, *, provider: str, job_count: int,
    source: dict[str, Any] | None = None, reason: str = "", resolved_url: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status, "provider": provider, "job_count": max(0, int(job_count)),
    }
    if source:
        result["source"] = source
    if reason:
        result["reason"] = reason
    if resolved_url:
        result["resolved_url"] = resolved_url
    return result


def probe_greenhouse(
    session: requests.Session, name: str, slug: str, resolved_url: str = ""
) -> dict[str, Any]:
    metadata = response_json(session, f"https://boards-api.greenhouse.io/v1/boards/{slug}")
    actual = str(metadata.get("name") or "")
    if actual and not source_discovery.identity_matches(name, actual):
        return source_result(
            "BROKEN", provider="greenhouse", job_count=0,
            reason=f"board identity mismatch: {actual}",
        )
    data = response_json(
        session, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false"
    )
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return source_result(
            "BROKEN", provider="greenhouse", job_count=0,
            reason="jobs payload is missing",
        )
    return source_result(
        "WORKING" if jobs else "NO_JOBS", provider="greenhouse", job_count=len(jobs),
        source={
            "name": name, "kind": "product", "wlb_score": 3,
            "ats": "greenhouse", "slug": slug, "enabled": True,
        },
        resolved_url=resolved_url or f"https://boards.greenhouse.io/{slug}",
    )


def probe_lever(
    session: requests.Session, name: str, slug: str, resolved_url: str = ""
) -> dict[str, Any]:
    jobs = response_json(session, f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if not isinstance(jobs, list):
        return source_result(
            "BROKEN", provider="lever", job_count=0, reason="jobs payload is not a list"
        )
    return source_result(
        "WORKING" if jobs else "NO_JOBS", provider="lever", job_count=len(jobs),
        source={
            "name": name, "kind": "product", "wlb_score": 3,
            "ats": "lever", "slug": slug, "enabled": True,
        } if jobs else None,
        resolved_url=resolved_url or f"https://jobs.lever.co/{slug}",
        reason="" if jobs else "official Lever namespace currently has no postings",
    )


def probe_ashby(
    session: requests.Session, name: str, slug: str, resolved_url: str = ""
) -> dict[str, Any]:
    data = response_json(
        session,
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
    )
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return source_result(
            "BROKEN", provider="ashby", job_count=0, reason="jobs payload is missing"
        )
    return source_result(
        "WORKING" if jobs else "NO_JOBS", provider="ashby", job_count=len(jobs),
        source={
            "name": name, "kind": "product", "wlb_score": 3,
            "ats": "ashby", "slug": slug, "enabled": True,
        },
        resolved_url=resolved_url or f"https://jobs.ashbyhq.com/{slug}",
    )


def workday_parts(url: str) -> tuple[str, str, str] | None:
    parsed = urlparse(url)
    if "myworkdayjobs.com" not in parsed.netloc.casefold():
        return None
    parts = [part for part in parsed.path.split("/") if part]
    while parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
        parts.pop(0)
    if not parts:
        return None
    return (
        f"{parsed.scheme or 'https'}://{parsed.netloc}",
        parsed.netloc.split(".", 1)[0],
        parts[0],
    )


def find_india_facet(value: Any) -> tuple[str, str] | None:
    found: list[tuple[str, str]] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            parameter = str(item.get("facetParameter") or "")
            for child in item.get("values") or []:
                if isinstance(child, dict):
                    if (
                        normalize(str(child.get("descriptor") or "")) == "india"
                        and parameter and child.get("id")
                    ):
                        found.append((parameter, str(child["id"])))
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return found[0] if found else None


def probe_workday(
    session: requests.Session, name: str, url: str
) -> dict[str, Any] | None:
    parts = workday_parts(url)
    if not parts:
        return None
    base, tenant, site = parts
    endpoint = f"{base}/wday/cxs/{tenant}/{site}/jobs"
    response = session.post(
        endpoint,
        json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""},
        headers={**HEADERS, "Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    raw_jobs = data.get("jobPostings") or []
    total = int(data.get("total") or len(raw_jobs))
    india = find_india_facet(data.get("facets") or [])
    ats = "workday_india" if india else "workday_search"
    return source_result(
        "WORKING" if total else "NO_JOBS", provider="workday", job_count=total,
        source={
            "name": name, "kind": "product", "wlb_score": 3, "ats": ats,
            "url": endpoint, "career_site_url": f"{base}/{site}",
            "max_results_per_term": 60, "enabled": True,
        },
        resolved_url=f"{base}/{site}",
        reason="" if india else "no India country facet; production must filter job locations",
    )

def oracle_parts(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if "oraclecloud.com" not in parsed.netloc.casefold():
        return None
    match = re.search(r"/sites/([^/]+)", parsed.path)
    if not match:
        return None
    return f"{parsed.scheme or 'https'}://{parsed.netloc}", match.group(1)


def probe_oracle(
    session: requests.Session, name: str, url: str
) -> dict[str, Any] | None:
    parts = oracle_parts(url)
    if not parts:
        return None
    base, site = parts
    endpoint = f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    response = session.get(
        endpoint,
        params={
            "onlyData": "true",
            "expand": "requisitionList.workLocation",
            "finder": f'findReqs;siteNumber={site},limit=24,offset=0,keyword="data"',
        },
        headers=HEADERS, timeout=TIMEOUT,
    )
    response.raise_for_status()
    jobs: list[dict[str, Any]] = []
    for container in response.json().get("items") or []:
        jobs.extend(container.get("requisitionList") or [])
    return source_result(
        "WORKING" if jobs else "NO_JOBS",
        provider="oracle_hcm", job_count=len(jobs),
        source={
            "name": name, "kind": "product", "wlb_score": 3,
            "ats": "oracle_hcm", "url": endpoint,
            "career_site_url": f"{base}/hcmUI/CandidateExperience/en/sites/{site}",
            "site_number": site, "max_results_per_term": 48, "enabled": True,
        },
        resolved_url=f"{base}/hcmUI/CandidateExperience/en/sites/{site}/jobs",
    )


def probe_phenom(
    session: requests.Session, name: str, url: str
) -> dict[str, Any] | None:
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    base = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    widget = base + "/widgets"
    response = session.post(
        widget,
        json={
            "lang": "en_global", "deviceType": "desktop", "country": "global",
            "pageName": "search-results", "ddoKey": "refineSearch", "from": 0,
            "jobs": True, "counts": True,
            "all_fields": ["category", "country", "state", "city"],
            "size": 20, "keywords": "data",
            "selected_fields": {"country": ["India"]},
        },
        headers={**HEADERS, "Referer": url}, timeout=TIMEOUT,
    )
    if response.status_code in (401, 403, 429):
        return None
    response.raise_for_status()
    container = response.json().get("refineSearch") or {}
    jobs = (container.get("data") or {}).get("jobs")
    if not isinstance(jobs, list):
        return None
    total = int(container.get("totalHits") or len(jobs))
    return source_result(
        "WORKING" if total else "NO_JOBS",
        provider="phenom", job_count=total,
        source={
            "name": name, "kind": "product", "wlb_score": 3, "ats": "phenom",
            "url": widget,
            "career_site_url": base + parsed.path.rsplit("/search-results", 1)[0],
            "enabled": True,
        },
        resolved_url=url,
    )


def probe_successfactors(
    session: requests.Session, name: str, url: str, html: str
) -> dict[str, Any] | None:
    marker = "successfactors" in html.casefold() or "jobs2web" in html.casefold()
    if not marker and not re.search(r"/(?:viewalljobs|search)/?$", urlparse(url).path):
        return None
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    search_url = base + "/search/"
    response = session.get(
        search_url,
        params={"q": "data", "locationsearch": "India", "startrow": 0},
        headers=HEADERS, timeout=TIMEOUT,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.select("tr.data-row")
    if not rows and "jobTitle-link" not in response.text:
        return None
    return source_result(
        "WORKING" if rows else "NO_JOBS",
        provider="successfactors", job_count=len(rows),
        source={
            "name": name, "kind": "product", "wlb_score": 3,
            "ats": "successfactors_search", "url": search_url,
            "career_site_url": base + "/", "enabled": True,
        },
        resolved_url=search_url,
    )


def probe_talentbrew(
    session: requests.Session, name: str, url: str, html: str
) -> dict[str, Any] | None:
    if "/search-jobs" not in urlparse(url).path and "data-job-id" not in html:
        return None
    response = session.get(
        url, params={"k": "data", "p": 1}, headers=HEADERS, timeout=TIMEOUT,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs = soup.select('a[data-job-id][href*="/job/"]')
    if not jobs and "data-job-id" not in response.text:
        return None
    return source_result(
        "WORKING" if jobs else "NO_JOBS",
        provider="talentbrew",
        job_count=len({str(job.get("href") or "") for job in jobs}),
        source={
            "name": name, "kind": "product", "wlb_score": 3,
            "ats": "talentbrew_html", "url": url,
            "career_site_url": url, "enabled": True,
        },
        resolved_url=url,
    )


def probe_kula(
    session: requests.Session, name: str, url: str
) -> dict[str, Any]:
    response = session.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    slug = next((part for part in urlparse(url).path.split("/") if part), "")
    soup = BeautifulSoup(response.text, "html.parser")
    links = {
        urljoin(url, str(link.get("href") or ""))
        for link in soup.select("a[href]")
        if re.fullmatch(rf"/?{re.escape(slug)}/\d+/?", str(link.get("href") or ""))
    }
    return source_result(
        "WORKING" if links else "NO_JOBS", provider="kula", job_count=len(links),
        source={
            "name": name, "kind": "product", "wlb_score": 3,
            "ats": "kula_html", "url": url, "career_site_url": url, "enabled": True,
        },
        resolved_url=url,
    )


def probe_paylocity(
    session: requests.Session, name: str, url: str
) -> dict[str, Any]:
    data = response_json(session, url)
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return source_result(
            "BROKEN", provider="paylocity", job_count=0, reason="jobs payload is missing"
        )
    return source_result(
        "WORKING" if jobs else "NO_JOBS",
        provider="paylocity", job_count=len(jobs),
        source={
            "name": name, "kind": "product", "wlb_score": 3,
            "ats": "paylocity_feed", "url": url,
            "career_site_url": "https://recruiting.paylocity.com/", "enabled": True,
        },
        resolved_url=url,
    )


def probe_cohesity(
    session: requests.Session, name: str, url: str
) -> dict[str, Any]:
    data = response_json(session, url)
    grouped = data.get("job_data") if isinstance(data, dict) else None
    if not isinstance(grouped, dict):
        return source_result(
            "BROKEN", provider="cohesity", job_count=0, reason="job_data payload is missing"
        )
    jobs = [
        job for values in grouped.values()
        for job in (values if isinstance(values, list) else [])
        if isinstance(job, dict)
    ]
    return source_result(
        "WORKING" if jobs else "NO_JOBS",
        provider="cohesity", job_count=len(jobs),
        source={
            "name": name, "kind": "product", "wlb_score": 3,
            "ats": "cohesity_feed", "url": url,
            "career_site_url": "https://www.cohesity.com/careers/open-positions/",
            "enabled": True,
        },
        resolved_url=url,
    )

def slug_from_provider_url(url: str, provider: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if provider == "greenhouse" and "boards-api.greenhouse.io" in parsed.netloc:
        if "boards" in parts:
            index = parts.index("boards")
            return parts[index + 1] if len(parts) > index + 1 else ""
    return parts[0] if parts else ""


def provider_from_url(url: str) -> str:
    host = urlparse(url).netloc.casefold()
    if "greenhouse.io" in host:
        return "greenhouse"
    if host in {"jobs.lever.co", "api.lever.co", "api.eu.lever.co"}:
        return "lever"
    if "ashbyhq.com" in host:
        return "ashby"
    if host == "careers.kula.ai":
        return "kula"
    if "myworkdayjobs.com" in host:
        return "workday"
    if "oraclecloud.com" in host and "/sites/" in urlparse(url).path:
        return "oracle"
    return ""


def run_provider(
    session: requests.Session, name: str, provider: str, url: str, slug: str = ""
) -> dict[str, Any] | None:
    if provider == "greenhouse":
        return probe_greenhouse(
            session, name, slug or slug_from_provider_url(url, provider), url
        )
    if provider == "lever":
        return probe_lever(
            session, name, slug or slug_from_provider_url(url, provider), url
        )
    if provider == "ashby":
        return probe_ashby(
            session, name, slug or slug_from_provider_url(url, provider), url
        )
    if provider == "workday":
        return probe_workday(session, name, url)
    if provider == "oracle":
        return probe_oracle(session, name, url)
    if provider == "kula":
        return probe_kula(session, name, url)
    if provider == "paylocity":
        return probe_paylocity(session, name, url)
    if provider == "cohesity":
        return probe_cohesity(session, name, url)
    return None


def supported_link_from_html(html: str, base_url: str) -> tuple[str, str] | None:
    soup = BeautifulSoup(html, "html.parser")
    candidates = [
        urljoin(base_url, str(node.get(attribute) or ""))
        for selector, attribute in (("iframe[src]", "src"), ("a[href]", "href"))
        for node in soup.select(selector)
    ]
    for candidate in candidates:
        provider = provider_from_url(candidate)
        if provider:
            return provider, candidate
    return None


def classify_company(record: dict[str, Any]) -> dict[str, Any]:
    name = str(record["name"])
    if record.get("declared_no_public_board"):
        return {
            **record,
            "status": "NO_PUBLIC_BOARD",
            "reason": "User supplied an explicit no-public-board result; no URL was guessed.",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    source_url = str(record["source_url"])
    result: dict[str, Any] = {
        **record, "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    session = requests.Session()
    known = KNOWN_RESOLUTIONS.get(name)
    if known:
        try:
            resolved = run_provider(
                session, name, known["provider"], known["resolved_url"],
                known.get("slug", ""),
            )
            if resolved:
                result.update(resolved)
                result["discovered_from_official_page"] = True
                return result
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            result["known_resolution_error"] = f"{type(exc).__name__}: {exc}"

    direct_provider = provider_from_url(source_url)
    if direct_provider:
        try:
            direct = run_provider(session, name, direct_provider, source_url)
            if direct:
                result.update(direct)
                return result
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            result.update({
                "status": "BLOCKED" if code in (401, 403, 429) else "BROKEN",
                "http_status": code,
                "reason": f"{direct_provider} endpoint returned HTTP {code}",
            })
            return result
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            result.update({
                "status": "BROKEN",
                "reason": f"{direct_provider} probe failed: {type(exc).__name__}: {exc}",
            })
            return result

    initial_status = 0
    redirect_target = ""
    try:
        initial = session.get(
            source_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False,
        )
        initial_status = initial.status_code
        if 300 <= initial.status_code < 400 and initial.headers.get("Location"):
            redirect_target = urljoin(source_url, initial.headers["Location"])
        response = session.get(
            redirect_target or source_url,
            headers=HEADERS, timeout=TIMEOUT, allow_redirects=True,
        )
        result["http_status"] = response.status_code
        result["final_url"] = response.url
        result["redirected"] = bool(
            redirect_target or response.url.rstrip("/") != source_url.rstrip("/")
        )
    except requests.RequestException as exc:
        result.update({
            "status": "BROKEN", "http_status": initial_status,
            "reason": f"request failed: {type(exc).__name__}: {exc}",
        })
        return result

    final_provider = provider_from_url(response.url)
    if final_provider:
        try:
            provider_result = run_provider(session, name, final_provider, response.url)
            if provider_result:
                result.update(provider_result)
                if result["redirected"]:
                    result["resolved_status"] = result["status"]
                    result["status"] = "REDIRECT"
                return result
        except (requests.RequestException, ValueError, TypeError, KeyError):
            pass

    if response.status_code in (401, 403, 429):
        if "/search-results" in urlparse(source_url).path:
            try:
                phenom = probe_phenom(session, name, source_url)
                if phenom:
                    result.update(phenom)
                    return result
            except (requests.RequestException, ValueError, TypeError, KeyError):
                pass
        result.update({
            "status": "BLOCKED",
            "reason": f"official page returned HTTP {response.status_code}",
        })
        return result
    if response.status_code >= 400:
        result.update({
            "status": "BROKEN",
            "reason": f"official page returned HTTP {response.status_code}",
        })
        return result

    html = response.text
    paylocity_match = re.search(
        r"https://recruiting\.paylocity\.com/recruiting/v2/api/feed/jobs/[a-f0-9-]+",
        html, re.IGNORECASE,
    )
    if paylocity_match:
        try:
            result.update(probe_paylocity(session, name, paylocity_match.group(0)))
            return result
        except (requests.RequestException, ValueError, TypeError, KeyError):
            pass

    supported_link = supported_link_from_html(html, response.url)
    if supported_link:
        provider, linked_url = supported_link
        try:
            linked = run_provider(session, name, provider, linked_url)
            if linked:
                result.update(linked)
                result["resolved_status"] = result["status"]
                result["status"] = "REDIRECT"
                return result
        except (requests.RequestException, ValueError, TypeError, KeyError):
            pass

    for probe in (probe_successfactors, probe_talentbrew):
        try:
            probed = probe(session, name, response.url, html)
            if probed:
                result.update(probed)
                if result["redirected"]:
                    result["resolved_status"] = result["status"]
                    result["status"] = "REDIRECT"
                return result
        except (requests.RequestException, ValueError, TypeError, KeyError):
            continue

    if (
        "/search-results" in urlparse(response.url).path
        or "phenompeople" in html.casefold()
    ):
        try:
            phenom = probe_phenom(session, name, response.url)
            if phenom:
                result.update(phenom)
                if result["redirected"]:
                    result["resolved_status"] = result["status"]
                    result["status"] = "REDIRECT"
                return result
        except (requests.RequestException, ValueError, TypeError, KeyError):
            pass

    soup = BeautifulSoup(html, "html.parser")
    job_postings = 0
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "")
        except (TypeError, json.JSONDecodeError):
            continue
        job_postings += json.dumps(payload).count('"JobPosting"')
    job_links = {
        urljoin(response.url, str(link.get("href") or ""))
        for link in soup.select("a[href]")
        if re.search(
            r"/(?:job|jobs|position|positions|opening|openings|career|careers)(?:/|$)",
            urlparse(urljoin(response.url, str(link.get("href") or ""))).path,
            re.IGNORECASE,
        )
    }
    page_text = clean_text(soup)
    no_jobs = bool(re.search(
        r"\b(?:no current openings|no open positions|no jobs found|0 jobs)\b",
        page_text, re.IGNORECASE,
    ))
    if no_jobs:
        result.update({
            "status": "NO_JOBS", "job_count": 0,
            "reason": "official page explicitly reports no current openings",
        })
    elif job_postings:
        result.update({
            "status": "DYNAMIC", "job_count": job_postings,
            "reason": "JobPosting records are visible but no stable supported list feed was proven",
        })
    elif job_links:
        result.update({
            "status": "DYNAMIC", "job_count": len(job_links),
            "reason": "official page exposes job-related links but needs a company-specific adapter",
        })
    else:
        result.update({
            "status": "DYNAMIC", "job_count": 0,
            "reason": "official page loads, but no stable machine-readable job list was proven",
        })
    if result["redirected"]:
        result["resolved_status"] = result["status"]
        result["status"] = "REDIRECT"
    return result

def validate_batch(
    batch_index: int, batch_size: int, workers: int
) -> dict[str, Any]:
    all_records = read_mappings()
    records = all_records[batch_index * batch_size:(batch_index + 1) * batch_size]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(classify_company, record): record["name"] for record in records}
        for future in as_completed(futures):
            name = futures[future]
            try:
                item = future.result()
            except Exception as exc:
                item = {
                    "name": name, "status": "BROKEN",
                    "reason": f"unexpected validator error: {type(exc).__name__}: {exc}",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
            print(
                f"{item['status']}: {name}"
                f" ({item.get('provider', 'page')}, jobs={item.get('job_count', 0)})",
                flush=True,
            )
            results.append(item)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_index": batch_index, "batch_size": batch_size,
        "total_mappings": len(all_records),
        "results": sorted(results, key=lambda item: item["name"].casefold()),
    }


def merge_results(
    input_dir: Path, output: Path, expected_parts: int | None
) -> dict[str, Any]:
    paths = sorted(input_dir.rglob("part-*.json"))
    parts = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    if expected_parts is not None:
        indexes = {int(part["batch_index"]) for part in parts}
        missing = sorted(set(range(expected_parts)) - indexes)
        if missing:
            raise RuntimeError(f"Refusing partial merge; missing batch artifacts: {missing}")
    results = sorted(
        [item for part in parts for item in part.get("results", [])],
        key=lambda item: str(item["name"]).casefold(),
    )
    expected_names = {item["name"].casefold() for item in read_mappings()}
    actual_names = {str(item["name"]).casefold() for item in results}
    if expected_names != actual_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise RuntimeError(f"Mapping coverage mismatch; missing={missing}, extra={extra}")

    counts: dict[str, int] = {}
    promotable: list[dict[str, Any]] = []
    for item in results:
        status = str(item.get("status") or "BROKEN")
        counts[status] = counts.get(status, 0) + 1
        resolved_status = str(item.get("resolved_status") or status)
        source = item.get("source")
        if (
            isinstance(source, dict)
            and source.get("ats") in SUPPORTED_ATS
            and resolved_status in {"WORKING", "NO_JOBS"}
        ):
            promotable.append(source)

    document = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_mappings": len(results), "status_counts": counts,
            "promotable_sources": len(promotable),
            "note": "Runtime classification of user-supplied official URLs; generic pages are never auto-enabled.",
        },
        "companies": results,
    }
    output.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8",
    )
    promotable_path = output.with_name("career_source_promotable.yaml")
    promotable_path.write_text(
        yaml.safe_dump(
            {
                "metadata": {
                    "generated_at": document["metadata"]["generated_at"],
                    "verified_sources": len(promotable),
                    "note": "Parser-supported sources only; promotion still requires identity and duplicate review.",
                },
                "companies": promotable,
            },
            sort_keys=False, allow_unicode=True,
        ),
        encoding="utf-8",
    )
    summary = {
        "total_mappings": len(results), "status_counts": counts,
        "promotable_sources": len(promotable),
        "non_working": [
            {
                "name": item["name"], "status": item["status"],
                "resolved_status": item.get("resolved_status"),
                "reason": item.get("reason", ""),
            }
            for item in results
            if item.get("status") not in {"WORKING", "NO_JOBS"}
        ],
    }
    output.with_suffix(".summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    print(json.dumps(summary["status_counts"], sort_keys=True))
    print(f"Promotable parser-supported sources: {len(promotable)}")
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-index", type=int)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--merge-dir", type=Path)
    parser.add_argument("--expected-parts", type=int)
    args = parser.parse_args()
    if args.merge_dir:
        merge_results(args.merge_dir, args.output, args.expected_parts)
        return 0
    if args.batch_index is None:
        parser.error("--batch-index is required unless --merge-dir is used")
    result = validate_batch(args.batch_index, args.batch_size, args.workers)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())