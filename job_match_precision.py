"""Precision guardrails for adjacent early-career data and AI roles.

The broad matcher deliberately fetches generic titles so roles such as
"Engineer - AI Orchestration" are not missed.  This layer makes the final
decision conservative: adjacent roles must be data/AI work, not merely a
support or general software job whose company boilerplate mentions AI.
"""
from __future__ import annotations

import re
from typing import Any

import job_match_expanded as expanded
import job_match_production as production
import job_monitor as bot


EXCLUDED_ADJACENT_TITLE = re.compile(
    r"\b(?:technical support|support engineer|customer engineer|customer success|"
    r"technical services|application engineer|solutions? engineer|full[ -]?stack|"
    r"front[ -]?end|back[ -]?end|integrations? engineer|devops engineer|site reliability)\b",
    re.IGNORECASE,
)
DOMAIN_IN_TITLE = re.compile(
    r"\b(?:data|analytics?|machine learning|artificial intelligence|generative ai|"
    r"genai|ai|ml|llm|nlp|computer vision|deep learning|applied science|"
    r"decision science|business intelligence)\b",
    re.IGNORECASE,
)
STRONG_BODY_DOMAINS = (
    "data engineering",
    "data science",
    "data analytics",
    "machine learning",
    "artificial intelligence",
    "generative ai",
    "deep learning",
    "natural language processing",
    "computer vision",
    "business intelligence",
    "process mining",
    "process intelligence",
    "predictive model",
    "large language model",
    "ai orchestration",
)
CORE_PROFILE_SKILLS = (
    "python",
    "sql",
    "pandas",
    "numpy",
    "scikit",
    "pytorch",
    "tensorflow",
    "spark",
    "databricks",
    "airflow",
    "tableau",
    "power bi",
    "statistics",
)
EARLY_ROLE = re.compile(
    r"\b(?:entry[ -]?level|early[ -]?career|new grad|graduate role|associate|"
    r"0\s*(?:-|to)\s*[23]|1\s*(?:-|to|\+)\s*[123]?|2\s*(?:-|to|\+)\s*[35]?)\b",
    re.IGNORECASE,
)
ROLE_LEVEL_SENIOR = re.compile(
    r"\b(?:seeking|looking for|hiring)\s+(?:an?\s+)?senior\b",
    re.IGNORECASE,
)
NON_TARGET_CITY_IN_TITLE = re.compile(
    r"\b(?:based|located)\s+in\s+(?:hyderabad|pune|chennai|mumbai|gurgaon|"
    r"gurugram|noida|delhi|kolkata)\b",
    re.IGNORECASE,
)


def precision_score_job(job: bot.Job, settings: dict[str, Any]) -> tuple[int, list[str]]:
    """Score precise roles normally and apply stricter gates to broad titles."""
    if NON_TARGET_CITY_IN_TITLE.search(job.title or ""):
        return 0, ["title requires a non-target city rather than Remote India"]

    rejected, reason = production.reject_extended_experience(
        job.title, job.description, settings
    )
    if rejected:
        return 0, [reason]

    # Existing explicit data/AI/analytics titles remain governed by the proven
    # base matcher. The gates below only apply to newly broadened titles.
    if expanded.bot_original_is_target_title(job.title):
        return production.production_score_job(job, settings)

    if not expanded.is_generic_technical_title(job.title):
        return 0, ["title does not match a target or adjacent technical role"]
    if EXCLUDED_ADJACENT_TITLE.search(job.title or ""):
        return 0, ["adjacent title belongs to support/general application engineering"]

    opening = bot.clean_text(job.description)[:1200]
    if ROLE_LEVEL_SENIOR.search(opening):
        return 0, ["description identifies the role itself as senior"]

    score, reasons = expanded.expanded_score_job(job, settings)
    if not score:
        return score, reasons

    title_has_domain = bool(DOMAIN_IN_TITLE.search(job.title or ""))
    if title_has_domain:
        return score, reasons

    body = bot.normalize_match_text(job.description)
    domains = [value for value in STRONG_BODY_DOMAINS if value in body]
    skills = [value for value in CORE_PROFILE_SKILLS if value in body]
    early = bool(EARLY_ROLE.search(body))

    # For a title with no data/AI wording, require evidence from the actual
    # description that closely overlaps the candidate's profile. This keeps
    # Accenture data-engineering and Celonis process-intelligence roles while
    # rejecting generic C++/DevOps/software roles with a passing AI mention.
    strong_stack = len(skills) >= 3 and any(
        value in domains
        for value in ("data engineering", "data science", "data analytics", "business intelligence")
    )
    early_adjacent = early and len(domains) >= 1 and len(skills) >= 2
    if not (strong_stack or early_adjacent):
        return 0, ["generic title lacks enough profile-specific data/AI evidence"]

    reasons = list(reasons) + ["generic title passed strict profile-overlap check"]
    return min(score, 85), reasons
