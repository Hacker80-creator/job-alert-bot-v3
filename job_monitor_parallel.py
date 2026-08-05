"""Parallel source-fetching entry point with generated ATS source support.

Network collection is parallel. Discord posting and seen-state persistence are
delegated to job_monitor.main and therefore remain serialized.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

import job_monitor as bot


ROOT = Path(__file__).parent
DISCOVERED_FILE = ROOT / "discovered_sources.yaml"
SOURCE_WORKERS = max(1, int(os.getenv("MAX_SOURCE_WORKERS", "10")))


def load_merged_config() -> dict[str, Any]:
    config = yaml.safe_load(bot.CONFIG_FILE.read_text(encoding="utf-8"))
    if not DISCOVERED_FILE.exists():
        return config
    discovered = yaml.safe_load(DISCOVERED_FILE.read_text(encoding="utf-8")) or {}
    existing = {str(item["name"]).casefold() for item in config.get("companies", [])}
    for source in discovered.get("companies", []):
        name_key = str(source.get("name", "")).casefold()
        if name_key and name_key not in existing:
            config.setdefault("companies", []).append(source)
            existing.add(name_key)
    return config


def parse_workable(company: dict[str, Any]) -> list[bot.Job]:
    url = company.get("url") or f"https://www.workable.com/api/accounts/{company['slug']}?details=true"
    data = bot.get_json(url)
    raw_jobs = data.get("jobs", []) if isinstance(data, dict) else []
    jobs: list[bot.Job] = []
    for item in raw_jobs:
        salary = item.get("salary") or {}
        salary_text = ""
        if isinstance(salary, dict) and (salary.get("salary_from") or salary.get("salary_to")):
            salary_text = " ".join(str(value) for value in (
                salary.get("salary_currency"), salary.get("salary_from"), salary.get("salary_to")
            ) if value is not None)
        jobs.append(bot.Job(
            company=company["name"],
            title=bot.clean_text(item.get("title") or item.get("full_title")),
            location=bot.flatten_location(item.get("location") or item.get("locations")),
            url=item.get("url") or item.get("shortlink") or item.get("application_url") or "",
            source="Official careers: Workable",
            description=bot.clean_text(item.get("description") or item.get("description_html")),
            department=bot.clean_text(item.get("department")),
            salary_text=salary_text,
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def parse_recruitee(company: dict[str, Any]) -> list[bot.Job]:
    url = company.get("url") or f"https://{company['slug']}.recruitee.com/api/offers/"
    data = bot.get_json(url)
    raw_jobs = data.get("offers", []) if isinstance(data, dict) else []
    jobs: list[bot.Job] = []
    for item in raw_jobs:
        location = item.get("location") or item.get("locations") or [
            item.get("city"), item.get("state"), item.get("country"),
        ]
        jobs.append(bot.Job(
            company=company["name"],
            title=bot.clean_text(item.get("title")),
            location=bot.flatten_location(location),
            url=item.get("careers_url") or item.get("careers_apply_url") or item.get("url") or "",
            source="Official careers: Recruitee",
            description=bot.clean_text(item.get("description") or item.get("description_html")),
            department=bot.clean_text(item.get("department")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


def run() -> int:
    config = load_merged_config()
    original_fetch = bot.fetch_company_jobs

    # Some existing parsers call load_config for filter settings. Point them at
    # the same merged object for the whole run.
    bot.load_config = lambda: config
    bot.SCAN_ERRORS.clear()

    def fetch(company: dict[str, Any]) -> list[bot.Job]:
        if not company.get("enabled", True):
            return []
        parser = {
            "workable": parse_workable,
            "recruitee": parse_recruitee,
        }.get(company.get("ats"))
        if parser is None:
            return original_fetch(company)
        try:
            jobs = parser(company)
            print(f"{company['name']}: {len(jobs)} raw jobs from {company['ats']}")
            return jobs
        except Exception as exc:
            print(f"WARN {company['name']} failed: {exc}")
            bot.SCAN_ERRORS.append(company["name"])
            return []

    cached: dict[str, list[bot.Job]] = {}
    with ThreadPoolExecutor(max_workers=SOURCE_WORKERS) as pool:
        futures = {pool.submit(fetch, company): company for company in config["companies"]}
        for future in as_completed(futures):
            company = futures[future]
            key = str(company["name"]).casefold()
            try:
                cached[key] = future.result()
            except Exception as exc:
                print(f"WARN {company['name']} parallel worker failed: {exc}")
                bot.SCAN_ERRORS.append(company["name"])
                cached[key] = []

    prefetch_errors = set(bot.SCAN_ERRORS)

    def cached_fetch(company: dict[str, Any]) -> list[bot.Job]:
        if company["name"] in prefetch_errors and company["name"] not in bot.SCAN_ERRORS:
            bot.SCAN_ERRORS.append(company["name"])
        return cached.get(str(company["name"]).casefold(), [])

    # main() clears SCAN_ERRORS, then performs serialized Discord delivery and
    # immediate state writes using these already-fetched results.
    bot.fetch_company_jobs = cached_fetch
    return bot.main()


if __name__ == "__main__":
    raise SystemExit(run())
