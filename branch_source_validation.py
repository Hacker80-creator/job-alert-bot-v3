"""Live-test a feature-branch source batch without alerts or state writes."""
from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import custom_source_parsers_v30
import job_match_expanded as expanded
import job_monitor as bot
import job_monitor_entry
import job_monitor_entry_v44
import job_monitor_parallel
import source_registry_v44


ROOT = Path(__file__).parent

GENERIC_JOB_LABELS = {
    "all jobs", "apply", "careers", "career opportunities", "find jobs",
    "job search", "jobs", "open positions", "open roles", "opportunities",
    "search jobs", "see jobs", "view jobs", "view open roles",
}
NO_OPENINGS_PATTERN = re.compile(
    r"\b(?:currently\s+)?(?:have\s+)?no\s+(?:current\s+|open\s+)?"
    r"(?:jobs?|openings?|positions?|roles?|vacancies)\b",
    re.IGNORECASE,
)
JOB_DETAIL_PATH = re.compile(
    r"/(?:jobs?|careers?|positions?|openings?|opportunities?|requisitions?)"
    r"/(?!search(?:[/?#]|$)|all(?:[/?#]|$)|locations?(?:[/?#]|$)|"
    r"categories(?:[/?#]|$))[^/?#]+",
    re.IGNORECASE,
)
JOB_DETAIL_QUERY = re.compile(
    r"(?:[?&](?:job_?id|job|position_?id|requisition_?id)=)[^&#]+",
    re.IGNORECASE,
)


def assess_direct_source(company: dict[str, Any]) -> dict[str, Any]:
    """Prove an HTML source exposes job records or an explicit empty state."""
    response = requests.get(
        company["url"],
        headers=custom_source_parsers_v30.BROWSER_HEADERS,
        timeout=40,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    visible_text = bot.clean_text(soup.get_text(" "))
    if NO_OPENINGS_PATTERN.search(visible_text):
        return {"monitorable": True, "evidence": "explicit_no_openings"}

    jobposting_count = 0
    for script in soup.find_all("script", type="application/ld+json"):
        jobposting_count += len(re.findall(
            r'"@type"\s*:\s*"JobPosting"', script.string or script.get_text(),
            flags=re.IGNORECASE,
        ))
    if jobposting_count:
        return {
            "monitorable": True,
            "evidence": "jobposting_jsonld",
            "record_count": jobposting_count,
        }

    job_links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        label = bot.clean_text(anchor.get_text(" "))
        if not label or len(label) > 180 or label.casefold() in GENERIC_JOB_LABELS:
            continue
        href = urljoin(response.url, str(anchor.get("href") or ""))
        parsed = urlparse(href)
        candidate = f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
        if JOB_DETAIL_PATH.search(candidate) or JOB_DETAIL_QUERY.search(candidate):
            job_links.append(href)
    if job_links:
        return {
            "monitorable": True,
            "evidence": "server_rendered_job_links",
            "record_count": len(set(job_links)),
        }
    return {"monitorable": False, "evidence": "no_verifiable_job_records"}


def source_names(path: Path) -> list[str]:
    return [
        company["name"]
        for company in source_registry_v44.build_source_overrides(path)
        if company.get("enabled", True)
    ]


def validate_source(company: dict[str, Any]) -> dict[str, Any]:
    jobs: list[bot.Job] = []
    last_error = ""
    swallowed_error = False
    for attempt in range(3):
        prior_errors = sum(
            company["name"].casefold() in error.casefold()
            for error in bot.SCAN_ERRORS
        )
        try:
            parser = {
                "workable": job_monitor_parallel.parse_workable,
                "recruitee": job_monitor_parallel.parse_recruitee,
            }.get(company.get("ats"))
            jobs = (
                parser(company)
                if parser is not None
                else custom_source_parsers_v30.fetch_company_jobs_with_custom_v30(company)
            )
        except Exception as exc:  # Defensive: custom adapters normally contain errors.
            last_error = f"{type(exc).__name__}: {exc}"
        current_errors = sum(
            company["name"].casefold() in error.casefold()
            for error in bot.SCAN_ERRORS
        )
        swallowed_error = current_errors > prior_errors
        if jobs or (not swallowed_error and not last_error):
            break
        if attempt < 2:
            time.sleep(2 ** attempt)
            last_error = ""
    if not jobs and (last_error or swallowed_error):
        return {
            "name": company["name"],
            "status": "FAILED",
            "job_count": 0,
            "error": last_error or "production adapter failed after 3 attempts",
        }
    direct_assessment: dict[str, Any] = {}
    if not jobs and company.get("ats") == "direct_job_html":
        try:
            direct_assessment = assess_direct_source(company)
        except Exception as exc:
            direct_assessment = {
                "monitorable": False,
                "evidence": f"health_probe_failed: {type(exc).__name__}: {exc}",
            }
    empty_status = "NO_CURRENT_MATCHING_JOBS"
    if direct_assessment and not direct_assessment["monitorable"]:
        empty_status = "UNRESOLVED_DYNAMIC_SOURCE"
    return {
        "name": company["name"],
        "status": "WORKING" if jobs else empty_status,
        "job_count": len(jobs),
        **({"monitor_evidence": direct_assessment} if direct_assessment else {}),
        "sample_jobs": [
            {
                "title": job.title,
                "location": job.location,
                "url": job.url,
            }
            for job in jobs[:3]
        ],
    }


def run(overrides_file: Path, output: Path, workers: int) -> int:
    bot.parse_workday_search = expanded.parse_workday_with_generic_details
    bot.parse_smartrecruiters = expanded.parse_smartrecruiters_with_generic_details
    bot.parse_lever = job_monitor_entry.parse_lever_with_region
    bot.SCAN_ERRORS.clear()

    companies = {
        company["name"]: company
        for company in job_monitor_entry_v44.load_final_config()["companies"]
    }
    names = source_names(overrides_file)
    missing = [name for name in names if name not in companies]
    disabled = [
        name for name in names
        if name in companies and not companies[name].get("enabled", True)
    ]
    results: list[dict[str, Any]] = []
    selected = [companies[name] for name in names if name in companies and name not in disabled]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(validate_source, company): company["name"] for company in selected}
        for future in as_completed(futures):
            result = future.result()
            if result["status"] == "NO_CURRENT_MATCHING_JOBS":
                print(
                    f"NO_CURRENT_MATCHING_JOBS {result['name']}: "
                    "source completed successfully",
                    flush=True,
                )
            elif result["status"] == "UNRESOLVED_DYNAMIC_SOURCE":
                print(
                    f"UNRESOLVED_DYNAMIC_SOURCE {result['name']}: "
                    "generic page returned no verifiable job records",
                    flush=True,
                )
            else:
                print(
                    f"{result['status']} {result['name']}: "
                    f"{result['job_count']} raw jobs",
                    flush=True,
                )
            results.append(result)

    results.sort(key=lambda item: item["name"].casefold())
    summary = {
        "requested": len(names),
        "completed": len(results),
        "working": sum(item["status"] == "WORKING" for item in results),
        "no_current_matching_jobs": sum(
            item["status"] == "NO_CURRENT_MATCHING_JOBS" for item in results
        ),
        "unresolved_dynamic_sources": sum(
            item["status"] == "UNRESOLVED_DYNAMIC_SOURCE" for item in results
        ),
        "failed": sum(item["status"] == "FAILED" for item in results),
        "missing": missing,
        "disabled": disabled,
        "results": results,
    }
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        "BRANCH_SOURCE_SUMMARY "
        f"requested={summary['requested']} completed={summary['completed']} "
        f"working={summary['working']} "
        f"no_current_matching_jobs={summary['no_current_matching_jobs']} "
        f"unresolved_dynamic_sources={summary['unresolved_dynamic_sources']} "
        f"failed={summary['failed']} missing={len(missing)} disabled={len(disabled)}"
    )
    return 1 if (
        summary["failed"]
        or summary["unresolved_dynamic_sources"]
        or missing
        or disabled
    ) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--overrides-file", type=Path,
        default=ROOT / "verified_sources_v44.txt",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "branch_source_validation.summary.json",
    )
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    return run(args.overrides_file, args.output, args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
