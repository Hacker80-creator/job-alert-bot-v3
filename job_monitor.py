"""Discord Job Alert Bot for Bangalore Data Science / Analytics roles.

Primary source: official career feeds / ATS APIs.
Secondary source: Indeed best-effort search, filtered by an approved product-company allowlist.

The bot is designed for GitHub Actions every 30 minutes.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote_plus

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "companies.yaml"
STATE_FILE = ROOT / "state" / "seen_jobs.json"

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
MIN_SCORE = int(os.getenv("MIN_SCORE", "70"))
MAX_ALERTS_PER_RUN = int(os.getenv("MAX_ALERTS_PER_RUN", "15"))
SEND_STARTUP_SUMMARY = os.getenv("SEND_STARTUP_SUMMARY", "false").lower() == "true"
ENABLE_INDEED = os.getenv("ENABLE_INDEED", "true").lower() == "true"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SuriJobAlertBot/3.0; +https://github.com/)",
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

@dataclass
class Job:
    company: str
    title: str
    location: str
    url: str
    source: str
    description: str = ""
    department: str = ""
    wlb_score: int = 3
    score: int = 0
    reasons: list[str] | None = None

    @property
    def fingerprint(self) -> str:
        raw = f"{self.company}|{self.title}|{self.location}|{self.url}".lower().strip()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def load_config() -> dict[str, Any]:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_seen(seen: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(seen, indent=2, sort_keys=True), encoding="utf-8")


def clean_text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        value = " ".join(map(str, value))
    text = BeautifulSoup(str(value), "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def get_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    if method == "POST":
        r = requests.post(url, json=payload or {}, headers=HEADERS, timeout=20)
    else:
        r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def get_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def flatten_location(value: Any) -> str:
    if isinstance(value, dict):
        parts = [value.get(k) for k in ("name", "city", "region", "country", "location")]
        return clean_text(" ".join([str(p) for p in parts if p]))
    if isinstance(value, list):
        return clean_text("; ".join(flatten_location(x) for x in value))
    return clean_text(value)


def has_location_match(text: str, settings: dict[str, Any]) -> bool:
    t = text.lower()
    include = settings["location_terms"]
    exclude = settings["exclude_location_terms"]
    if any(term in t for term in include):
        return True
    # Some official API postings omit location in list response; allow India remote if no competing Indian city exists.
    if "india" in t and "remote" in t:
        return True
    if any(term in t for term in exclude):
        return False
    return False


def reject_by_seniority(title: str, body: str, settings: dict[str, Any]) -> tuple[bool, str]:
    text = f"{title} {body}".lower()
    title_l = title.lower()
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

    if has_location_match(f"{job.location} {job.description}", settings):
        score += 25
        reasons.append("Bangalore/Bengaluru or Remote India")
    else:
        reasons.append("location not clearly Bangalore/Remote India")
        return 0, reasons

    for term in settings["strong_title_terms"]:
        if term in title_l:
            score += 35
            reasons.append(f"role title: {term}")
            break

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
    url = f"https://api.smartrecruiters.com/v1/companies/{company['slug']}/postings?limit=100"
    data = get_json(url)
    jobs = []
    for item in data.get("content", []):
        location = flatten_location(item.get("location"))
        detail = ""
        detail_url = item.get("ref")
        if detail_url:
            try:
                detail_json = get_json(detail_url)
                detail = clean_text(detail_json.get("jobAd", {}).get("sections", {}))
            except Exception:
                pass
        jobs.append(Job(
            company=company["name"],
            title=clean_text(item.get("name")),
            location=location,
            url=item.get("ref", ""),
            source="Official careers: SmartRecruiters",
            description=detail,
            department=clean_text(item.get("department")),
            wlb_score=company.get("wlb_score", 3),
        ))
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
    # Generic Workday CXS endpoint. Some tenants require a site-specific body; failures are logged and skipped.
    payload = {"appliedFacets": {}, "limit": 100, "offset": 0, "searchText": "data Bangalore"}
    data = get_json(company["url"], method="POST", payload=payload)
    raw_jobs = data.get("jobPostings", []) or data.get("jobs", [])
    jobs = []
    for item in raw_jobs:
        external_path = item.get("externalPath") or item.get("url") or ""
        if external_path.startswith("/"):
            base = company["url"].split("/wday/")[0]
            url = base + external_path
        else:
            url = external_path or company["url"]
        jobs.append(Job(
            company=company["name"],
            title=clean_text(item.get("title")),
            location=flatten_location(item.get("locationsText") or item.get("location")),
            url=url,
            source="Official careers: Workday",
            description=clean_text(item.get("bulletFields") or item.get("jobDescription")),
            department=clean_text(item.get("jobFamily")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_html_search(company: dict[str, Any]) -> list[Job]:
    # Fallback. Better than nothing, but official APIs above are more reliable.
    page = get_html(company["url"])
    soup = BeautifulSoup(page, "html.parser")
    text = clean_text(soup.get_text(" "))
    results: list[Job] = []
    for a in soup.find_all("a", href=True):
        title = clean_text(a.get_text(" "))
        if not title or len(title) > 140:
            continue
        title_l = title.lower()
        if not any(term in title_l for term in ["data", "analytics", "scientist", "machine learning", "analyst", "business intelligence", "ai ", "ml "]):
            continue
        href = a["href"]
        if href.startswith("/"):
            base_match = re.match(r"https?://[^/]+", company["url"])
            href = (base_match.group(0) if base_match else "") + href
        results.append(Job(
            company=company["name"],
            title=title,
            location=text[:2000],
            url=href if href.startswith("http") else company["url"],
            source="Official careers: HTML fallback",
            description=text[:5000],
            department="",
            wlb_score=company.get("wlb_score", 3),
        ))
    if not results and any(x in text.lower() for x in ["data", "analytics", "scientist", "machine learning"]):
        results.append(Job(
            company=company["name"],
            title="Possible matching career page result - review manually",
            location=text[:2000],
            url=company["url"],
            source="Official careers: HTML fallback",
            description=text[:5000],
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
        "amazon": parse_amazon,
        "ms_search": parse_ms_search,
        "workday_search": parse_workday_search,
        "html_search": parse_html_search,
    }
    parser = parsers.get(ats)
    if not parser:
        print(f"WARN unsupported ATS for {company['name']}: {ats}")
        return []
    try:
        jobs = parser(company)
        print(f"{company['name']}: {len(jobs)} raw jobs from {ats}")
        return jobs
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        return []


def approved_company_names(config: dict[str, Any]) -> list[str]:
    return [c["name"] for c in config["companies"] if c.get("enabled", True)]


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
        time.sleep(1)
    return jobs


def filter_and_score(jobs: Iterable[Job], settings: dict[str, Any]) -> list[Job]:
    output: list[Job] = []
    seen_fp: set[str] = set()
    for job in jobs:
        if not job.title or not job.url:
            continue
        score, reasons = score_job(job, settings)
        if score >= MIN_SCORE:
            job.score = score
            job.reasons = reasons
            if job.fingerprint not in seen_fp:
                output.append(job)
                seen_fp.add(job.fingerprint)
    output.sort(key=lambda j: (j.score, j.wlb_score), reverse=True)
    return output


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
                {"name": "Match score", "value": f"{job.score}/100", "inline": True},
                {"name": "WLB priority", "value": f"{job.wlb_score}/5", "inline": True},
                {"name": "Source", "value": job.source[:1000], "inline": False},
            ],
            "footer": {"text": "Product-company DS/Analytics alert • scanned every 30 min"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }
    r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    if r.status_code not in (200, 204):
        print(f"ERROR Discord response {r.status_code}: {r.text[:500]}")
        return False
    return True


def discord_summary(message: str) -> None:
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message[:1900]}, timeout=15)
    except Exception as exc:
        print(f"WARN summary failed: {exc}")


def main() -> int:
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL secret is missing")
        return 1

    config = load_config()
    seen = load_seen()
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
        fp = job.fingerprint
        if fp not in seen:
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
            seen[job.fingerprint] = {
                "first_seen_utc": now,
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "url": job.url,
                "source": job.source,
                "score": job.score,
            }
        else:
            failed_alerts += 1
        time.sleep(1)

    # Keep only the most recently seen jobs when the state grows too large.
    if len(seen) > 5000:
        items = sorted(
            seen.items(),
            key=lambda item: item[1].get("first_seen_utc", ""),
            reverse=True,
        )[:4000]
        seen = dict(items)

    save_seen(seen)

    if len(new_jobs) > MAX_ALERTS_PER_RUN:
        remaining = len(new_jobs) - MAX_ALERTS_PER_RUN
        discord_summary(
            f"⚠️ {len(new_jobs)} new jobs matched. "
            f"This run attempted {MAX_ALERTS_PER_RUN}; the remaining {remaining} will be retried next run."
        )

    if failed_alerts:
        print(f"ERROR: {failed_alerts} Discord alert(s) failed and will be retried")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
