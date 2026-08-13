"""Live-test a feature-branch source batch without alerts or state writes."""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import custom_source_parsers_v30
import job_match_expanded as expanded
import job_monitor as bot
import job_monitor_entry
import job_monitor_entry_v44
import job_monitor_parallel
import source_registry_v44


ROOT = Path(__file__).parent


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
    return {
        "name": company["name"],
        "status": "WORKING" if jobs else "NO_CURRENT_MATCHING_JOBS",
        "job_count": len(jobs),
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
        f"failed={summary['failed']} missing={len(missing)} disabled={len(disabled)}"
    )
    return 1 if summary["failed"] or missing or disabled else 0


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
