"""Independent SAP UI5/Fiori/BTP and BI/reporting alert pipeline."""
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
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

import custom_source_parsers_v30
import job_match_expanded as expanded
import job_match_production as production
import job_monitor as bot
import job_monitor_entry
import job_monitor_parallel
import qa_job_alerts
from qa_company_sources import QA_ONLY_COMPANY_NAMES
from sap_bi_role_filter import (
    SAP_BI_ROLE_PHRASES,
    SAP_BI_SEARCH_TERMS,
    SAP_BI_SKILL_TERMS,
    is_sap_bi_title,
    is_senior_sap_bi_title,
    matched_sap_bi_role,
)


ROOT = Path(__file__).parent
SAP_BI_STATE_FILE = ROOT / "state" / "seen_sap_bi_jobs.json"
SAP_BI_HEALTH_FILE = ROOT / "state" / "sap_bi_scan_health.json"
SAP_BI_VALIDATION_FILE = ROOT / "sap_bi_source_validation.summary.json"


def load_sap_bi_config() -> dict[str, Any]:
    """Reuse the complete existing ML + QA source universe without adding companies."""
    config = copy.deepcopy(qa_job_alerts.load_qa_config())
    settings = config["settings"]
    settings["target_profile"] = (
        "Early-career SAP UI5/Fiori/BTP/CAP/OData, Power BI, BI/reporting, "
        "SQL, data-visualization, application-support, and requested junior "
        "data roles in Bengaluru/Bangalore or Remote India. Target roughly "
        "1.5 years of experience; accept 0 to 3 years, internships, graduate "
        "roles, trainees, and contract roles."
    )
    settings["strong_title_terms"] = list(SAP_BI_ROLE_PHRASES)
    settings["skill_terms"] = list(SAP_BI_SKILL_TERMS)

    for company in config.get("companies", []):
        company["search_terms"] = list(SAP_BI_SEARCH_TERMS)
        if "zwayam_search_terms" in company:
            company["zwayam_search_terms"] = list(SAP_BI_SEARCH_TERMS)

    config.setdefault("external_job_boards", {})["indeed_enabled"] = False
    return config


def sap_bi_score_job(job: bot.Job, settings: dict[str, Any]) -> tuple[int, list[str]]:
    role = matched_sap_bi_role(job.title)
    if not role:
        return 0, ["title is not in the approved SAP/BI role vocabulary"]
    if is_senior_sap_bi_title(job.title):
        return 0, ["SAP/BI title is above the accepted early-career level"]
    if not bot.has_location_match(job.location, settings):
        return 0, ["location not clearly Bangalore/Bengaluru or Remote India"]

    # The shared legacy guard sees the trailing digit in "1.5 years" as
    # "5 years". Normalize allowed decimal experience before using it, while
    # leaving values above three years intact so they are still rejected.
    def normalize_allowed_decimal(match: re.Match[str]) -> str:
        years = float(match.group(1))
        return f"{int(years)} years" if years <= 3 else match.group(0)

    experience_guard_description = re.sub(
        r"\b(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\b",
        normalize_allowed_decimal,
        job.description or "",
        flags=re.IGNORECASE,
    )
    rejected, reason = production.reject_extended_experience(
        job.title, experience_guard_description, settings
    )
    if rejected:
        return 0, [reason]

    body = bot.normalize_match_text(
        " ".join(filter(None, [job.title, job.department, job.description]))
    )
    matched_skills = [
        skill
        for skill in SAP_BI_SKILL_TERMS
        if f" {bot.normalize_match_text(skill)} " in f" {body} "
    ]
    reasons = [
        "Bangalore/Bengaluru or Remote India",
        f"approved SAP/BI role: {role}",
    ]
    score = 70
    if matched_skills:
        score += min(20, len(matched_skills) * 4)
        reasons.append("relevant skills: " + ", ".join(matched_skills[:6]))
    if any(
        term in body
        for term in (
            "intern",
            "trainee",
            "graduate",
            "junior",
            "associate",
            "entry level",
            "early career",
            "0 2 years",
            "0 to 2 years",
            "1 2 years",
            "1 to 2 years",
            "1 3 years",
            "1 to 3 years",
            "1 5 years",
            "1 5 year",
        )
    ):
        score += 10
        reasons.append("early-career/approximately 1.5-year signal")
    if "contract" in body:
        reasons.append("contract role accepted")
    if job.wlb_score >= 4:
        score += 5
        reasons.append("higher WLB priority company")
    return min(score, 100), reasons


def parse_sap_bi_html_search(company: dict[str, Any]) -> list[bot.Job]:
    """Read server-rendered career links and retain only approved titles."""
    page = bot.get_html(company["url"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
        soup = BeautifulSoup(page, "html.parser")
    jobs_by_url: dict[str, bot.Job] = {}
    for anchor in soup.find_all("a", href=True):
        href = urljoin(company["url"], str(anchor.get("href") or ""))
        if not href.startswith(("http://", "https://")):
            continue
        if not any(
            marker in href.casefold()
            for marker in ("job", "career", "position", "opening", "requisition", "apply")
        ):
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
        title = next((value for value in candidates if is_sap_bi_title(value)), "")
        if not title:
            continue
        jobs_by_url[href] = bot.Job(
            company=company["name"],
            title=title[:180],
            location=context[:700],
            url=href,
            source="Official careers: HTML SAP/BI listing",
            description=context[:2500],
            wlb_score=company.get("wlb_score", 3),
        )
    return list(jobs_by_url.values())


def _infosys_search_url(url: str, term: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["searchText"] = term
    return urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        urlencode(query),
        parsed.fragment,
    ))


def parse_infosys_api(company: dict[str, Any]) -> list[bot.Job]:
    """Search Infosys's official API with the SAP/BI query vocabulary."""
    jobs_by_id: dict[str, bot.Job] = {}
    for term in company.get("search_terms") or SAP_BI_SEARCH_TERMS:
        response = requests.get(
            _infosys_search_url(company["url"], str(term)),
            headers=bot.HEADERS,
            timeout=45,
        )
        response.raise_for_status()
        records = response.json()
        if not isinstance(records, list):
            raise ValueError("Infosys careers API returned a non-list response")
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
            minimum = item.get("minExperienceLevel")
            maximum = item.get("maxExperienceLevel")
            experience = ""
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


def fetch_sap_bi_company_jobs(company: dict[str, Any]) -> list[bot.Job]:
    parser = {
        "qa_html_search": parse_sap_bi_html_search,
        "breezy": qa_job_alerts.parse_breezy,
        "infosys_api": parse_infosys_api,
        "phenom_content_api": qa_job_alerts.parse_phenom_content_api,
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
    bot.DISCORD_WEBHOOK_URL = os.getenv("SAP_BI_DISCORD_WEBHOOK_URL", "").strip()
    bot.STATE_FILE = SAP_BI_STATE_FILE
    bot.HEALTH_FILE = SAP_BI_HEALTH_FILE
    bot.ENABLE_INDEED = False
    bot.is_target_title = is_sap_bi_title
    bot.score_job = sap_bi_score_job
    bot.parse_html_search = parse_sap_bi_html_search
    bot.parse_workday_search = expanded.parse_workday_with_generic_details
    bot.parse_smartrecruiters = expanded.parse_smartrecruiters_with_generic_details
    bot.parse_lever = job_monitor_entry.parse_lever_with_region
    bot.fetch_company_jobs = fetch_sap_bi_company_jobs
    job_monitor_parallel.load_merged_config = load_sap_bi_config


def validate_shared_extension_sources() -> int:
    """Validate sources shared from the QA extension on this feature branch."""
    configure_runtime()
    config = load_sap_bi_config()
    bot.load_config = lambda: config
    sources_by_name = {
        company["name"]: company
        for company in config["companies"]
        if company["name"] in QA_ONLY_COMPANY_NAMES
    }
    bot.SCAN_ERRORS.clear()
    results: list[dict[str, Any]] = []
    enabled = [
        source for source in sources_by_name.values() if source.get("enabled", True)
    ]
    with ThreadPoolExecutor(max_workers=min(8, len(enabled) or 1)) as pool:
        futures = {
            pool.submit(fetch_sap_bi_company_jobs, source): source
            for source in enabled
        }
        for future in as_completed(futures):
            source = futures[future]
            jobs = future.result()
            failed = source["name"] in bot.SCAN_ERRORS
            results.append({
                "company": source["name"],
                "ats": source.get("ats"),
                "status": (
                    "FAILED" if failed else ("WORKING" if jobs else "NO_CURRENT_MATCHING")
                ),
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
        "no_current_matching": sum(
            item["status"] == "NO_CURRENT_MATCHING" for item in results
        ),
        "disabled": sum(item["status"] == "DISABLED" for item in results),
        "results": results,
    }
    SAP_BI_VALIDATION_FILE.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "SAP_BI_SOURCE_SUMMARY "
        f"requested={summary['requested']} enabled={summary['enabled']} "
        f"working={summary['working']} "
        f"no_current_matching={summary['no_current_matching']} "
        f"failed={summary['failed']} disabled={summary['disabled']}"
    )
    for item in results:
        print(
            f"{item['status']} {item['company']}: "
            f"{item['raw_jobs']} raw jobs from {item['ats']}"
        )
    return 1 if summary["failed"] else 0


def run() -> int:
    configure_runtime()
    return job_monitor_parallel.run()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-sources", action="store_true")
    args = parser.parse_args()
    if args.validate_sources:
        return validate_shared_extension_sources()
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
