"""Discover verified public ATS feeds in 25-company GitHub Actions batches."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
import yaml


ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "companies.yaml"
DISCOVERED_FILE = ROOT / "discovered_sources.yaml"
ALLOWLIST_FILE = ROOT / "company_allowlist.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JobAlertSourceDiscovery/1.0; +https://github.com/)",
    "Accept": "application/json,text/plain,*/*",
}
TIMEOUT = (5, 10)


def normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_value.casefold())


def brand_words(value: str) -> set[str]:
    ignored = {
        "careers", "career", "jobs", "job", "at", "the", "company", "companies",
        "inc", "ltd", "limited", "llc", "corp", "corporation", "group", "holdings",
        "technology", "technologies", "software", "solutions", "services", "systems",
        "global", "international", "india", "private", "pvt",
    }
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return {word for word in re.findall(r"[a-z0-9]+", ascii_value.casefold()) if word not in ignored}


def identity_matches(expected: str, actual: str) -> bool:
    expected_norm = normalize(expected)
    actual_norm = normalize(actual)
    if not expected_norm or not actual_norm:
        return False
    if expected_norm == actual_norm:
        return True
    expected_words = brand_words(expected)
    actual_words = brand_words(actual)
    if expected_words and actual_words and expected_words == actual_words:
        return True
    # Labels such as "Careers at Datadog" are fine. Short brands require an
    # exact match so Box, Meta, Arm, SAP, etc. cannot collide with other boards.
    return len(expected_norm) >= 6 and expected_norm in actual_norm


def slug_candidates(name: str) -> list[str]:
    raw = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    raw = re.sub(r"\([^)]*\)", " ", raw).replace("&", " and ")
    words = re.findall(r"[A-Za-z0-9]+", raw)
    candidates = ["".join(words).lower(), "-".join(words).lower()]
    suffixes = {
        "india", "global", "group", "holdings", "limited", "ltd", "inc", "corp",
        "corporation", "technology", "technologies", "software", "solutions", "services",
    }
    trimmed = list(words)
    while len(trimmed) > 1 and trimmed[-1].casefold() in suffixes:
        trimmed.pop()
    if trimmed != words:
        candidates.extend(("".join(trimmed).lower(), "-".join(trimmed).lower()))
    candidates.append("".join(words))  # Some Ashby boards preserve case.
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))[:5]


def get_json(session: requests.Session, url: str) -> Any:
    response = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    return response.json()


def probe_greenhouse(session: requests.Session, name: str, slug: str) -> dict[str, Any] | None:
    metadata = get_json(session, f"https://boards-api.greenhouse.io/v1/boards/{slug}")
    board_name = str(metadata.get("name") or "")
    if not identity_matches(name, board_name):
        return None
    jobs = get_json(session, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if not isinstance(jobs.get("jobs"), list):
        return None
    return {
        "ats": "greenhouse", "slug": slug,
        "verified_job_count": len(jobs["jobs"]), "verified_name": board_name,
    }


def probe_lever(session: requests.Session, name: str, slug: str, *, eu: bool = False) -> dict[str, Any] | None:
    host = "api.eu.lever.co" if eu else "api.lever.co"
    jobs = get_json(session, f"https://{host}/v0/postings/{slug}?mode=json")
    if not isinstance(jobs, list) or not jobs:
        return None
    hosted_urls = [str(job.get("hostedUrl") or "") for job in jobs[:10]]
    if not any(f"/{slug}/" in url or url.rstrip("/").endswith(f"/{slug}") for url in hosted_urls):
        return None
    result: dict[str, Any] = {"ats": "lever", "slug": slug, "verified_job_count": len(jobs)}
    if eu:
        result["api_host"] = "api.eu.lever.co"
    return result


def probe_ashby(session: requests.Session, name: str, slug: str) -> dict[str, Any] | None:
    data = get_json(session, f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return None
    if jobs:
        urls = [str(job.get("jobUrl") or job.get("applyUrl") or "") for job in jobs[:10]]
        if not any(slug.casefold() in url.casefold() for url in urls):
            return None
    return {"ats": "ashby", "slug": slug, "verified_job_count": len(jobs)}


def probe_smartrecruiters(session: requests.Session, name: str, slug: str) -> dict[str, Any] | None:
    data = get_json(session, f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=10")
    jobs = data.get("content") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return None
    labels = {
        str((job.get("company") or {}).get("name") or "")
        for job in jobs if isinstance(job.get("company"), dict)
    }
    labels.discard("")
    if labels and not any(identity_matches(name, label) for label in labels):
        return None
    if not jobs and not identity_matches(name, slug):
        return None
    return {
        "ats": "smartrecruiters", "slug": slug,
        "verified_job_count": int(data.get("totalFound") or len(jobs)),
    }


def probe_workable(session: requests.Session, name: str, slug: str) -> dict[str, Any] | None:
    url = f"https://www.workable.com/api/accounts/{slug}?details=true"
    data = get_json(session, url)
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return None
    actual = str(data.get("name") or data.get("company_name") or slug)
    if not identity_matches(name, actual):
        return None
    return {
        "ats": "workable", "slug": slug, "url": url,
        "verified_job_count": len(jobs), "verified_name": actual,
    }


def probe_recruitee(session: requests.Session, name: str, slug: str) -> dict[str, Any] | None:
    url = f"https://{slug}.recruitee.com/api/offers/"
    data = get_json(session, url)
    jobs = data.get("offers") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return None
    company = data.get("company") or data.get("company_name")
    actual = str(company.get("name") if isinstance(company, dict) else company or slug)
    if not identity_matches(name, actual):
        return None
    return {
        "ats": "recruitee", "slug": slug, "url": url,
        "verified_job_count": len(jobs), "verified_name": actual,
    }


PROBES: list[tuple[str, Callable[..., dict[str, Any] | None]]] = [
    ("greenhouse", probe_greenhouse),
    ("lever", probe_lever),
    ("lever_eu", lambda session, name, slug: probe_lever(session, name, slug, eu=True)),
    ("ashby", probe_ashby),
    ("smartrecruiters", probe_smartrecruiters),
    ("workable", probe_workable),
    ("recruitee", probe_recruitee),
]


def discover_company(name: str) -> dict[str, Any]:
    session = requests.Session()
    attempts = 0
    errors: list[str] = []
    for provider, probe in PROBES:
        for slug in slug_candidates(name):
            attempts += 1
            try:
                found = probe(session, name, slug)
                if found:
                    found.update({"name": name, "kind": "product", "wlb_score": 3, "enabled": True})
                    return {"name": name, "status": "verified", "attempts": attempts, "source": found}
            except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
                if len(errors) < 3 and not isinstance(exc, requests.HTTPError):
                    errors.append(f"{provider}/{slug}: {type(exc).__name__}")
    return {"name": name, "status": "unresolved", "attempts": attempts, "errors": errors}


def read_discovered() -> dict[str, Any]:
    if not DISCOVERED_FILE.exists():
        return {"metadata": {}, "companies": []}
    return yaml.safe_load(DISCOVERED_FILE.read_text(encoding="utf-8")) or {"metadata": {}, "companies": []}


def approved_unconfigured_names() -> list[str]:
    config = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    configured = {str(item["name"]).casefold() for item in config.get("companies", [])}
    configured.update(str(item["name"]).casefold() for item in read_discovered().get("companies", []))
    names = {
        line.strip() for line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return sorted((name for name in names if name.casefold() not in configured), key=str.casefold)


def run_batch(batch_index: int, batch_size: int, workers: int) -> dict[str, Any]:
    all_names = approved_unconfigured_names()
    names = all_names[batch_index * batch_size:(batch_index + 1) * batch_size]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(discover_company, name): name for name in names}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # A single company must not fail its matrix shard.
                result = {"name": name, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            print(f"{result['status'].upper()}: {name}", flush=True)
            results.append(result)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_index": batch_index,
        "batch_size": batch_size,
        "total_unconfigured": len(all_names),
        "results": sorted(results, key=lambda item: item["name"].casefold()),
    }


def merge_results(input_dir: Path, output: Path, expected_parts: int | None = None) -> None:
    part_paths = sorted(input_dir.rglob("part-*.json"))
    parts = [json.loads(path.read_text(encoding="utf-8")) for path in part_paths]
    if expected_parts is not None:
        indexes = {int(part["batch_index"]) for part in parts}
        missing = sorted(set(range(expected_parts)) - indexes)
        if missing:
            raise RuntimeError(f"Refusing partial merge; missing batch artifacts: {missing}")

    existing = read_discovered()
    verified_by_name = {
        str(source["name"]).casefold(): source for source in existing.get("companies", [])
    }
    unresolved: set[str] = set()
    results = [result for part in parts for result in part.get("results", [])]
    for result in results:
        name = str(result["name"])
        if result.get("status") == "verified":
            verified_by_name[name.casefold()] = result["source"]
        elif name.casefold() not in verified_by_name:
            unresolved.add(name)

    sources = sorted(verified_by_name.values(), key=lambda item: item["name"].casefold())
    document = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "verified_sources": len(sources),
            "unresolved_in_latest_pass": len(unresolved),
            "note": "Generated from live-verified public ATS endpoints; guessed URLs are never enabled.",
        },
        "companies": sources,
    }
    output.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    output.with_suffix(".summary.json").write_text(json.dumps({
        "verified_sources": len(sources),
        "unresolved_companies": sorted(unresolved, key=str.casefold),
    }, indent=2), encoding="utf-8")
    print(f"Merged {len(parts)} batches: {len(sources)} verified, {len(unresolved)} unresolved")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-index", type=int)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--merge-dir", type=Path)
    parser.add_argument("--expected-parts", type=int)
    args = parser.parse_args()

    if args.merge_dir:
        merge_results(args.merge_dir, args.output, args.expected_parts)
        return 0
    if args.batch_index is None:
        parser.error("--batch-index is required unless --merge-dir is used")
    result = run_batch(args.batch_index, args.batch_size, args.workers)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
