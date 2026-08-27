"""Independent QA/testing alert pipeline using the production source registry."""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

import custom_source_parsers_v30
import job_match_expanded as expanded
import job_match_production as production
import job_monitor as bot
import job_monitor_entry
import job_monitor_entry_v44
import job_monitor_parallel
from qa_company_sources import QA_ONLY_COMPANY_NAMES, build_qa_only_sources
from qa_role_filter import (
    QA_ROLE_PHRASES,
    QA_SEARCH_TERMS,
    QA_SKILL_TERMS,
    is_qa_title,
    is_senior_qa_title,
)


ROOT = Path(__file__).parent
QA_STATE_FILE = ROOT / "state" / "seen_qa_jobs.json"
QA_HEALTH_FILE = ROOT / "state" / "qa_scan_health.json"
QA_VALIDATION_FILE = ROOT / "qa_source_validation.summary.json"


def load_qa_config() -> dict[str, Any]:
    """Reuse every production scanner, then append sources exclusive to QA."""
    config = copy.deepcopy(job_monitor_entry_v44.load_final_config())
    settings = config["settings"]
    settings["target_profile"] = (
        "Entry-level QA, quality assurance, software testing, SDET, manual, "
        "functional, API, mobile, performance, validation, and test-automation "
        "roles in Bengaluru/Bangalore or Remote India. Accept 0 to 3 years, "
        "internships, graduate roles, trainees, and contract roles."
    )
    settings["strong_title_terms"] = list(QA_ROLE_PHRASES)
    settings["skill_terms"] = list(QA_SKILL_TERMS)

    # Query searchable ATS feeds for QA terms instead of the ML/data terms.
    for company in config.get("companies", []):
        company["search_terms"] = list(QA_SEARCH_TERMS)

    existing = {
        str(company.get("name", "")).casefold()
        for company in config.get("companies", [])
    }
    for source in build_qa_only_sources():
        if source["name"].casefold() not in existing:
            config.setdefault("companies", []).append(source)
            existing.add(source["name"].casefold())

    config.setdefault("external_job_boards", {})["indeed_enabled"] = False
    return config


def qa_score_job(job: bot.Job, settings: dict[str, Any]) -> tuple[int, list[str]]:
    if not is_qa_title(job.title):
        return 0, ["title is not in the approved QA/testing role vocabulary"]
    if is_senior_qa_title(job.title):
        return 0, ["QA title is above the accepted 0-3 year level"]
    if not bot.has_location_match(job.location, settings):
        return 0, ["location not clearly Bangalore/Bengaluru or Remote India"]

    rejected, reason = production.reject_extended_experience(
        job.title, job.description, settings
    )
    if rejected:
        return 0, [reason]

    normalized_title = bot.normalize_match_text(job.title)
    matched_role = next(
        (role for role in sorted(QA_ROLE_PHRASES, key=len, reverse=True)
         if f" {role} " in f" {normalized_title} "),
        "QA/testing role",
    )
    body = bot.normalize_match_text(
        " ".join(filter(None, [job.title, job.department, job.description]))
    )
    matched_skills = [
        skill for skill in QA_SKILL_TERMS
        if f" {bot.normalize_match_text(skill)} " in f" {body} "
    ]
    reasons = [
        "Bangalore/Bengaluru or Remote India",
        f"QA role title: {matched_role}",
    ]
    score = 70
    if matched_skills:
        score += min(20, len(matched_skills) * 4)
        reasons.append("QA skills: " + ", ".join(matched_skills[:6]))
    if any(term in body for term in (
        "intern", "trainee", "graduate", "junior", "associate",
        "entry level", "early career", "0 3 years", "0 to 3 years",
        "1 3 years", "1 to 3 years",
    )):
        score += 10
        reasons.append("early-career/internship signal")
    if "contract" in body:
        reasons.append("contract role accepted")
    if job.wlb_score >= 4:
        score += 5
        reasons.append("higher WLB priority company")
    return min(score, 100), reasons


def parse_qa_html_search(company: dict[str, Any]) -> list[bot.Job]:
    """Conservative server-rendered fallback restricted to QA titles."""
    page = bot.get_html(company["url"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
        soup = BeautifulSoup(page, "html.parser")
    jobs_by_url: dict[str, bot.Job] = {}
    for anchor in soup.find_all("a", href=True):
        href = urljoin(company["url"], str(anchor.get("href") or ""))
        if not href.startswith(("http://", "https://")):
            continue
        if not any(marker in href.casefold() for marker in (
            "job", "career", "position", "opening", "requisition", "apply",
        )):
            continue

        candidates = [
            bot.clean_text(anchor.get_text(" ")),
            bot.clean_text(anchor.get("title")),
            bot.clean_text(anchor.get("aria-label")),
        ]
        context = candidates[0]
        for parent in anchor.parents:
            if parent is soup:
                break
            if getattr(parent, "name", "") not in {
                "article", "li", "tr", "div", "section",
            }:
                continue
            parent_text = bot.clean_text(parent.get_text(" "))
            if len(parent_text) > 2500:
                break
            heading = parent.find(["h1", "h2", "h3", "h4", "h5"])
            if heading:
                candidates.append(bot.clean_text(heading.get_text(" ")))
            if len(parent_text) > len(context) + 3:
                context = parent_text
                break
        title = next((value for value in candidates if is_qa_title(value)), "")
        if not title:
            continue
        jobs_by_url[href] = bot.Job(
            company=company["name"],
            title=title[:180],
            location=context[:700],
            url=href,
            source="Official careers: HTML QA listing",
            description=context[:2500],
            wlb_score=company.get("wlb_score", 3),
        )
    return list(jobs_by_url.values())


def parse_breezy(company: dict[str, Any]) -> list[bot.Job]:
    data = bot.get_json(company["url"])
    records = data if isinstance(data, list) else data.get("positions", [])
    jobs: list[bot.Job] = []
    for item in records:
        location = item.get("location") or {}
        if isinstance(location, dict):
            location_text = bot.clean_text(location.get("name"))
            if location.get("is_remote") and "india" not in location_text.casefold():
                location_text = f"{location_text}; Remote"
        else:
            location_text = bot.flatten_location(location)
        jobs.append(bot.Job(
            company=company["name"],
            title=bot.clean_text(item.get("name") or item.get("title")),
            location=location_text,
            url=str(item.get("url") or ""),
            source="Official careers: Breezy",
            description=bot.clean_text(item.get("description")),
            department=bot.clean_text(item.get("department")),
            salary_text=bot.clean_text(item.get("salary")),
            requisition_id=bot.clean_text(item.get("id")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_infosys_api(company: dict[str, Any]) -> list[bot.Job]:
    """Read Infosys's official unauthenticated India careers API."""
    response = requests.get(company["url"], headers=bot.HEADERS, timeout=45)
    response.raise_for_status()
    records = response.json()
    if not isinstance(records, list):
        raise ValueError("Infosys careers API returned a non-list response")

    jobs_by_id: dict[str, bot.Job] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        job_id = bot.clean_text(
            item.get("referenceCode")
            or item.get("requisitionId")
            or item.get("postingId")
        )
        title = bot.clean_text(
            item.get("postingTitle") or item.get("roleDesignation")
        )
        if not job_id or not title:
            continue
        source_id = bot.clean_text(item.get("sourceId"))
        job_url = (
            "https://career.infosys.com/jobdesc?jobReferenceCode="
            f"{quote(job_id)}&sourceId={quote(source_id)}"
        )
        experience = ""
        minimum = item.get("minExperienceLevel")
        maximum = item.get("maxExperienceLevel")
        if minimum not in (None, "") or maximum not in (None, ""):
            experience = f"Experience: {minimum or 0}-{maximum or ''} years"
        description = " | ".join(filter(None, [
            bot.clean_text(item.get("postingDescription")),
            bot.clean_text(item.get("technicalRequirement")),
            bot.clean_text(item.get("rolesResponsibilities")),
            bot.clean_text(item.get("additionalResponsibility")),
            bot.clean_text(item.get("preferredSkills")),
            experience,
        ]))
        jobs_by_id.setdefault(job_id, bot.Job(
            company=company["name"],
            title=title,
            location=bot.clean_text(item.get("location")),
            url=job_url,
            source="Official careers: Infosys",
            description=description,
            department=bot.clean_text(
                item.get("functionalArea") or item.get("unit")
            ),
            requisition_id=job_id,
            wlb_score=company.get("wlb_score", 3),
        ))
    return list(jobs_by_id.values())


def parse_phenom_content_api(company: dict[str, Any]) -> list[bot.Job]:
    """Read Phenom's first-party content API without the protected site shell."""
    terms = company.get("search_terms") or list(QA_SEARCH_TERMS)
    page_size = max(10, min(100, int(company.get("page_size", 50))))
    max_pages = max(1, int(company.get("max_pages_per_term", 2)))
    locale = str(company.get("locale", "en_global"))
    site_id = str(company.get("site_id", ""))
    jobs_by_id: dict[str, bot.Job] = {}

    for term in terms:
        for page in range(max_pages):
            payload = {
                "lang": locale,
                "deviceType": "desktop",
                "country": "global",
                "pageName": "search-results",
                "ddoKey": "refineSearch",
                "sortBy": "",
                "subsearch": "",
                "from": page * page_size,
                "jobs": True,
                "counts": True,
                "all_fields": ["category", "country", "state", "city"],
                "size": page_size,
                "clearAll": False,
                "jdsource": "facets",
                "isSliderEnable": True,
                "keywords": str(term),
                "selected_fields": {"country": ["India"]},
            }
            response = requests.get(
                company["url"],
                params={
                    "locale": locale,
                    "siteType": "external",
                    "deviceType": "desktop",
                    "payload": json.dumps(payload, separators=(",", ":")),
                },
                headers=bot.HEADERS,
                timeout=40,
            )
            response.raise_for_status()
            container = response.json().get("refineSearch") or {}
            raw_jobs = (container.get("data") or {}).get("jobs") or []
            for item in raw_jobs:
                job_id = bot.clean_text(
                    item.get("jobId") or item.get("reqId")
                    or item.get("jobSeqNo")
                )
                title = bot.clean_text(item.get("title"))
                if not job_id or not title:
                    continue
                slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
                job_url = (
                    company["career_site_url"].rstrip("/")
                    + f"/job/{quote(job_id)}/{quote(slug)}"
                )
                description = " | ".join(filter(None, [
                    bot.clean_text(item.get("descriptionTeaser")),
                    bot.clean_text(item.get("ml_skills")),
                    (
                        f"Experience: {bot.clean_text(item.get('experience'))} years"
                        if item.get("experience") not in (None, "") else ""
                    ),
                    bot.clean_text(item.get("type")),
                ]))
                jobs_by_id.setdefault(job_id, bot.Job(
                    company=company["name"],
                    title=title,
                    location=bot.flatten_location(
                        item.get("location") or item.get("cityStateCountry")
                        or [item.get("city"), item.get("state"), item.get("country")]
                    ),
                    url=job_url,
                    source=f"Official careers: Phenom ({site_id})",
                    description=description,
                    department=bot.clean_text(
                        item.get("department") or item.get("category")
                    ),
                    requisition_id=job_id,
                    wlb_score=company.get("wlb_score", 3),
                ))
            try:
                total = int(container.get("totalHits") or 0)
            except (TypeError, ValueError):
                total = 0
            if (
                not raw_jobs
                or len(raw_jobs) < page_size
                or (total and (page + 1) * page_size >= total)
            ):
                break
    return list(jobs_by_id.values())


def fetch_qa_company_jobs(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "qa_html_search": parse_qa_html_search,
        "breezy": parse_breezy,
        "infosys_api": parse_infosys_api,
        "phenom_content_api": parse_phenom_content_api,
    }.get(company.get("ats"))
    if parser is None:
        return custom_source_parsers_v30.fetch_company_jobs_with_custom_v30(company)
    if not company.get("enabled", True):
        return []
    try:
        jobs = parser(company)
        print(f"{company['name']}: {len(jobs)} raw jobs from {company['ats']}")
        return jobs
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        bot.SCAN_ERRORS.append(company["name"])
        return []


def configure_runtime() -> None:
    bot.DISCORD_WEBHOOK_URL = os.getenv("QA_DISCORD_WEBHOOK_URL", "").strip()
    bot.STATE_FILE = QA_STATE_FILE
    bot.HEALTH_FILE = QA_HEALTH_FILE
    bot.ENABLE_INDEED = False
    bot.is_target_title = is_qa_title
    bot.score_job = qa_score_job
    bot.parse_html_search = parse_qa_html_search
    bot.parse_workday_search = expanded.parse_workday_with_generic_details
    bot.parse_smartrecruiters = expanded.parse_smartrecruiters_with_generic_details
    bot.parse_lever = job_monitor_entry.parse_lever_with_region
    bot.fetch_company_jobs = fetch_qa_company_jobs
    job_monitor_parallel.load_merged_config = load_qa_config


def validate_qa_only_sources() -> int:
    configure_runtime()
    config = load_qa_config()
    bot.load_config = lambda: config
    sources_by_name = {
        company["name"]: company for company in config["companies"]
        if company["name"] in QA_ONLY_COMPANY_NAMES
    }
    bot.SCAN_ERRORS.clear()
    results: list[dict[str, Any]] = []
    enabled = [source for source in sources_by_name.values() if source.get("enabled", True)]
    with ThreadPoolExecutor(max_workers=min(8, len(enabled) or 1)) as pool:
        futures = {pool.submit(fetch_qa_company_jobs, source): source for source in enabled}
        for future in as_completed(futures):
            source = futures[future]
            jobs = future.result()
            failed = source["name"] in bot.SCAN_ERRORS
            results.append({
                "company": source["name"],
                "ats": source.get("ats"),
                "status": "FAILED" if failed else ("WORKING" if jobs else "NO_CURRENT_MATCHING"),
                "raw_jobs": len(jobs),
            })
    for source in sources_by_name.values():
        if not source.get("enabled", True):
            results.append({
                "company": source["name"],
                "ats": source.get("ats"),
                "status": "DISABLED",
                "raw_jobs": 0,
                "reason": source.get("disabled_reason", "disabled"),
            })
    results.sort(key=lambda item: item["company"].casefold())
    summary = {
        "requested": len(sources_by_name),
        "enabled": len(enabled),
        "failed": sum(item["status"] == "FAILED" for item in results),
        "working": sum(item["status"] == "WORKING" for item in results),
        "no_current_matching": sum(item["status"] == "NO_CURRENT_MATCHING" for item in results),
        "disabled": sum(item["status"] == "DISABLED" for item in results),
        "results": results,
    }
    QA_VALIDATION_FILE.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        "QA_SOURCE_SUMMARY "
        f"requested={summary['requested']} enabled={summary['enabled']} "
        f"working={summary['working']} no_current_matching={summary['no_current_matching']} "
        f"failed={summary['failed']} disabled={summary['disabled']}"
    )
    for item in results:
        print(f"{item['status']} {item['company']}: {item['raw_jobs']} raw jobs from {item['ats']}")
    return 1 if summary["failed"] else 0


def run() -> int:
    configure_runtime()
    return job_monitor_parallel.run()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-sources", action="store_true")
    args = parser.parse_args()
    if args.validate_sources:
        return validate_qa_only_sources()
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
