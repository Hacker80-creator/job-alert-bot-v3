"""Discord Job Alert Bot for Bangalore Data Science / Analytics roles.

Primary source: official career feeds / ATS APIs.
Secondary source: Indeed best-effort search, filtered by an approved product-company allowlist.

The bot is designed for GitHub Actions every 30 minutes.
"""
from __future__ import annotations

import ast
import hashlib
import html
import json
import os
import re
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import requests
import yaml
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "companies.yaml"
STATE_FILE = ROOT / "state" / "seen_jobs.json"
HEALTH_FILE = ROOT / "state" / "scan_health.json"
SCAN_ERRORS: list[str] = []

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
MIN_SCORE = int(os.getenv("MIN_SCORE", "70"))
MAX_ALERTS_PER_RUN = int(os.getenv("MAX_ALERTS_PER_RUN", "15"))
SEND_STARTUP_SUMMARY = os.getenv("SEND_STARTUP_SUMMARY", "false").lower() == "true"
SEND_DAILY_HEALTH = os.getenv("SEND_DAILY_HEALTH", "true").lower() == "true"
DAILY_HEALTH_HOURS = int(os.getenv("DAILY_HEALTH_HOURS", "24"))
ENABLE_INDEED = os.getenv("ENABLE_INDEED", "true").lower() == "true"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SuriJobAlertBot/3.0; +https://github.com/)",
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def canonical_job_url(url: str) -> str:
    """Normalize a job-specific public URL for cross-run deduplication."""
    try:
        parsed = urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""

    path = re.sub(r"/+", "/", parsed.path or "/")
    path = re.sub(r"/(?:en[-_][a-z]{2})(?=/)", "", path, flags=re.IGNORECASE)
    path = re.sub(r"/apply(?=/|$)", "", path, flags=re.IGNORECASE)
    path = path.rstrip("/") or "/"
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_key = key.casefold()
        if normalized_key.startswith("utm_") or normalized_key in {
            "domain", "source", "src", "ref", "referrer", "gh_src", "tracking",
            "q", "query", "keyword", "keywords", "location", "page", "lang", "hl",
            "lastselectedfacet", "selectedcategoriesfacet", "track_view",
        }:
            continue
        query_items.append((key, value))

    query_names = {key.casefold() for key, _ in query_items}
    job_marker = bool(re.search(
        r"/(?:job|jobs|position|positions|posting|postings|requisition|"
        r"requisitions|opening|openings)/[^/]+",
        path,
        re.IGNORECASE,
    ))
    identifier = bool(
        re.search(r"[0-9a-f]{8}-[0-9a-f-]{20,}|\d{4,}|_[a-z]{0,3}\d{4,}", path, re.IGNORECASE)
        or query_names.intersection({"id", "jobid", "job_id", "position_id", "opportunityid", "gh_jid"})
    )
    if not (job_marker or identifier):
        return ""

    normalized = urlunsplit((
        parsed.scheme.casefold(),
        parsed.netloc.casefold(),
        path,
        urlencode(sorted(query_items)),
        "",
    ))
    return normalized.casefold()


def is_public_job_url(url: str) -> bool:
    """Return false for malformed links and known machine-only ATS endpoints."""
    try:
        parsed = urlsplit(str(url or "").strip())
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    host = parsed.netloc.casefold().split(":", 1)[0]
    path = parsed.path.casefold()
    if host in {
        "api.smartrecruiters.com",
        "api.lever.co",
        "boards-api.greenhouse.io",
    }:
        return False
    if any(marker in path for marker in (
        "/wday/cxs/",
        "/hcmrestapi/",
        "/posting-api/job-board/",
        "/recruiting/v2/api/feed/",
    )):
        return False
    return True

def make_url_fingerprint(url: str) -> str:
    canonical = canonical_job_url(url)
    if not canonical:
        return ""
    return hashlib.sha256(f"url|{canonical}".encode("utf-8")).hexdigest()[:24]


def make_dedupe_keys(company: str, title: str, location: str, url: str = "") -> set[str]:
    """Prefer a job-specific URL; use semantic identity only as a fallback."""
    url_key = make_url_fingerprint(url)
    if url_key:
        return {url_key}
    return {make_fingerprint(company, title, location)}


def make_fingerprint(company: str, title: str, location: str) -> str:
    """Create a stable key that ignores URL and harmless punctuation changes."""
    parts = []
    for value in (company, title, location):
        normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
        parts.append(normalized)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


@dataclass
class Job:
    company: str
    title: str
    location: str
    url: str
    source: str
    description: str = ""
    department: str = ""
    salary_text: str = ""
    wlb_score: int = 3
    score: int = 0
    reasons: list[str] | None = None

    @property
    def fingerprint(self) -> str:
        return make_fingerprint(self.company, self.title, self.location)

    @property
    def dedupe_keys(self) -> set[str]:
        return make_dedupe_keys(self.company, self.title, self.location, self.url)

    @property
    def state_key(self) -> str:
        """Use a requisition-specific key so equal titles do not overwrite."""
        return make_url_fingerprint(self.url) or self.fingerprint

def load_config() -> dict[str, Any]:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            stored = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return stored if isinstance(stored, dict) else {}
        except Exception:
            return {}
    return {}


def state_dedupe_keys(seen: dict[str, Any]) -> set[str]:
    """Build semantic and canonical-URL keys from persisted alert records."""
    keys = set(seen)
    for record in seen.values():
        if not isinstance(record, dict):
            continue
        if not all(record.get(key) for key in ("company", "title", "location")):
            continue
        keys.update(make_dedupe_keys(
            str(record["company"]),
            str(record["title"]),
            str(record["location"]),
            str(record.get("url") or ""),
        ))
    return keys


def save_seen(seen: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(seen, indent=2, sort_keys=True), encoding="utf-8")


def clean_text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        value = " ".join(map(str, value))
    raw = str(value)
    text = BeautifulSoup(raw, "html.parser").get_text(" ") if "<" in raw and ">" in raw else raw
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def get_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    for attempt in range(3):
        try:
            if method == "POST":
                response = requests.post(
                    url, json=payload or {}, headers=HEADERS, timeout=20
                )
            else:
                response = requests.get(url, headers=HEADERS, timeout=20)
        except (requests.Timeout, requests.ConnectionError):
            if attempt >= 2:
                raise
            time.sleep(1 + attempt * 2)
            continue

        # Workday search POSTs occasionally return short-lived 429/5xx
        # responses. Retry the bounded list query, but do not retry GET detail
        # enrichment and amplify a tenant's rate limit.
        retryable = method == "POST" and response.status_code in {429, 502, 503}
        if retryable and attempt < 2:
            time.sleep(1 + attempt * 2)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("unreachable JSON retry state")


def get_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def flatten_location(value: Any) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        embedded = re.match(r"^(.*?)(\{.*\}|\[.*\])$", candidate, re.DOTALL)
        prefix = clean_text(embedded.group(1)) if embedded else ""
        structured = embedded.group(2) if embedded else candidate
        if structured and structured[0] in "[{" and structured[-1] in "]}":
            for loader in (json.loads, ast.literal_eval):
                try:
                    parsed = loader(structured)
                except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
                    continue
                if isinstance(parsed, (dict, list)):
                    # Workday sometimes appends a serialized country object to
                    # an already complete location. Keep the readable prefix
                    # because the metadata is redundant.
                    return flatten_location(prefix) if prefix else flatten_location(parsed)
        # Deduplicate repeated Workday locations joined with semicolons.
        parts: list[str] = []
        seen_parts: set[str] = set()
        for item in candidate.split(";"):
            part = clean_text(item)
            normalized = normalize_match_text(part)
            if part and normalized not in seen_parts:
                parts.append(part)
                seen_parts.add(normalized)
        return "; ".join(parts)
    if isinstance(value, dict):
        values = [value.get(k) for k in (
            "name", "descriptor", "city", "addressLocality", "region", "addressRegion",
            "country", "addressCountry", "alpha2Code", "location", "fullLocation",
            "formattedLocation",
        )]
        parts: list[str] = []
        seen_parts: set[str] = set()
        for item in values:
            part = flatten_location(item) if item is not None else ""
            normalized = normalize_match_text(part)
            if part and normalized not in seen_parts:
                parts.append(part)
                seen_parts.add(normalized)
        return clean_text(" ".join(parts))
    if isinstance(value, list):
        unique: list[str] = []
        normalized_parts: list[str] = []
        country_tokens = {"india", "in", "ind"}
        for item in value:
            part = flatten_location(item)
            normalized = normalize_match_text(part)
            if not part:
                continue
            skip = False
            replace_index: int | None = None
            for index, existing in enumerate(normalized_parts):
                if normalized == existing:
                    skip = True
                    break
                if normalized.startswith(existing + " "):
                    suffix = normalized[len(existing):].strip().split()
                    if suffix and set(suffix) <= country_tokens:
                        skip = True
                        break
                if existing.startswith(normalized + " "):
                    suffix = existing[len(normalized):].strip().split()
                    if suffix and set(suffix) <= country_tokens:
                        replace_index = index
                        break
            if replace_index is not None:
                unique[replace_index] = part
                normalized_parts[replace_index] = normalized
            elif not skip:
                unique.append(part)
                normalized_parts.append(normalized)
        return clean_text("; ".join(unique))
    return clean_text(value)

def normalize_match_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def is_target_title(title: str) -> bool:
    target_terms = (
        "data scientist", "machine learning engineer", "ml engineer", "applied scientist",
        "decision scientist", "data analyst", "product analyst", "business analyst",
        "analytics engineer", "business intelligence", "bi analyst", "insights analyst",
        "ai engineer", "nlp engineer", "mlops engineer",
    )
    return any(term in title.casefold() for term in target_terms)


def has_location_match(location: str, settings: dict[str, Any]) -> bool:
    """Accept Bangalore/Karnataka or a role explicitly marked remote in India."""
    normalized = normalize_match_text(location)
    if not normalized:
        return False

    tokens = set(normalized.split())
    if "remote" in tokens and ("india" in tokens or "ind" in tokens):
        return True
    if "blr" in tokens and ("india" in tokens or "ind" in tokens):
        return True

    padded = f" {normalized} "
    for term in settings["location_terms"]:
        needle = normalize_match_text(term)
        if needle and f" {needle} " in padded:
            return True
    return False


def reject_by_seniority(title: str, body: str, settings: dict[str, Any]) -> tuple[bool, str]:
    text = f"{title} {body}".lower()
    title_l = title.lower()
    if re.search(r"\b(?:avp|svp|vp)\b", title_l):
        return True, "blocked seniority abbreviation"
    for term in settings["blocked_title_terms"]:
        if term in title_l:
            return True, f"blocked title term: {term}"
    for pat in settings["experience_reject_patterns"]:
        if pat in text:
            return True, f"too much experience: {pat}"
    # Catch common 4-10 year patterns.
    m = re.search(r"\b([4-9]|1[0-5])\s*\+?\s*(?:years|yrs)\b", text)
    if m:
        return True, f"experience appears too high: {m.group(0)}"
    return False, ""


def score_job(job: Job, settings: dict[str, Any]) -> tuple[int, list[str]]:
    text = f"{job.title} {job.department} {job.location} {job.description}".lower()
    title_l = job.title.lower()
    reasons: list[str] = []
    score = 0

    if has_location_match(job.location, settings):
        score += 25
        reasons.append("Bangalore/Bengaluru or Remote India")
    else:
        reasons.append("location not clearly Bangalore/Remote India")
        return 0, reasons

    matched_title = next((term for term in settings["strong_title_terms"] if term in title_l), None)
    if not matched_title:
        return 0, ["title does not match a target data/AI/analytics role"]
    # A precise target title plus an approved location is sufficient even
    # when an ATS list endpoint does not include the full job description.
    score += 45
    reasons.append(f"role title: {matched_title}")

    matched_skills = [s for s in settings["skill_terms"] if s in text]
    if matched_skills:
        score += min(30, len(matched_skills) * 5)
        reasons.append("skills: " + ", ".join(matched_skills[:6]))

    if any(word in text for word in ["data science", "analytics", "machine learning", "business intelligence", "applied science", "experimentation"]):
        score += 10
        reasons.append("data/analytics context")

    if any(word in text for word in ["entry level", "new grad", "associate", "0-2", "0 to 2", "0-3", "0 to 3", "1-3", "1 to 3", "early career"]):
        score += 10
        reasons.append("early-career signal")

    if job.wlb_score >= 4:
        score += 5
        reasons.append("higher WLB priority company")

    rejected, why = reject_by_seniority(job.title, job.description, settings)
    if rejected:
        return 0, [why]

    return min(score, 100), reasons


def parse_greenhouse(company: dict[str, Any]) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company['slug']}/jobs?content=true"
    data = get_json(url)
    jobs = []
    for item in data.get("jobs", []):
        location = flatten_location(item.get("location"))
        jobs.append(Job(
            company=company["name"],
            title=clean_text(item.get("title")),
            location=location,
            url=item.get("absolute_url", ""),
            source="Official careers: Greenhouse",
            description=clean_text(item.get("content")),
            department=flatten_location(item.get("departments")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_lever(company: dict[str, Any]) -> list[Job]:
    url = f"https://api.lever.co/v0/postings/{company['slug']}?mode=json"
    data = get_json(url)
    jobs = []
    for item in data:
        categories = item.get("categories", {}) or {}
        location = flatten_location(categories.get("location"))
        description = " ".join([
            clean_text(item.get("description")),
            clean_text(item.get("descriptionPlain")),
            clean_text(item.get("lists")),
        ])
        jobs.append(Job(
            company=company["name"],
            title=clean_text(item.get("text")),
            location=location,
            url=item.get("hostedUrl") or item.get("applyUrl") or "",
            source="Official careers: Lever",
            description=description,
            department=clean_text(categories.get("department")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_ashby(company: dict[str, Any]) -> list[Job]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company['slug']}?includeCompensation=true"
    data = get_json(url)
    raw_jobs = data.get("jobs", data if isinstance(data, list) else [])
    jobs = []
    for item in raw_jobs:
        location = flatten_location(item.get("location") or item.get("locationName"))
        jobs.append(Job(
            company=company["name"],
            title=clean_text(item.get("title")),
            location=location,
            url=item.get("jobUrl") or item.get("applyUrl") or item.get("url") or "",
            source="Official careers: Ashby",
            description=clean_text(item.get("descriptionHtml") or item.get("descriptionPlain") or item.get("description")),
            department=clean_text(item.get("department")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_smartrecruiters(company: dict[str, Any]) -> list[Job]:
    search_terms = company.get("search_terms") or [""]
    if isinstance(search_terms, str):
        search_terms = [search_terms]

    target_titles = (
        "data scientist", "machine learning engineer", "ml engineer", "applied scientist",
        "decision scientist", "data analyst", "product analyst", "business analyst",
        "analytics engineer", "business intelligence", "bi analyst", "insights analyst",
        "ai engineer", "nlp engineer", "mlops engineer",
    )
    settings = load_config()["settings"]
    jobs: list[Job] = []
    seen_ids: set[str] = set()
    for search_text in search_terms:
        url = f"https://api.smartrecruiters.com/v1/companies/{company['slug']}/postings?limit=100"
        if search_text:
            url += f"&q={quote_plus(search_text)}"
        data = get_json(url)
        for item in data.get("content", []):
            item_id = str(item.get("id") or item.get("ref") or "")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            title = clean_text(item.get("name"))
            location = flatten_location(item.get("location"))
            detail = ""
            public_url = item.get("ref", "")
            # Details are needed for the 0-3 year filter, but only target titles
            # can become alerts. This avoids hundreds of needless API requests.
            if any(term in title.casefold() for term in target_titles) and has_location_match(location, settings):
                detail_url = item.get("ref")
                if detail_url:
                    try:
                        detail_json = get_json(detail_url)
                        detail = clean_text(detail_json.get("jobAd", {}).get("sections", {}))
                        public_url = detail_json.get("postingUrl") or detail_json.get("applyUrl") or public_url
                    except Exception:
                        pass
            jobs.append(Job(
                company=company["name"],
                title=title,
                location=location,
                url=public_url,
                source="Official careers: SmartRecruiters",
                description=detail,
                department=clean_text(item.get("department")),
                wlb_score=company.get("wlb_score", 3),
            ))
    return jobs


def parse_zwayam(company: dict[str, Any]) -> list[Job]:
    """Read public Zwayam career portals such as careers.tavant.com."""
    jobs: list[Job] = []
    page_size = 10
    max_results = max(page_size, int(company.get("max_results", 100)))
    portal_url = company["career_site_url"].rstrip("/")
    request_headers = {
        **HEADERS,
        "Origin": f"https://{company['domain']}",
        "Referer": f"{portal_url}/",
    }

    for offset in range(0, max_results, page_size):
        filter_criteria = {
            "paginationStartNo": offset,
            "selectedCall": "sort",
            "sortCriteria": {"name": "modifiedDate", "isAscending": False},
            "anyOfTheseWords": "",
        }
        for attempt in range(2):
            try:
                response = requests.post(
                    company["url"],
                    data={
                        "filterCri": json.dumps(filter_criteria),
                        "domain": company["domain"],
                        "companyId": company["company_id"],
                    },
                    headers=request_headers,
                    timeout=(8, 15),
                )
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                if attempt == 1:
                    if jobs:
                        print(f"WARN {company['name']} returned partial Zwayam results: {exc}")
                        SCAN_ERRORS.append(f"{company['name']} (partial feed)")
                        return jobs
                    raise
                time.sleep(1)
        envelope = response.json()
        data = envelope.get("data") or {}
        raw_jobs = data.get("data") or []

        for item in raw_jobs:
            source = item.get("_source") or item
            slug = clean_text(source.get("jobUrl"))
            salary_parts = [source.get("minJobSalary"), source.get("maxJobSalary")]
            if all(str(value or "").strip() for value in salary_parts):
                salary_text = f"INR {salary_parts[0]}-{salary_parts[1]} per annum"
            else:
                salary_text = ""
            description = " ".join(filter(None, [
                clean_text(source.get("mediumDescription")),
                clean_text(source.get("role")),
                clean_text(source.get("jdSkillsKnown")),
                clean_text(source.get("experienceUIField") or source.get("yrsOfExperience")),
            ]))
            jobs.append(Job(
                company=company["name"],
                title=clean_text(source.get("jobTitle")),
                location=flatten_location(source.get("locationSeparatedbySlash") or source.get("jobLocationRecord") or source.get("location")),
                url=f"{portal_url}/job/{slug}" if slug else portal_url,
                source="Official careers: Zwayam",
                description=description,
                department=clean_text(source.get("text1") or source.get("departmentName")),
                salary_text=salary_text,
                wlb_score=company.get("wlb_score", 3),
            ))

        if not raw_jobs or not data.get("hasMoreData"):
            break
        time.sleep(0.1)
    return jobs

def parse_amazon(company: dict[str, Any]) -> list[Job]:
    url = "https://www.amazon.jobs/en/search.json?base_query=data&loc_query=Bangalore%2C%20India&country=IND&offset=0&result_limit=100&sort=relevant"
    data = get_json(url)
    jobs = []
    for item in data.get("jobs", []):
        jobs.append(Job(
            company=company["name"],
            title=clean_text(item.get("title")),
            location=clean_text(item.get("normalized_location") or item.get("location")),
            url="https://www.amazon.jobs" + item.get("job_path", ""),
            source="Official careers: Amazon Jobs",
            description=clean_text(item.get("description") or item.get("basic_qualifications")),
            department=clean_text(item.get("business_category")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_ms_search(company: dict[str, Any]) -> list[Job]:
    # Microsoft site is heavily dynamic; this endpoint is a best-effort public search route.
    url = "https://gcsservices.careers.microsoft.com/search/api/v1/search?lc=India&l=en_us&pg=1&pgSz=100&q=data%20scientist&flt=true"
    data = get_json(url)
    raw_jobs = data.get("operationResult", {}).get("result", {}).get("jobs", []) or data.get("jobs", [])
    jobs = []
    for item in raw_jobs:
        location = flatten_location(item.get("locations") or item.get("location"))
        job_id = item.get("jobId") or item.get("id") or ""
        jobs.append(Job(
            company=company["name"],
            title=clean_text(item.get("title")),
            location=location,
            url=f"https://jobs.careers.microsoft.com/global/en/job/{job_id}" if job_id else "https://jobs.careers.microsoft.com/",
            source="Official careers: Microsoft",
            description=clean_text(item.get("description")),
            department=clean_text(item.get("discipline")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_workday_search(company: dict[str, Any]) -> list[Job]:
    # Workday CXS accepts pages of at most 20 jobs on the verified tenants.
    # Query a small set of role families and deduplicate results across queries.
    search_terms = company.get("search_terms") or ["data", "machine learning", "AI", "analytics"]
    if isinstance(search_terms, str):
        search_terms = [search_terms]

    page_size = 20
    max_results_per_term = max(20, int(company.get("max_results_per_term", 40)))
    career_site_url = company.get("career_site_url") or company["url"].split("/wday/")[0]
    jobs: list[Job] = []
    seen_keys: set[str] = set()

    for search_text in search_terms:
        for offset in range(0, max_results_per_term, page_size):
            payload = {
                "appliedFacets": {},
                "limit": page_size,
                "offset": offset,
                "searchText": search_text,
            }
            try:
                data = get_json(company["url"], method="POST", payload=payload)
            except Exception as exc:
                print(f"WARN {company['name']} Workday query {search_text!r} failed: {exc}")
                break

            raw_jobs = data.get("jobPostings", []) or data.get("jobs", [])
            if not raw_jobs:
                break

            for item in raw_jobs:
                title = clean_text(item.get("title"))
                location = flatten_location(item.get("locationsText") or item.get("location"))
                external_path = item.get("externalPath") or item.get("url") or ""
                dedupe_key = external_path or f"{title}|{location}".casefold()
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)

                if external_path.startswith("/"):
                    url = career_site_url.rstrip("/") + external_path
                else:
                    url = external_path or career_site_url

                jobs.append(Job(
                    company=company["name"],
                    title=title,
                    location=location,
                    url=url,
                    source="Official careers: Workday",
                    description=clean_text(item.get("bulletFields") or item.get("jobDescription")),
                    department=clean_text(item.get("jobFamily")),
                    wlb_score=company.get("wlb_score", 3),
                ))

            try:
                total = int(data.get("total") or 0)
            except (TypeError, ValueError):
                total = 0
            if len(raw_jobs) < page_size or (total and offset + len(raw_jobs) >= total):
                break
            time.sleep(0.1)

    return jobs


def parse_oracle_hcm(company: dict[str, Any]) -> list[Job]:
    """Search a public Oracle Recruiting Candidate Experience site."""
    terms = company.get("search_terms") or ["data scientist", "machine learning", "data analyst", "analytics"]
    page_size = 24
    max_results = max(page_size, int(company.get("max_results_per_term", 48)))
    site_number = str(company["site_number"])
    career_url = company["career_site_url"].rstrip("/")
    detail_url = company["url"].replace("recruitingCEJobRequisitions", "recruitingCEJobRequisitionDetails")
    settings = load_config()["settings"]
    jobs: list[Job] = []
    seen_ids: set[str] = set()
    for term in terms:
        for offset in range(0, max_results, page_size):
            parts = [f"siteNumber={site_number}", f"limit={page_size}", f"offset={offset}", f'keyword="{term}"']
            if company.get("location_facet"):
                parts.append(f"selectedLocationsFacet={company['location_facet']}")
            response = requests.get(
                company["url"],
                params={
                    "onlyData": "true",
                    "expand": "requisitionList.workLocation,requisitionList.otherWorkLocations,requisitionList.secondaryLocations",
                    "finder": "findReqs;" + ",".join(parts),
                },
                headers=HEADERS, timeout=20,
            )
            response.raise_for_status()
            raw_jobs: list[dict[str, Any]] = []
            for container in response.json().get("items", []):
                raw_jobs.extend(container.get("requisitionList") or [])
            if not raw_jobs:
                break
            for item in raw_jobs:
                job_id = str(item.get("Id") or item.get("id") or "")
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                title = clean_text(item.get("Title") or item.get("title"))
                location = flatten_location([value for value in (
                    item.get("PrimaryLocation"), item.get("workLocation"),
                    item.get("otherWorkLocations"), item.get("secondaryLocations"),
                ) if value])
                description = clean_text(item.get("ShortDescriptionStr") or item.get("ShortDescription") or item.get("ExternalDescriptionStr"))
                if is_target_title(title) and has_location_match(location, settings):
                    try:
                        detail = requests.get(
                            detail_url,
                            params={"expand": "all", "onlyData": "true", "finder": f'ById;Id="{job_id}",siteNumber={site_number}'},
                            headers=HEADERS, timeout=20,
                        )
                        detail.raise_for_status()
                        detail_items = detail.json().get("items") or []
                        if detail_items:
                            info = detail_items[0]
                            if isinstance(info.get("requisitionList"), list) and info["requisitionList"]:
                                info = info["requisitionList"][0]
                            description = clean_text(info.get("ExternalDescriptionStr") or info.get("JobDescription") or info.get("Description") or info) or description
                    except Exception as exc:
                        print(f"WARN {company['name']} Oracle detail failed: {exc}")
                jobs.append(Job(
                    company=company["name"], title=title, location=location,
                    url=f"{career_url}/job/{job_id}", source="Official careers: Oracle Recruiting",
                    description=description, department=clean_text(item.get("JobFunction") or item.get("Category")),
                    wlb_score=company.get("wlb_score", 3),
                ))
            if len(raw_jobs) < page_size:
                break
            time.sleep(0.1)
    return jobs


def parse_eightfold(company: dict[str, Any]) -> list[Job]:
    """Search an official Eightfold career site for Bengaluru and Remote India."""
    terms = company.get("search_terms") or ["data scientist", "machine learning", "data analyst", "analytics"]
    locations = company.get("search_locations") or ["Bengaluru, Karnataka, India", "Remote, India"]
    max_results = max(10, int(company.get("max_results_per_search", 30)))
    domain = company["domain"]
    career_url = company["career_site_url"].rstrip("/")
    detail_url = company["url"].rsplit("/", 1)[0] + "/position_details"
    settings = load_config()["settings"]
    jobs: list[Job] = []
    seen_ids: set[str] = set()
    for term in terms:
        for search_location in locations:
            for offset in range(0, max_results, 10):
                response = requests.get(
                    company["url"],
                    params={"domain": domain, "query": term, "location": search_location, "start": offset},
                    headers=HEADERS, timeout=20,
                )
                response.raise_for_status()
                data = response.json().get("data") or {}
                raw_jobs = data.get("positions") or []
                if not raw_jobs:
                    break
                for item in raw_jobs:
                    job_id = str(item.get("id") or "")
                    if not job_id or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    title = clean_text(item.get("name") or item.get("title"))
                    location = flatten_location(item.get("locations") or item.get("location"))
                    description = clean_text(item.get("jobDescription") or item.get("description"))
                    department = clean_text(item.get("department") or item.get("jobFunction"))
                    if is_target_title(title) and has_location_match(location, settings):
                        try:
                            detail = requests.get(
                                detail_url, params={"position_id": job_id, "domain": domain, "hl": "en"},
                                headers=HEADERS, timeout=20,
                            )
                            detail.raise_for_status()
                            info = detail.json().get("data") or {}
                            if isinstance(info.get("data"), dict):
                                info = info["data"]
                            description = clean_text(info.get("jobDescription") or info.get("description")) or description
                            department = clean_text(info.get("department")) or department
                        except Exception as exc:
                            print(f"WARN {company['name']} Eightfold detail failed: {exc}")
                    jobs.append(Job(
                        company=company["name"], title=title, location=location,
                        url=f"{career_url}/job/{job_id}?domain={domain}", source="Official careers: Eightfold",
                        description=description, department=department, wlb_score=company.get("wlb_score", 3),
                    ))
                total = int(data.get("count") or 0)
                if len(raw_jobs) < 10 or (total and offset + len(raw_jobs) >= total):
                    break
                time.sleep(0.1)
    return jobs


def parse_html_search(company: dict[str, Any]) -> list[Job]:
    # Conservative fallback. Only use text from the link's nearest compact card;
    # whole-page text can attach an unrelated location to a blog or navigation link.
    page = get_html(company["url"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
        soup = BeautifulSoup(page, "html.parser")
    results: list[Job] = []
    for a in soup.find_all("a", href=True):
        title = clean_text(a.get_text(" "))
        if not title or len(title) > 140:
            continue
        title_l = title.lower()
        if not any(term in title_l for term in ["data", "analytics", "scientist", "machine learning", "analyst", "business intelligence", "ai ", "ml "]):
            continue
        href = a["href"]
        href_l = href.lower()
        if not any(marker in href_l for marker in ("job", "career", "position", "opening", "requisition")):
            continue

        context = title
        for parent in a.parents:
            if parent is soup:
                break
            if getattr(parent, "name", "") not in {"article", "li", "tr", "div", "section"}:
                continue
            candidate = clean_text(parent.get_text(" "))
            if len(candidate) > 2000:
                break
            if len(candidate) > len(title) + 3:
                context = candidate
                break

        if href.startswith("/"):
            base_match = re.match(r"https?://[^/]+", company["url"])
            href = (base_match.group(0) if base_match else "") + href
        results.append(Job(
            company=company["name"],
            title=title,
            location=context[:500],
            url=href if href.startswith("http") else company["url"],
            source="Official careers: HTML fallback",
            description=context[:2000],
            department="",
            wlb_score=company.get("wlb_score", 3),
        ))
    return results


def fetch_company_jobs(company: dict[str, Any]) -> list[Job]:
    if not company.get("enabled", True):
        return []
    ats = company.get("ats")
    parsers = {
        "greenhouse": parse_greenhouse,
        "lever": parse_lever,
        "ashby": parse_ashby,
        "smartrecruiters": parse_smartrecruiters,
        "zwayam": parse_zwayam,
        "amazon": parse_amazon,
        "ms_search": parse_ms_search,
        "workday_search": parse_workday_search,
        "oracle_hcm": parse_oracle_hcm,
        "eightfold": parse_eightfold,
        "html_search": parse_html_search,
    }
    parser = parsers.get(ats)
    if not parser:
        print(f"WARN unsupported ATS for {company['name']}: {ats}")
        SCAN_ERRORS.append(f"{company['name']} (unsupported source)")
        return []
    try:
        jobs = parser(company)
        print(f"{company['name']}: {len(jobs)} raw jobs from {ats}")
        return jobs
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        SCAN_ERRORS.append(company["name"])
        return []


def approved_company_names(config: dict[str, Any]) -> list[str]:
    names = {c["name"] for c in config["companies"] if c.get("enabled", True)}
    allowlist_name = config.get("external_job_boards", {}).get("company_allowlist_file")
    if allowlist_name:
        try:
            for line in (ROOT / allowlist_name).read_text(encoding="utf-8").splitlines():
                name = line.strip()
                if name and not name.startswith("#"):
                    names.add(name)
        except Exception as exc:
            print(f"WARN secondary company allowlist failed: {exc}")
    return sorted(names)


def scrape_indeed_best_effort(config: dict[str, Any]) -> list[Job]:
    if not ENABLE_INDEED:
        return []
    names = approved_company_names(config)
    terms = ["data scientist", "data analyst", "machine learning engineer", "analytics engineer", "business analyst", "applied scientist"]
    jobs: list[Job] = []
    for term in terms:
        url = f"https://in.indeed.com/jobs?q={quote_plus(term)}&l=Bengaluru%2C+Karnataka&sort=date&fromage=1"
        try:
            page = get_html(url)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
                soup = BeautifulSoup(page, "html.parser")
            cards = soup.select("div.job_seen_beacon, div.result, td.resultContent")
            for card in cards[:20]:
                title = clean_text(card.select_one("h2, a[data-jk], span[title]") or card)
                company = clean_text(card.select_one("span[data-testid='company-name'], span.companyName, span.company") or "")
                if not company:
                    continue
                if not any(n.lower() in company.lower() or company.lower() in n.lower() for n in names):
                    continue
                href = ""
                link = card.find("a", href=True)
                if link:
                    href = link["href"]
                    if href.startswith("/"):
                        href = "https://in.indeed.com" + href
                loc = clean_text(card.select_one("div[data-testid='text-location'], div.companyLocation") or "Bengaluru")
                jobs.append(Job(company=company, title=title[:140], location=loc, url=href or url, source="Indeed best-effort", description=clean_text(card), wlb_score=3))
        except Exception as exc:
            print(f"WARN Indeed failed for {term}: {exc}")
            if "Indeed fallback" not in SCAN_ERRORS:
                SCAN_ERRORS.append("Indeed fallback")
        time.sleep(1)
    return jobs


def filter_and_score(jobs: Iterable[Job], settings: dict[str, Any]) -> list[Job]:
    output: list[Job] = []
    seen_keys: set[str] = set()
    for job in jobs:
        if not job.title or not is_public_job_url(job.url):
            continue
        score, reasons = score_job(job, settings)
        if score >= MIN_SCORE:
            job.score = score
            job.reasons = reasons
            if job.dedupe_keys.isdisjoint(seen_keys):
                output.append(job)
                seen_keys.update(job.dedupe_keys)
    output.sort(key=lambda j: (j.score, j.wlb_score), reverse=True)
    return output


def _format_lpa(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _posted_salary_lpa(text: str) -> tuple[float, float] | None:
    """Extract an explicitly posted INR annual salary and normalize it to LPA."""
    cleaned = clean_text(text)
    for dash in (chr(0x2212), chr(0x2013), chr(0x2014)):
        cleaned = cleaned.replace(dash, "-")
    lpa_range = re.search(
        r"(?i)(?:\u20b9|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:-|to)\s*"
        r"(?:\u20b9|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*"
        r"(?:lpa|lakhs?(?:\s+per\s+(?:annum|year))?)\b",
        cleaned,
    )
    if lpa_range:
        low, high = map(float, lpa_range.groups())
        if 1 <= low <= high <= 200:
            return low, high

    annual_range = re.search(
        r"(?i)(?:\u20b9|rs\.?|inr)\s*([\d,]{6,})\s*(?:-|to)\s*"
        r"(?:\u20b9|rs\.?|inr)?\s*([\d,]{6,})\s*(?:per\s+(?:annum|year)|p\.?a\.?)",
        cleaned,
    )
    if annual_range:
        low, high = (float(value.replace(",", "")) / 100_000 for value in annual_range.groups())
        if 1 <= low <= high <= 200:
            return low, high
    return None


def expected_salary(job: Job) -> str:
    """Return posted pay when available, otherwise a conservative 0-3 YOE India CTC estimate."""
    posted = _posted_salary_lpa(" ".join(filter(None, [job.salary_text, job.description])))
    if posted:
        return f"Posted \u20b9{_format_lpa(posted[0])}\u2013{_format_lpa(posted[1])} LPA"

    title = normalize_match_text(job.title)
    if any(term in title for term in ("machine learning engineer", "ml engineer", "ai engineer", "nlp engineer", "mlops engineer")):
        low, high = 10, 22
    elif any(term in title for term in ("data scientist", "applied scientist", "decision scientist")):
        low, high = 8, 18
    elif "analytics engineer" in title:
        low, high = 8, 16
    elif any(term in title for term in ("data engineer", "data platform engineer", "data pipeline engineer")):
        low, high = 8, 18
    elif any(term in title for term in ("devops", "platform engineer", "build engineer", "release engineer", "automation engineer", "site reliability", "compute operations")):
        low, high = 7, 16
    elif any(term in title for term in ("data analyst", "product analyst", "business analyst", "bi analyst", "insights analyst", "business intelligence")):
        low, high = 6, 14
    else:
        low, high = 7, 15
    return f"Est. \u20b9{low}\u2013{high} LPA"


def discord_post(job: Job) -> bool:
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL secret is missing")
        return False
    reasons = "\n".join(f"• {r}" for r in (job.reasons or [])[:5])
    payload = {
        "embeds": [{
            "title": job.title[:250],
            "url": job.url,
            "description": f"**{job.company}**\n{reasons}",
            "color": 5814783,
            "fields": [
                {"name": "Location", "value": job.location[:1000] or "Not specified", "inline": True},
                {"name": "Expected salary*", "value": expected_salary(job), "inline": True},
                {"name": "Match score", "value": f"{job.score}/100", "inline": True},
                {"name": "WLB priority", "value": f"{job.wlb_score}/5", "inline": True},
                {"name": "Source", "value": job.source[:1000], "inline": False},
            ],
            "footer": {"text": "*Salary is estimated unless marked Posted \u2022 scanned every 30 min"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }
    r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    if r.status_code not in (200, 204):
        print(f"ERROR Discord response {r.status_code}: {r.text[:500]}")
        return False
    return True


def discord_summary(message: str) -> bool:
    if not DISCORD_WEBHOOK_URL:
        return False
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": message[:1900]}, timeout=15)
        if response.status_code not in (200, 204):
            print(f"WARN summary response {response.status_code}: {response.text[:300]}")
            return False
        return True
    except Exception as exc:
        print(f"WARN summary failed: {exc}")
        return False


def maybe_send_health_summary(
    *,
    raw_count: int,
    matching_count: int,
    official_source_count: int,
    allowlist_count: int,
) -> None:
    """Send a daily/changed health status and persist it for rate limiting."""
    if not SEND_DAILY_HEALTH:
        return

    previous: dict[str, Any] = {}
    if HEALTH_FILE.exists():
        try:
            previous = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
        except Exception:
            previous = {}

    now = datetime.now(timezone.utc)
    failed_sources = sorted(set(SCAN_ERRORS))
    previous_failures = previous.get("failed_sources") or []
    last_notice = previous.get("last_notice_utc")
    due = True
    if last_notice:
        try:
            due = now - datetime.fromisoformat(last_notice) >= timedelta(hours=DAILY_HEALTH_HOURS)
        except (TypeError, ValueError):
            due = True

    if failed_sources == previous_failures and not due:
        return

    if failed_sources:
        shown = ", ".join(failed_sources[:15])
        extra = len(failed_sources) - 15
        suffix = f" (+{extra} more)" if extra > 0 else ""
        message = (
            f"\u26a0\ufe0f Job bot health: scan completed with {len(failed_sources)} source issue(s). "
            f"Raw jobs: {raw_count}; matching now: {matching_count}. "
            f"Affected: {shown}{suffix}. Other sources continue normally."
        )
    elif previous_failures:
        message = (
            f"\u2705 Job bot recovered: all {official_source_count} configured sources completed "
            f"without a recorded source error. Raw jobs: {raw_count}; matching now: {matching_count}."
        )
    else:
        message = (
            f"\u2705 Daily job bot health: scan completed. "
            f"Configured sources: {official_source_count}; approved companies: {allowlist_count}; "
            f"raw jobs: {raw_count}; matching now: {matching_count}."
        )

    if discord_summary(message):
        HEALTH_FILE.parent.mkdir(exist_ok=True)
        HEALTH_FILE.write_text(
            json.dumps(
                {
                    "last_notice_utc": now.isoformat(),
                    "failed_sources": failed_sources,
                    "official_source_count": official_source_count,
                    "allowlist_count": allowlist_count,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def main() -> int:
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL secret is missing")
        return 1

    SCAN_ERRORS.clear()
    config = load_config()
    seen = load_seen()
    seen_keys = state_dedupe_keys(seen)
    settings = config["settings"]
    all_jobs: list[Job] = []

    for company in config["companies"]:
        all_jobs.extend(fetch_company_jobs(company))
        time.sleep(0.4)

    if config.get("external_job_boards", {}).get("indeed_enabled", False):
        all_jobs.extend(scrape_indeed_best_effort(config))

    matching = filter_and_score(all_jobs, settings)
    now = datetime.now(timezone.utc).isoformat()

    new_jobs: list[Job] = []
    for job in matching:
        if job.dedupe_keys.isdisjoint(seen_keys):
            new_jobs.append(job)
    print(f"Raw jobs: {len(all_jobs)} | Matching: {len(matching)} | New: {len(new_jobs)}")

    if SEND_STARTUP_SUMMARY:
        discord_summary(f"✅ Job bot scan finished. Raw: {len(all_jobs)}, matching: {len(matching)}, new: {len(new_jobs)}")

    failed_alerts = 0
    attempted_jobs = new_jobs[:MAX_ALERTS_PER_RUN]
    for job in attempted_jobs:
        ok = discord_post(job)
        print(f"Alert {'sent' if ok else 'failed'}: {job.title} @ {job.company} ({job.score})")
        if ok:
            seen[job.state_key] = {
                "first_seen_utc": now,
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "url": job.url,
                "source": job.source,
                "score": job.score,
            }
            seen_keys.update(job.dedupe_keys)
            # Persist immediately after Discord accepts an alert. The workflow's
            # always-run state step commits this even if a later alert fails.
            save_seen(seen)
        else:
            failed_alerts += 1
        time.sleep(1)

    save_seen(seen)

    if len(new_jobs) > MAX_ALERTS_PER_RUN:
        remaining = len(new_jobs) - MAX_ALERTS_PER_RUN
        discord_summary(
            f"⚠️ {len(new_jobs)} new jobs matched. "
            f"This run attempted {MAX_ALERTS_PER_RUN}; the remaining {remaining} will be retried next run."
        )

    maybe_send_health_summary(
        raw_count=len(all_jobs),
        matching_count=len(matching),
        official_source_count=sum(
            1 for company in config["companies"] if company.get("enabled", True)
        ),
        allowlist_count=len(approved_company_names(config)),
    )

    if failed_alerts:
        print(f"ERROR: {failed_alerts} Discord alert(s) failed and will be retried")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
