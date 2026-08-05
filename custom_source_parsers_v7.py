"""Production Workday facet parser with multi-location coverage."""
from __future__ import annotations

import time
from typing import Any

import custom_source_parsers_v6 as previous
import job_match_expanded as expanded
import job_monitor as bot


BASE_CUSTOM_FETCH = previous.fetch_company_jobs_with_custom_v6


def _is_multi_location_label(location: str) -> bool:
    return location.casefold() in {"2 locations", "3 locations", "4 locations"}


def parse_workday_faceted_complete(company: dict[str, Any]) -> list[bot.Job]:
    """Search verified Workday facets without losing shared-location jobs."""
    terms = company.get("search_terms") or ["data", "machine learning", "AI", "analytics"]
    facets = company.get("applied_facets") or {}
    page_size = 20
    max_results = max(page_size, int(company.get("max_results_per_term", 60)))
    career_url = company["career_site_url"].rstrip("/")
    facet_location = str(company.get("facet_location_label") or "Bangalore, India")
    by_path: dict[str, bot.Job] = {}
    multi_location_paths: set[str] = set()

    for term in terms:
        for offset in range(0, max_results, page_size):
            data = bot.get_json(
                company["url"],
                method="POST",
                payload={
                    "appliedFacets": facets,
                    "limit": page_size,
                    "offset": offset,
                    "searchText": term,
                },
            )
            raw_jobs = data.get("jobPostings") or []
            if not raw_jobs:
                break
            for item in raw_jobs:
                path = str(item.get("externalPath") or item.get("url") or "")
                if not path or path in by_path:
                    continue
                location = bot.flatten_location(item.get("locationsText") or item.get("location"))
                if _is_multi_location_label(location):
                    # These results were selected by verified Bangalore facet IDs.
                    # Workday hides the matching city when it displays "N Locations".
                    location = f"{facet_location} (multi-location)"
                    multi_location_paths.add(path)
                url = career_url + path if path.startswith("/") else path
                by_path[path] = bot.Job(
                    company=company["name"],
                    title=bot.clean_text(item.get("title")),
                    location=location,
                    url=url,
                    source="Official careers: Workday",
                    description=bot.clean_text(item.get("bulletFields") or item.get("jobDescription")),
                    department=bot.clean_text(item.get("jobFamily")),
                    wlb_score=company.get("wlb_score", 4),
                )
            try:
                total = int(data.get("total") or 0)
            except (TypeError, ValueError):
                total = 0
            if len(raw_jobs) < page_size or (total and offset + len(raw_jobs) >= total):
                break
            time.sleep(0.1)

    settings = bot.load_config()["settings"]
    detail_budget = max(0, int(company.get("max_candidate_details", 20)))
    base = company["url"].rsplit("/jobs", 1)[0]
    for path, job in by_path.items():
        if detail_budget <= 0:
            break
        if not expanded.expanded_is_target_title(job.title):
            continue
        if not bot.has_location_match(job.location, settings):
            continue
        try:
            detail = bot.get_json(base + path)
            info = detail.get("jobPostingInfo") or {}
            job.description = bot.clean_text(info.get("jobDescription")) or job.description
            job.department = bot.clean_text(
                info.get("jobFamily") or info.get("jobRequisitionLocation")
            ) or job.department
            detail_location = bot.flatten_location(
                info.get("location") or info.get("jobRequisitionLocation")
            )
            if path not in multi_location_paths and detail_location:
                job.location = detail_location
            detail_budget -= 1
        except Exception as exc:
            print(f"WARN {company['name']} Workday detail failed: {exc}")
    return list(by_path.values())


def fetch_company_jobs_with_custom_v7(company: dict[str, Any]) -> list[bot.Job]:
    if company.get("ats") != "workday_faceted":
        return BASE_CUSTOM_FETCH(company)
    try:
        jobs = parse_workday_faceted_complete(company)
        print(f"{company['name']}: {len(jobs)} raw jobs from workday_faceted")
        return jobs
    except Exception as exc:
        print(f"WARN {company['name']} failed: {exc}")
        bot.SCAN_ERRORS.append(company["name"])
        return []
