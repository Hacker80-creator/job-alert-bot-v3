"""Description-aware matching for adjacent early-career data/AI roles.

Some employers publish useful roles under generic titles such as "Engineer".
These helpers keep the precise title matcher, then admit a generic technical
title only when its description contains strong data/AI evidence.
"""
from __future__ import annotations

import re
from typing import Any

import job_monitor as bot


BASE_SCORE_JOB = bot.score_job
BASE_PARSE_WORKDAY = bot.parse_workday_search
BASE_PARSE_SMARTRECRUITERS = bot.parse_smartrecruiters

GENERIC_TECH_TITLE = re.compile(
    r"\b(?:engineer|developer|technical analyst|program analyst|research associate)\b",
    re.IGNORECASE,
)
DOMAIN_SIGNALS = (
    "machine learning",
    "artificial intelligence",
    "generative ai",
    "gen ai",
    "data science",
    "data analytics",
    "data engineering",
    "data pipeline",
    "deep learning",
    "natural language processing",
    "computer vision",
    "predictive model",
    "recommendation system",
    "ml workload",
    "ai orchestration",
    "large language model",
    "llm",
)
TECH_SKILLS = (
    "python",
    "sql",
    "pandas",
    "numpy",
    "scikit",
    "pytorch",
    "tensorflow",
    "machine learning",
    "deep learning",
    "spark",
    "databricks",
    "airflow",
    "tableau",
    "power bi",
)
EARLY_CAREER_SIGNALS = (
    "entry level",
    "early career",
    "new grad",
    "graduate role",
    "associate",
    "0-2",
    "0 to 2",
    "0-3",
    "0 to 3",
    "1-3",
    "1 to 3",
    "1+ year",
    "2+ years",
)


def is_generic_technical_title(title: str) -> bool:
    return bool(GENERIC_TECH_TITLE.search(title or ""))


def expanded_is_target_title(title: str) -> bool:
    """Broaden detail fetching; final admission still happens in score_job."""
    return bot_original_is_target_title(title) or is_generic_technical_title(title)


bot_original_is_target_title = bot.is_target_title


def expanded_score_job(job: bot.Job, settings: dict[str, Any]) -> tuple[int, list[str]]:
    score, reasons = BASE_SCORE_JOB(job, settings)
    if score:
        return score, reasons

    if not bot.has_location_match(job.location, settings):
        return 0, ["location not clearly Bangalore/Remote India"]
    if not is_generic_technical_title(job.title):
        return 0, ["title does not match a target or adjacent technical role"]

    rejected, why = bot.reject_by_seniority(job.title, job.description, settings)
    if rejected:
        return 0, [why]

    text = f" {job.title} {job.department} {job.description} ".casefold()
    normalized_title = f" {bot.normalize_match_text(job.title)} "
    domains = [signal for signal in DOMAIN_SIGNALS if signal in text]
    if " ai " in normalized_title and "title: ai" not in domains:
        domains.append("title: AI")
    if " ml " in normalized_title and "title: ml" not in domains:
        domains.append("title: ML")
    skills = [skill for skill in TECH_SKILLS if skill in text]
    early = next((signal for signal in EARLY_CAREER_SIGNALS if signal in text), None)

    # A generic title must have strong description evidence. Two independent
    # domain signals are enough; otherwise require a domain plus two skills or
    # an explicit early-career statement.
    if not domains or (len(domains) < 2 and len(skills) < 2 and not early):
        return 0, ["generic technical title lacks strong data/AI evidence"]

    score = 25 + 35
    reasons = ["Bangalore/Bengaluru or Remote India", "adjacent engineer role verified from description"]
    if domains:
        score += min(15, len(domains) * 5)
        reasons.append("data/AI context: " + ", ".join(domains[:3]))
    if skills:
        score += min(20, len(skills) * 5)
        reasons.append("skills: " + ", ".join(skills[:5]))
    if early:
        score += 10
        reasons.append(f"early-career signal: {early}")
    if job.wlb_score >= 4:
        score += 5
        reasons.append("higher WLB priority company")
    return min(score, 100), reasons


def _workday_detail_url(company: dict[str, Any], job: bot.Job) -> str:
    if "/job/" not in job.url or "/jobs" not in company.get("url", ""):
        return ""
    external_path = "/job/" + job.url.split("/job/", 1)[1]
    return company["url"].rsplit("/jobs", 1)[0] + external_path


def parse_workday_with_generic_details(company: dict[str, Any]) -> list[bot.Job]:
    jobs = BASE_PARSE_WORKDAY(company)
    settings = bot.load_config()["settings"]
    detail_limit = max(0, int(company.get("max_generic_details", 12)))
    fetched = 0
    for job in jobs:
        if fetched >= detail_limit:
            break
        if not is_generic_technical_title(job.title) or not bot.has_location_match(job.location, settings):
            continue
        detail_url = _workday_detail_url(company, job)
        if not detail_url:
            continue
        try:
            data = bot.get_json(detail_url)
            info = data.get("jobPostingInfo") or {}
            job.description = bot.clean_text(info.get("jobDescription")) or job.description
            job.department = bot.clean_text(info.get("jobFamily") or info.get("jobRequisitionLocation")) or job.department
            fetched += 1
        except Exception as exc:
            print(f"WARN {company['name']} Workday detail failed: {exc}")
    return jobs


def parse_smartrecruiters_with_generic_details(company: dict[str, Any]) -> list[bot.Job]:
    jobs = BASE_PARSE_SMARTRECRUITERS(company)
    settings = bot.load_config()["settings"]
    detail_limit = max(0, int(company.get("max_generic_details", 12)))
    fetched = 0
    for job in jobs:
        if fetched >= detail_limit:
            break
        if job.description or not is_generic_technical_title(job.title):
            continue
        if not bot.has_location_match(job.location, settings) or "api.smartrecruiters.com/" not in job.url:
            continue
        try:
            detail = bot.get_json(job.url)
            job.description = bot.clean_text(detail.get("jobAd", {}).get("sections", {}))
            job.url = detail.get("postingUrl") or detail.get("applyUrl") or job.url
            fetched += 1
        except Exception as exc:
            print(f"WARN {company['name']} SmartRecruiters detail failed: {exc}")
    return jobs
