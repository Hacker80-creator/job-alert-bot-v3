"""Final production matching guardrails layered over expanded role matching."""
from __future__ import annotations

import re
from typing import Any

import job_match_expanded as expanded
import job_monitor as bot


def reject_extended_experience(title: str, description: str, settings: dict[str, Any]) -> tuple[bool, str]:
    rejected, reason = bot.reject_by_seniority(title, description, settings)
    if rejected:
        return rejected, reason

    text = bot.normalize_match_text(f"{title} {description}")
    # ATS descriptions often write "year(s)", which normalizes to "year s".
    # Reject only when the stated minimum itself exceeds the 0-3 YOE target;
    # a broad 2-5 band can still legitimately accept a two-year candidate.
    minimum = re.search(
        r"\b(?:minimum|min|at least|requires?|required)\s+(\d+(?:\.\d+)?)\s*(?:plus\s+)?year(?:s|\s+s)?\b",
        text,
    )
    if minimum and float(minimum.group(1)) >= 4:
        return True, f"experience minimum too high: {minimum.group(1)} years"

    plus = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:plus|\+)\s*year(?:s|\s+s)?\b", text)
    if plus and float(plus.group(1)) >= 4:
        return True, f"experience minimum too high: {plus.group(1)}+ years"
    return False, ""


def production_score_job(job: bot.Job, settings: dict[str, Any]) -> tuple[int, list[str]]:
    rejected, reason = reject_extended_experience(job.title, job.description, settings)
    if rejected:
        return 0, [reason]
    return expanded.expanded_score_job(job, settings)
