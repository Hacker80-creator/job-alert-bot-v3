"""Production entry point for the parallel, generated-source-aware monitor."""
from __future__ import annotations

from typing import Any

import job_monitor as bot
import job_monitor_parallel


def parse_lever_with_region(company: dict[str, Any]) -> list[bot.Job]:
    api_host = company.get("api_host", "api.lever.co")
    url = f"https://{api_host}/v0/postings/{company['slug']}?mode=json"
    data = bot.get_json(url)
    jobs: list[bot.Job] = []
    for item in data:
        categories = item.get("categories", {}) or {}
        description = " ".join([
            bot.clean_text(item.get("description")),
            bot.clean_text(item.get("descriptionPlain")),
            bot.clean_text(item.get("lists")),
        ])
        jobs.append(bot.Job(
            company=company["name"],
            title=bot.clean_text(item.get("text")),
            location=bot.flatten_location(categories.get("location")),
            url=item.get("hostedUrl") or item.get("applyUrl") or "",
            source="Official careers: Lever",
            description=description,
            department=bot.clean_text(categories.get("department")),
            wlb_score=company.get("wlb_score", 3),
        ))
    return jobs


if __name__ == "__main__":
    # fetch_company_jobs resolves parser functions from the job_monitor module
    # at call time, so this adds Lever's EU public host without changing v3.
    bot.parse_lever = parse_lever_with_region
    raise SystemExit(job_monitor_parallel.run())
