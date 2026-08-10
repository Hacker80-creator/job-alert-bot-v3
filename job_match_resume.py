"""Resume-aware matching for Jagadev's adjacent early-career roles.

The existing production matcher remains authoritative for data/AI roles. This
module adds a separate, description-gated lane for the candidate's demonstrated
DevOps, platform, build/release, automation, and data-engineering experience.
"""
from __future__ import annotations

import re
from typing import Any

import job_match_expanded as expanded
import job_match_precision as precision
import job_match_production as production
import job_monitor as bot


PLATFORM_TITLE = re.compile(
    r"\b(?:devops|platform|build(?: and)? release|release engineering|"
    r"build engineering|automation|infrastructure|site reliability|"
    r"cloud operations|compute operations|engineering compute)\b",
    re.IGNORECASE,
)
DATA_ADJACENT_TITLE = re.compile(
    r"\b(?:data engineer|data platform engineer|data pipeline engineer|"
    r"etl developer|data science|analytics developer)\b",
    re.IGNORECASE,
)
NON_PROFILE_TITLE = re.compile(
    r"\b(?:technical support|customer engineer|customer success|field service|sales|"
    r"full[ -]?stack|front[ -]?end|back[ -]?end|physical design|silicon|rtl|"
    r"firmware|embedded|electrical|mechanical|verification engineer)\b",
    re.IGNORECASE,
)
EXPERIENCED_TITLE = re.compile(r"\badvisor\b", re.IGNORECASE)
DESCRIPTION_SENIOR = re.compile(
    r"\b(?:senior contributor|senior[ -]level|seasoned professional|"
    r"experienced (?:software|platform|devops|data) engineer)\b",
    re.IGNORECASE,
)
ADJACENT_EXPERIENCE_TOO_HIGH = re.compile(
    r"\b(?:minimum|min|at least|requires?|required|bring|have|with)?\s*"
    r"(3(?:\.0)?)\s*(?:plus|\+)\s*year(?:s|\s+s)?\b",
    re.IGNORECASE,
)
EARLY_ROLE = re.compile(
    r"\b(?:entry[ -]?level|early[ -]?career|new grad|graduate role|associate|"
    r"apprentice|trainee|0\s*(?:-|to)\s*[23]|1\s*(?:-|to|\+)\s*[123]?|"
    r"2\s*(?:-|to|\+)\s*[35]?)\b",
    re.IGNORECASE,
)

PROFILE_SKILLS = (
    "python",
    "sql",
    "groovy",
    "bash",
    "shell scripting",
    "git",
    "github",
    "github actions",
    "jenkins",
    "docker",
    "podman",
    "linux",
    "rhel",
    "jfrog",
    "artifactory",
    "ansible",
    "yaml",
    "power bi",
)
DATA_SKILLS = (
    "python",
    "sql",
    "pandas",
    "numpy",
    "scikit learn",
    "machine learning",
    "statistics",
    "spark",
    "databricks",
    "airflow",
    "etl",
    "power bi",
    "tableau",
)
PLATFORM_SIGNALS = (
    "devops",
    "platform engineering",
    "ci cd",
    "continuous integration",
    "continuous delivery",
    "continuous deployment",
    "infrastructure as code",
    "build automation",
    "release automation",
    "deployment automation",
    "containerized",
    "containerization",
    "configuration management",
    "artifact management",
    "linux systems",
    "compute infrastructure",
    "engineering compute",
    "site reliability",
    "cloud infrastructure",
    "build pipeline",
    "deployment pipeline",
)


def _phrases(text: str, candidates: tuple[str, ...]) -> list[str]:
    padded = f" {bot.normalize_match_text(text)} "
    return [value for value in candidates if f" {value} " in padded]


def resume_is_target_title(title: str) -> bool:
    """Broaden detail fetching; final alert admission remains description-gated."""
    return bool(
        expanded.expanded_is_target_title(title)
        or PLATFORM_TITLE.search(title or "")
        or DATA_ADJACENT_TITLE.search(title or "")
    )


def _resume_lane(job: bot.Job, settings: dict[str, Any]) -> tuple[int, list[str]]:
    if not bot.has_location_match(job.location, settings):
        return 0, ["location not clearly Bangalore/Remote India"]

    rejected, reason = production.reject_extended_experience(
        job.title, job.description, settings
    )
    if rejected:
        return 0, [reason]
    if NON_PROFILE_TITLE.search(job.title or ""):
        return 0, ["role family does not overlap the resume target lanes"]
    if EXPERIENCED_TITLE.search(job.title or ""):
        return 0, ["title indicates an experienced advisory level"]

    opening = bot.clean_text(job.description)[:1600]
    if DESCRIPTION_SENIOR.search(opening):
        return 0, ["description identifies an experienced/senior role"]
    if ADJACENT_EXPERIENCE_TOO_HIGH.search(bot.clean_text(job.description)):
        return 0, ["adjacent role requires 3+ years; above demonstrated experience"]

    title = job.title or ""
    body = " ".join(filter(None, [job.department, job.description]))
    profile_skills = _phrases(body, PROFILE_SKILLS)
    early = bool(EARLY_ROLE.search(bot.normalize_match_text(body)))

    platform_title = bool(PLATFORM_TITLE.search(title))
    platform_signals = _phrases(f"{title} {body}", PLATFORM_SIGNALS)
    generic_technical = expanded.is_generic_technical_title(title)

    if platform_title or (generic_technical and platform_signals):
        if platform_title:
            qualified = len(platform_signals) >= 1 and len(profile_skills) >= 3
        else:
            qualified = (
                early and len(platform_signals) >= 2 and len(profile_skills) >= 4
            )
        if qualified:
            score = 60
            reasons = [
                "Bangalore/Bengaluru or Remote India",
                "resume lane: DevOps/platform/build automation",
            ]
            score += min(20, len(profile_skills) * 5)
            reasons.append("resume skills: " + ", ".join(profile_skills[:6]))
            score += min(10, len(platform_signals) * 5)
            reasons.append("platform context: " + ", ".join(platform_signals[:3]))
            if early:
                score += 10
                reasons.append("early-career signal")
            if job.wlb_score >= 4:
                score += 5
                reasons.append("higher WLB priority company")
            return min(score, 95), reasons

    if DATA_ADJACENT_TITLE.search(title):
        data_skills = _phrases(body, DATA_SKILLS)
        if len(data_skills) >= 2:
            score = 65 + min(20, len(data_skills) * 5)
            reasons = [
                "Bangalore/Bengaluru or Remote India",
                "resume lane: data engineering/data science",
                "resume skills: " + ", ".join(data_skills[:6]),
            ]
            if early:
                score += 10
                reasons.append("early-career signal")
            if job.wlb_score >= 4:
                score += 5
                reasons.append("higher WLB priority company")
            return min(score, 95), reasons

    return 0, ["role lacks enough evidence for a resume-aligned adjacent lane"]


def resume_score_job(job: bot.Job, settings: dict[str, Any]) -> tuple[int, list[str]]:
    """Keep proven data/AI decisions, then evaluate the adjacent resume lane."""
    score, reasons = precision.precision_score_job(job, settings)
    if score:
        return score, reasons
    adjacent_score, adjacent_reasons = _resume_lane(job, settings)
    if adjacent_score:
        return adjacent_score, adjacent_reasons
    return 0, adjacent_reasons or reasons
