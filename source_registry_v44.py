"""Build runtime source records from the v44 verified careers catalog.

The catalog keeps the user-supplied first-party URL visible and reviewable.
This module translates well-known ATS URLs into the parser configuration used
by the scanner. Branded pages use the conservative direct-HTML adapter until
branch validation proves that a more specific adapter is required.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).parent
CATALOG_FILE = ROOT / "verified_sources_v44.txt"
DEFERRED_FILE = ROOT / "deferred_sources_v44.txt"
DEFERRED_REASONS = {
    "NO_PUBLIC_BOARD",
    "NO_RELIABLE_FEED",
    "RUNNER_BLOCKED",
    "STALE_OR_REMOVED",
}

DEFAULT_SEARCH_TERMS = [
    "data",
    "machine learning",
    "AI",
    "analytics",
    "DevOps",
    "platform",
    "automation",
]

SUCCESSFACTORS_HOSTS = {
    "careers.cipla.com",
    "careers.cargill.com",
    "careers.lupin.com",
    "jobs.heromotocorp.com",
    "jobs.kellanova.com",
    "jobs.schaeffler.com",
    "jobs.sunpharma.com",
    "jobs.volvocars.com",
}

TALENTBREW_HOSTS = {
    "careers.labcorp.com",
    "careers.mimecast.com",
    "careers.saksglobal.com",
    "careers.scopely.com",
    "careers.thomsonreuters.com",
    "jobs.baxter.com",
    "jobs.parexel.com",
}

ZOHO_PUBLIC_NAMES = {
    "GALAXEYE SPACE SOLUTIONS PRIVATE LIMITED",
    "HealthPlix Technologies",
    "InCore Semiconductors",
    "Oben Electric",
    "PlaySimple Games",
    "Qure.ai",
}

CANONICAL_PARENT = {
    "Apptio": ("IBM", ["Apptio"]),
    "Beckman Coulter": ("Danaher", ["Beckman Coulter"]),
    "Cytiva": ("Danaher", ["Cytiva"]),
    "Flutura": ("Accenture", ["Flutura"]),
    "Saankhya Labs": ("Tejas Networks", ["Saankhya Labs"]),
}


def _catalog_rows(path: Path = CATALOG_FILE) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, url = line.partition("|")
        if not separator or not name.strip() or not url.strip():
            raise ValueError(f"invalid v44 catalog line: {raw_line!r}")
        rows.append((name.strip(), url.strip()))
    return rows


def deferred_source_names(path: Path = DEFERRED_FILE) -> list[str]:
    names: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, reason = line.partition("|")
        if not separator or reason not in DEFERRED_REASONS:
            raise ValueError(f"invalid v44 deferred line: {raw_line!r}")
        names.append(name.strip())
    return names


def _workday_config(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    host = parsed.netloc
    tenant = host.split(".", 1)[0]
    site = ""
    if "recruiting" in parts:
        index = parts.index("recruiting")
        if len(parts) >= index + 3:
            tenant = parts[index + 1]
            site = parts[index + 2]
    if not site:
        meaningful = [
            part for part in parts
            if part.casefold() not in {"en", "en-us", "en_us"}
        ]
        site = meaningful[-1] if meaningful else "External"
    endpoint = f"{parsed.scheme}://{host}/wday/cxs/{tenant}/{site}/jobs"
    return {
        "ats": "workday_search",
        "url": endpoint,
        "career_site_url": url,
        "search_terms": DEFAULT_SEARCH_TERMS,
        "max_results_per_term": 40,
        "max_generic_details": 10,
    }


def _oracle_config(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    match = re.search(r"/sites/([^/?#]+)", parsed.path, flags=re.IGNORECASE)
    site_number = unquote(match.group(1)) if match else "CX"
    endpoint = (
        f"{parsed.scheme}://{parsed.netloc}"
        "/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    )
    return {
        "ats": "oracle_hcm",
        "url": endpoint,
        "career_site_url": url,
        "site_number": site_number,
        "search_terms": DEFAULT_SEARCH_TERMS,
        "max_results_per_term": 48,
    }


def classify_source(name: str, url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    host = parsed.netloc.casefold()
    path = parsed.path.strip("/")
    runtime_name, aliases = CANONICAL_PARENT.get(name, (name, []))
    company: dict[str, Any] = {
        "name": runtime_name,
        "kind": "data_product",
        "wlb_score": 3,
        "enabled": True,
        "source_status": "branch_validation_required",
    }
    if aliases:
        company["aliases"] = aliases

    if name == "Ameriprise Financial":
        company.update(
            ats="ameriprise_html",
            url=url,
            career_site_url=url,
            search_terms=DEFAULT_SEARCH_TERMS,
            max_pages_per_term=2,
        )
    elif name == "Dassault Systèmes":
        company.update(
            ats="dassault_xml",
            url="https://www.3ds.com/apisearch/card_search_api",
            career_site_url=url,
            search_terms=DEFAULT_SEARCH_TERMS,
            max_pages_per_term=3,
        )
    elif name == "Eightfold AI":
        company.update(
            ats="eightfold",
            url="https://app.eightfold.ai/api/pcsx/search",
            career_site_url="https://app.eightfold.ai/careers",
            domain="volkscience.com",
            search_terms=DEFAULT_SEARCH_TERMS,
            search_locations=["Bengaluru, Karnataka, India", "Remote, India"],
            max_results_per_search=30,
        )
    elif name == "SLB":
        company.update(
            ats="eightfold",
            url="https://apply.slb.com/api/pcsx/search",
            career_site_url="https://apply.slb.com/careers",
            domain="slb.com",
            search_terms=DEFAULT_SEARCH_TERMS,
            search_locations=["Bengaluru, Karnataka, India", "Remote, India"],
            max_results_per_search=30,
        )
    elif name == "Nestlé":
        company.update(
            ats="jobs2web_rss",
            url="https://jobdetails.nestle.com/services/rss/job/",
            career_site_url="https://jobdetails.nestle.com/",
            search_terms=DEFAULT_SEARCH_TERMS,
            search_location="India",
            max_candidate_details=10,
        )
    elif name == "TheMathCompany":
        company.update(
            ats="peoplestrong",
            url=(
                "https://mathco-careers.peoplestrong.com/"
                "api/cp/rest/altone/cp/jobs/v1?offset=0&limit=100"
            ),
            career_site_url="https://mathco-careers.peoplestrong.com/job/joblist",
            max_results=100,
        )
    elif name == "lululemon":
        company.update(
            ats="lululemon_avature",
            url="https://careers.lululemon.com/en_US/careers/SearchCareer",
            career_site_url=url,
            search_terms=["data", "analytics", "AI"],
        )
    elif name == "Tonbo Imaging":
        company.update(
            ats="tonbo_html",
            url=(
                "https://tonboimaging.com/defense/"
                "?rest_route=/wp/v2/pages/11924"
            ),
            career_site_url=url,
            default_location="Bengaluru, India",
        )
    elif name in {"Impetus Technologies", "Rakuten India", "Reverie Language Technologies", "Sony India Software Centre"}:
        zwayam = {
            "Impetus Technologies": ("https://public.zwayam.com/jobs/search", "impetus.openings.co", "MTUxNjY="),
            "Rakuten India": ("https://apic2.zwayam.com/jobs/search", "rakuten.openings.co", "MTUxMjQ="),
            "Reverie Language Technologies": ("https://public.zwayam.com/jobs/search", "careers.reverieinc.com", "MTUxNDQ="),
            "Sony India Software Centre": ("https://public.zwayam.com/jobs/search", "careers.sonyindiasoftware.co.in", "MTU1MzI="),
        }[name]
        company.update(
            ats="tavant_browser_transport",
            url=zwayam[0],
            career_site_url=url,
            domain=zwayam[1],
            company_id=zwayam[2],
            max_results=10,
            read_timeout_seconds=25,
        )
    elif "darwinbox." in host and "/candidatev2/" in f"/{path}/":
        company_id = "main"
        match = re.search(r"/candidatev2/([^/]+)", parsed.path, flags=re.IGNORECASE)
        if match:
            company_id = unquote(match.group(1))
        company.update(
            ats="darwinbox_v2",
            url=f"{parsed.scheme}://{parsed.netloc}/ms/candidateapi/job/alljobs",
            career_site_url=url,
            company_id=company_id,
            max_results=100,
        )
    elif host == "job-boards.greenhouse.io":
        company.update(ats="greenhouse", slug=path.split("/", 1)[0])
    elif host == "jobs.lever.co":
        company.update(ats="lever", slug=path.split("/", 1)[0])
    elif host == "jobs.ashbyhq.com":
        company.update(ats="ashby", slug=path.split("/", 1)[0])
    elif host == "careers.smartrecruiters.com":
        company.update(ats="smartrecruiters", slug=path.split("/", 1)[0])
    elif "myworkdayjobs.com" in host or "myworkdaysite.com" in host:
        company.update(_workday_config(url))
    elif "oraclecloud.com" in host:
        company.update(_oracle_config(url))
    elif host == "apply.workable.com":
        slug = path.split("/", 1)[0]
        company.update(
            ats="workable",
            slug=slug,
            url=f"https://www.workable.com/api/accounts/{slug}?details=true",
            career_site_url=url,
        )
    elif host.endswith("freshteam.com"):
        company.update(ats="freshteam_html", url=url, career_site_url=url)
    elif name in ZOHO_PUBLIC_NAMES or host.endswith("zohorecruit.com"):
        company.update(ats="zoho_recruit_public", url=url, career_site_url=url)
    elif host == "careers.kula.ai":
        company.update(ats="kula_html", url=url, career_site_url=url)
    elif host.endswith("hire.trakstar.com"):
        company.update(ats="trakstar_html", url=url, career_site_url=url)
    elif host.endswith("sensehq.com"):
        company.update(ats="sensehq_next_data", url=url, career_site_url=url)
    elif host.endswith("app.param.ai"):
        company.update(
            ats="param_ai",
            url=f"{parsed.scheme}://{parsed.netloc}/api/career/get_job/",
            career_site_url=url,
        )
    elif host == "app.eightfold.ai":
        company.update(ats="eightfold_html", url=url, career_site_url=url)
    elif host in SUCCESSFACTORS_HOSTS:
        company.update(
            ats="successfactors_search",
            url=url,
            career_site_url=url,
            search_location="India",
            search_terms=DEFAULT_SEARCH_TERMS,
            max_pages_per_term=2,
            max_candidate_details=10,
        )
    elif host in TALENTBREW_HOSTS:
        company.update(
            ats="talentbrew_html",
            url=url,
            career_site_url=url,
            search_terms=DEFAULT_SEARCH_TERMS,
            max_pages_per_term=2,
            max_candidate_details=10,
        )
    else:
        company.update(
            ats="direct_job_html",
            url=url,
            career_site_url=url,
            max_candidate_details=10,
        )
    return company


def build_source_overrides(path: Path = CATALOG_FILE) -> list[dict[str, Any]]:
    """Return one merged override per canonical company name."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for source_name, url in _catalog_rows(path):
        company = classify_source(source_name, url)
        name = company["name"]
        if name not in merged:
            merged[name] = company
            order.append(name)
            continue
        prior = merged[name]
        combined_aliases = list(dict.fromkeys([
            *prior.get("aliases", []),
            *company.get("aliases", []),
        ]))
        # Prefer a newly supplied direct source over an inherited parent-only
        # alias record, while retaining every acquired-brand label.
        prior.update(company)
        if combined_aliases:
            prior["aliases"] = combined_aliases
    return [merged[name] for name in order]


def source_names() -> list[str]:
    return [company["name"] for company in build_source_overrides()]
