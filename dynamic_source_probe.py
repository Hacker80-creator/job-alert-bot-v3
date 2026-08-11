"""Inspect unresolved dynamic career pages in parallel without enabling guesses."""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup

import audit_dynamic_coverage as audit
import job_monitor as bot
import job_monitor_entry_v43


ROOT = Path(__file__).parent
PROVIDER_URL = re.compile(
    r"https?://[^\"'<> ]*(?:greenhouse|lever|ashby|workday|darwinbox|"
    r"ripplehire|jobvite|smartrecruiters|successfactors|eightfold|gem\.com|"
    r"param\.ai|turbohire|freshteam|icims|jibecdn|openings\.co|jobs\.deel\.com)"
    r"[^\"'<> ]*",
    re.IGNORECASE,
)
TARGET_TERMS = (
    "data", "analytics", "analyst", "scientist", "machine learning",
    "artificial intelligence", " ai ", " ml ",
)
JOB_MARKERS = ("job", "career", "opening", "opportunit", "position", "apply")


def dynamic_remaining() -> list[dict[str, Any]]:
    document = yaml.safe_load(
        (ROOT / "career_source_runtime_status.yaml").read_text(encoding="utf-8")
    )
    dynamic = [
        item for item in document["companies"]
        if item.get("status") == "DYNAMIC"
        or (
            item.get("status") == "REDIRECT"
            and item.get("resolved_status") == "DYNAMIC"
        )
    ]
    labels = {
        audit.normalized(label)
        for company in job_monitor_entry_v43.load_final_config()["companies"]
        if company.get("enabled", True)
        for label in [company["name"], *company.get("aliases", [])]
    }
    return [item for item in dynamic if audit.normalized(item["name"]) not in labels]


def _jobposting_count(soup: BeautifulSoup) -> int:
    count = 0
    for node in soup.find_all("script", type="application/ld+json"):
        text = node.string or node.get_text()
        count += len(re.findall(r'"@type"\s*:\s*"JobPosting"', text, re.IGNORECASE))
    return count


def probe(item: dict[str, Any]) -> dict[str, Any]:
    name = str(item["name"])
    requested_url = str(item.get("final_url") or item.get("source_url") or "")
    result: dict[str, Any] = {
        "name": name,
        "requested_url": requested_url,
        "status": "ERROR",
        "provider_urls": [],
        "candidate_links": [],
        "target_links": [],
        "jobposting_count": 0,
    }
    try:
        response = requests.get(
            requested_url,
            headers={**bot.HEADERS, "Accept": "text/html,application/xhtml+xml"},
            timeout=(8, 30),
        )
        result.update({
            "http_status": response.status_code,
            "final_url": response.url,
            "bytes": len(response.content),
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        result["provider_urls"] = list(dict.fromkeys(
            match.rstrip("\\") for match in PROVIDER_URL.findall(response.text)
        ))[:12]
        result["jobposting_count"] = _jobposting_count(soup)
        candidates: list[dict[str, str]] = []
        targets: list[dict[str, str]] = []
        for node in soup.find_all("a", href=True):
            href = urljoin(response.url, str(node.get("href") or ""))
            label = bot.clean_text(node.get_text(" "))
            folded = f" {label} {href} ".casefold()
            if any(marker in folded for marker in JOB_MARKERS):
                candidates.append({"label": label[:120], "url": href[:400]})
            if (
                any(term in folded for term in TARGET_TERMS)
                and any(marker in href.casefold() for marker in JOB_MARKERS)
            ):
                targets.append({"label": label[:160], "url": href[:400]})
        result["candidate_links"] = list({row["url"]: row for row in candidates}.values())[:20]
        result["target_links"] = list({row["url"]: row for row in targets}.values())[:10]
        result["status"] = "INSPECTED"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def run(batch_index: int, batch_size: int, workers: int, output: Path) -> int:
    remaining = dynamic_remaining()
    start = batch_index * batch_size
    batch = remaining[start:start + batch_size]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(probe, item): item["name"] for item in batch}
        for future in as_completed(futures):
            result = future.result()
            print(
                f"{result['status']} {result['name']}: "
                f"providers={len(result['provider_urls'])} "
                f"targets={len(result['target_links'])} "
                f"jobposting={result['jobposting_count']}",
                flush=True,
            )
            results.append(result)
    order = {item["name"]: index for index, item in enumerate(batch)}
    results.sort(key=lambda item: order[item["name"]])
    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_index": batch_index,
        "batch_size": batch_size,
        "total_remaining": len(remaining),
        "requested": len(batch),
        "inspected": sum(item["status"] == "INSPECTED" for item in results),
        "errors": sum(item["status"] == "ERROR" for item in results),
        "results": results,
    }
    output.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(
        "DYNAMIC_PROBE_SUMMARY "
        f"requested={document['requested']} inspected={document['inspected']} "
        f"errors={document['errors']} total_remaining={document['total_remaining']}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-index", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "dynamic_source_probe.summary.json",
    )
    args = parser.parse_args()
    return run(args.batch_index, args.batch_size, args.workers, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
