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

DARWINBOX_OFFICIAL_BOARDS = {
    # These first-party corporate pages link to the Darwinbox board below,
    # but the supplied catalog deliberately keeps the corporate URL visible.
    "Digit Insurance": (
        "https://godigit.darwinbox.in/ms/candidatev2/a651fdd75445d1/careers/home",
        "a651fdd75445d1",
        False,
    ),
    "Spinny": (
        "https://spinzone.darwinbox.in/ms/candidate/careers",
        "main",
        True,
    ),
    "Tata 1mg": (
        "https://1mg.darwinbox.in/jobs",
        "main",
        True,
    ),
}

# Corporate careers pages below advertise these first-party ATS boards.  The
# catalog continues to retain the user-supplied corporate URL, while runtime
# scanning uses the structured board so a JavaScript shell is never mistaken
# for an empty job list.
OFFICIAL_ATS_BOARDS = {
    "AIG": "https://aig.wd1.myworkdayjobs.com/aig",
    "Beckman Coulter": "https://danaher.wd1.myworkdayjobs.com/DanaherJobs",
    "Bureau": "https://jobs.ashbyhq.com/bureau",
    "CloudSEK": "https://job-boards.greenhouse.io/cloudsek",
    "Cytiva": "https://danaher.wd1.myworkdayjobs.com/DanaherJobs",
    "Dozee": "https://jobs.lever.co/dozee",
    "Eka Software Solutions": "https://careers.quoreka.com",
    "Flutura": "https://accenture.wd103.myworkdayjobs.com/AccentureCareers",
    "General Mills": "https://genmills.wd1.myworkdayjobs.com/GMI_External_Careers",
    "Haptik": "https://haptik.freshteam.com/jobs",
    "Labcorp": "https://labcorp.wd1.myworkdayjobs.com/External",
    "Pixxel": "https://pixxel.darwinbox.in/ms/candidate/careers",
    "Procter & Gamble": "https://pg.wd5.myworkdayjobs.com/1000",
    "Rapido": "https://rapido.darwinbox.in/ms/candidate/careers",
    "Saks Global": "https://saks.wd1.myworkdayjobs.com/careers_at_saks",
    "Scopely": "https://job-boards.greenhouse.io/scopely",
    "Thomson Reuters": (
        "https://thomsonreuters.wd5.myworkdayjobs.com/External_Career_Site"
    ),
    "Unilever": (
        "https://unilever.wd3.myworkdayjobs.com/"
        "Unilever_Experienced_Professionals"
    ),
    "CynLr": "https://cynlr.freshteam.com/jobs",
    "Zetwerk": "https://zetwerk.sensehq.com/careers",
}

STATIC_JOB_LINK_SOURCES = {
    "CoRover": r"^https://corover\.ai/company/careers/[^/?#]+/?$",
    "Credo Semiconductor": (
        r"^https://credo\.careers\.hibob\.com/jobs/[^/?#]+/apply/?$"
    ),
    "Detect Technologies": (
        r"^https://detecttechnologies\.com/career/[^/?#]+/?$"
    ),
    "Dhruva Space": (
        r"^https://www\.dhruvaspace\.com/careers/[^/?#]+/?$"
    ),
    "Facilio": r"^https://facilio\.com/careers/[^/?#]+/?$",
    "HomeLane": r"^https://sentinel\.homelane\.com/jobs/[^/?#]+/?$",
    "Gramener": r"^https://gramener\.com/careers/[a-z0-9-]+/?$",
    "HyperVerge": r"^https://www\.linkedin\.com/jobs/view/\d+/?(?:\?.*)?$",
    "InVideo": r"^https://careers\.invideo\.io/roles/[^/?#]+/?$",
    "Incedo": r"^https://www\.incedoinc\.com/career/[^/?#]+/?$",
    "Lemnisk": r"^https://www\.lemnisk\.co/job/\d+/?$",
    "Mimecast": r"^https://careers\.mimecast\.com/en/jobs/[^/?#]+/[^/?#]+/?$",
    "ProductDossier": r"^https://www\.kytes\.com/career/[^/?#]+/?$",
    "PVH Corp.": (
        r"^https://careers\.pvh\.com/jobs/"
        r"(?!search(?:[/?#]|$))[^/?#]+/?$"
    ),
    "Rapyd": (
        r"^https://www\.rapyd\.net/company/careers/positions/[^/?#]+/?$"
    ),
    "Sumo Digital India": (
        r"^https://www\.sumo-digital\.com/careers/[^/?#]+/?$"
    ),
    "Tata Elxsi": (
        r"^https://www\.tataelxsi\.com/careers/job-openings/[^/?#]+/?$"
    ),
    "JCB India": r"^https://careers\.jcb\.com/search/\d+/[^/?#]+/?$",
    "MetLife GOSC": (
        r"^https://www\.metlifecareers\.com/en_US/ml/JobDetail/[^?#]+/\d+/?$"
    ),
}

SUCCESSFACTORS_HOSTS = {
    "careers.cipla.com",
    "careers.lupin.com",
    "careers.reckitt.com",
    "careers.tatamotors.com",
    "jobs.heromotocorp.com",
    "jobs.kellanova.com",
    "jobs.schaeffler.com",
    "jobs.volvocars.com",
    "www.careers.zurich.com",
    "careers.hyundai.co.in",
}

TALENTBREW_HOSTS = {
    "careers.cargill.com",
    "careers.labcorp.com",
    "careers.mimecast.com",
    "careers.saksglobal.com",
    "careers.scopely.com",
    "careers.thomsonreuters.com",
    "jobs.baxter.com",
    "jobs.parexel.com",
    "jobs.sunpharma.com",
    "careers.breadfinancial.com",
    "careers.mars.com",
    "www.metlifecareers.com",
}

ZOHO_PUBLIC_NAMES = {
    "GALAXEYE SPACE SOLUTIONS PRIVATE LIMITED",
    "GalaxEye Space",
    "HealthPlix",
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


def deferred_source_reasons(path: Path = DEFERRED_FILE) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, reason = line.partition("|")
        if not separator or reason not in DEFERRED_REASONS:
            raise ValueError(f"invalid v44 deferred line: {raw_line!r}")
        reasons[name.strip().casefold()] = reason
    return reasons


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
    official_board = OFFICIAL_ATS_BOARDS.get(name)
    if official_board and url != official_board:
        company = classify_source(name, official_board)
        company["catalog_url"] = url
        return company

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
    elif name == "American Express":
        company.update(
            ats="oracle_hcm",
            url=(
                "https://egug.fa.us2.oraclecloud.com/hcmRestApi/resources/"
                "latest/recruitingCEJobRequisitions"
            ),
            career_site_url=url,
            site_number="CX_1",
            search_terms=DEFAULT_SEARCH_TERMS,
            max_results_per_term=48,
        )
    elif name == "Cirrus Logic":
        company.update(
            ats="lever",
            slug="cirrus",
            api_host="api.eu.lever.co",
            career_site_url=url,
        )
    elif name == "IBM":
        company.update(
            ats="ibm_avature",
            url="https://ibmglobal.avature.net/en_US/careers/OpenJobs",
            career_site_url=(
                "https://careers.ibm.com/en_US/careers/SearchJobs"
            ),
            search_terms=DEFAULT_SEARCH_TERMS,
            records_per_page=48,
            max_pages_per_term=1,
            local_location_keyword="Bangalore",
            location_filter_field="10296[]",
            india_location_filter="103855",
            work_arrangement_filter_field="10297[]",
            remote_work_filter="583469",
            include_remote_india=True,
        )
    elif name == "River Mobility":
        company.update(
            ats="river_careers",
            url=(
                "https://main-svc-v2.prd.rideriver.com/"
                "api/v1/career/jobs"
            ),
            career_site_url=(
                "https://www.rideriver.com/careers/current-openings"
            ),
        )
    elif name == "Intuitive Surgical":
        company.update(
            ats="smartrecruiters",
            slug="Intuitive",
            career_site_url=url,
            search_terms=DEFAULT_SEARCH_TERMS,
        )
    elif name == "Kimberly-Clark":
        company.update(_workday_config(
            "https://kimberlyclark.wd1.myworkdayjobs.com/global"
        ))
        company["career_site_url"] = url
    elif name == "KaleidEO":
        company.update(
            ats="kaleideo_wordpress",
            url=(
                "https://kaleideo.co/wp-json/wp/v2/pages"
                "?slug=careers-at-kaleideo"
            ),
            career_site_url=url,
            default_location="Bengaluru, India",
        )
    elif name == "Quantzig":
        company.update(
            ats="quantzig_accordion",
            url=url,
            career_site_url=url,
            default_location="Bengaluru, India",
        )
    elif name == "Samsara":
        company.update(
            ats="greenhouse",
            slug="samsara",
            career_site_url=url,
        )
    elif name == "Molecular Connections":
        company.update(
            ats="wordpress_post_type",
            url=(
                "https://career.molecularconnections.com/"
                "wp-json/wp/v2/job_opening?per_page=100"
            ),
            career_site_url="https://career.molecularconnections.com/job_opening/",
            default_location="Bengaluru, India",
        )
    elif name == "New York Life India":
        company.update(
            ats="successfactors_search",
            url="https://jobs.newyorklife.com/search/",
            career_site_url=url,
            search_location="India",
            search_terms=DEFAULT_SEARCH_TERMS,
            max_pages_per_term=2,
            max_candidate_details=10,
        )
    elif name == "Signalchip":
        company.update(
            ats="signalchip_wordpress",
            url=(
                "https://www.signalchip.com/wp-json/wp/v2/pages"
                "?slug=job-openings"
            ),
            career_site_url=url,
            default_location="Bengaluru, India",
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
            search_terms=["data", "machine learning", "analytics", "AI"],
            search_locations=["India"],
            max_results_per_search=20,
            search_request_delay_seconds=0.2,
            rate_limit_attempts=3,
            rate_limit_base_delay_seconds=1,
            rate_limit_max_delay_seconds=4,
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
    # FarEye's official legacy portal currently returns Darwinbox's own
    # "Error while getting tenant info" from both public job APIs. Keep the
    # conservative page monitor until the tenant is restored instead of
    # turning every production run into a failed-source run.
    elif name == "FarEye" and "darwinbox." in host:
        company.update(
            ats="direct_job_html",
            url=url,
            career_site_url=url,
            max_candidate_details=10,
        )
    elif name == "H&M Group":
        # The official India site consistently returns HTTP 403 from GitHub's
        # hosted-runner network. Keep the reviewed URL in the registry, but do
        # not misreport the runner block as either a working feed or no jobs.
        company.update(
            ats="direct_job_html",
            url=url,
            career_site_url=url,
            enabled=False,
            source_status="RUNNER_BLOCKED",
        )
    elif name == "7-Eleven Global Solution Center":
        company.update(
            ats="ripplehire",
            url="https://7-eleven-gsc.ripplehire.com/candidate/",
            career_site_url=(
                "https://7-eleven-gsc.ripplehire.com/candidate/"
                "?token=xRX3yWuPaSF0NIdF21oh&source=CAREERSITE#list"
            ),
            token="xRX3yWuPaSF0NIdF21oh",
            source="CAREERSITE",
            page_size=100,
            max_results=500,
        )
    elif name == "IDfy":
        company.update(
            ats="turbohire_api",
            url="https://thapi.azurewebsites.net",
            career_site_url=(
                "https://idfy.turbohire.co/careerpage/"
                "e73676a8-bc5a-4b43-b9c6-d3fc7a60b572"
            ),
            org_id="e73676a8-bc5a-4b43-b9c6-d3fc7a60b572",
        )
    elif name == "Avalara":
        company.update(
            ats="jibe_api",
            url="https://careers.avalara.com/api/jobs",
            career_site_url="https://careers.avalara.com/careers-home/jobs",
            page_size=100,
            max_results=500,
        )
    elif name in {"Bread Financial", "Mars"}:
        path_prefix = {
            "Bread Financial": "/us/en",
            "Mars": "/global/en",
        }[name]
        company.update(
            ats="phenom",
            url=f"{parsed.scheme}://{parsed.netloc}/widgets",
            career_site_url=f"{parsed.scheme}://{parsed.netloc}{path_prefix}",
            search_terms=DEFAULT_SEARCH_TERMS,
            search_cities=["Bengaluru", "Bangalore", "Remote"],
            page_size=50,
            max_pages_per_query=3,
        )
    elif name == "MetLife GOSC":
        company.update(
            ats="static_job_links",
            url="https://www.metlifecareers.com/en_US/ml/SearchJobs",
            career_site_url=url,
            job_url_pattern=STATIC_JOB_LINK_SOURCES[name],
            max_results=100,
        )
    elif name == "JCB India":
        company.update(
            ats="static_job_links",
            url="https://careers.jcb.com/search",
            career_site_url=url,
            job_url_pattern=STATIC_JOB_LINK_SOURCES[name],
            max_results=100,
        )
    elif name == "National Australia Bank — NAB":
        company.update(
            ats="eightfold",
            url="https://nab.eightfold.ai/api/pcsx/search",
            career_site_url="https://nab.eightfold.ai/careers",
            domain="nab.com.au",
            search_terms=DEFAULT_SEARCH_TERMS,
            search_locations=[
                "Bengaluru, Karnataka, India",
                "Remote, India",
            ],
            max_results_per_search=30,
        )
    elif name == "Teva Pharmaceuticals":
        company.update(
            ats="eightfold_html",
            url="https://www.careers.teva/careers",
            career_site_url="https://www.careers.teva/careers",
            search_terms=DEFAULT_SEARCH_TERMS,
            search_locations=[
                "Bangalore, India",
                "Bengaluru, India",
                "Remote, India",
            ],
        )
    elif name in {"Annalect", "Epsilon", "Gallagher"}:
        jibe = {
            "Annalect": (
                "https://indiacareers.omnicomglobalsolutions.com/api/jobs",
                {},
            ),
            "Epsilon": (
                "https://careers.publicisgroupe.com/api/jobs",
                {"tags2": "Epsilon"},
            ),
            "Gallagher": (
                "https://jobs.ajg.com/api/jobs",
                {"country": "India"},
            ),
        }[name]
        company.update(
            ats="jibe_api",
            url=jibe[0],
            career_site_url=url,
            query_params=jibe[1],
            page_size=100,
            max_results=500,
        )
    elif "darwinbox." in host and re.search(r"/candidate(?:v2)?(?:/|$)", parsed.path, re.I):
        company_id = "main"
        match = re.search(r"/candidatev2/([^/]+)", parsed.path, flags=re.IGNORECASE)
        if match:
            company_id = unquote(match.group(1))
        company.update(
            ats="darwinbox_v2",
            url=f"{parsed.scheme}://{parsed.netloc}/ms/candidateapi/job/alljobs",
            career_site_url=url,
            company_id=company_id,
            bootstrap_required="/candidatev2/" not in parsed.path.casefold(),
            max_results=100,
        )
    elif name in DARWINBOX_OFFICIAL_BOARDS:
        board_url, company_id, bootstrap_required = DARWINBOX_OFFICIAL_BOARDS[name]
        board = urlparse(board_url)
        company.update(
            ats="darwinbox_v2",
            url=f"{board.scheme}://{board.netloc}/ms/candidateapi/job/alljobs",
            career_site_url=board_url,
            company_id=company_id,
            bootstrap_required=bootstrap_required,
            max_results=100,
        )
    elif name == "GreyOrange":
        company.update(
            ats="tavant_browser_transport",
            url="https://public.zwayam.com/jobs/search",
            career_site_url=url,
            domain="careers.greyorange.com",
            company_id="MTYwOTA=",
            max_results=100,
            read_timeout_seconds=25,
        )
    elif name == "Addverb":
        company.update(
            ats="hrone_html",
            url="https://app.hrone.cloud/api/external/referral/CareerPosition/Details",
            career_site_url="https://hr1.to/9c16d2",
            max_results=100,
        )
    elif name == "Evalueserve":
        company.update(
            ats="evalueserve_html",
            url=url,
            career_site_url=url,
        )
    elif name in STATIC_JOB_LINK_SOURCES:
        company.update(
            ats="static_job_links",
            url=url,
            career_site_url=url,
            job_url_pattern=STATIC_JOB_LINK_SOURCES[name],
            max_results=100,
        )
        if name == "HyperVerge":
            company["source_label"] = "Official HyperVerge page: LinkedIn job"
            company["fetch_job_details"] = False
            company["location_pattern"] = (
                r"\b(Bengaluru|Bangalore|Remote(?:\s*-\s*India)?)\b"
            )
        if name == "Incedo":
            company["fetch_job_details"] = False
            company["use_card_context_as_location"] = False
        if name == "Detect Technologies":
            company["ignored_detail_locations"] = ["get in touch"]
            company["use_card_context_as_location"] = False
        if name == "PVH Corp.":
            company["preserve_card_title"] = True
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
    elif name == "Eka Software Solutions" and host == "careers.quoreka.com":
        company.update(ats="freshteam_html", url=url, career_site_url=url)
    elif host.endswith(".keka.com"):
        company.update(ats="keka_embed", url=url, career_site_url=url)
    elif host.endswith(".icims.com"):
        company.update(
            ats="icims_html",
            url=f"{parsed.scheme}://{parsed.netloc}/jobs/search",
            career_site_url=url,
            max_pages=30,
        )
    elif host == "jobs.jobvite.com":
        slug = path.split("/", 1)[0]
        company.update(
            ats="jobvite_html",
            url=f"https://jobs.jobvite.com/{slug}/?nl=1&fr=false",
            career_site_url=url,
            slug=slug,
        )
    elif host == "recruiterflow.com" and path.endswith("/jobs"):
        company.update(ats="recruiterflow_html", url=url, career_site_url=url)
    elif host == "careers.gnani.ai":
        company.update(
            ats="gnani_api",
            url="https://careers.gnani.ai/api/jobs",
            career_site_url=url,
        )
    elif host.endswith(".peoplestrong.com"):
        origin = f"{parsed.scheme}://{parsed.netloc}"
        company.update(
            ats="peoplestrong",
            url=f"{origin}/api/cp/rest/altone/cp/jobs/v1?offset=0&limit=100",
            career_site_url=url,
            bootstrap_url=f"{origin}/api/cp/rest/altone/cp/urlinfo",
            search_terms=DEFAULT_SEARCH_TERMS,
        )
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
        search_url = url
        if "/search" not in parsed.path.casefold():
            search_url = f"{parsed.scheme}://{parsed.netloc}/search/"
        company.update(
            ats="successfactors_search",
            url=search_url,
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
    deferred_reason = deferred_source_reasons().get(name.casefold())
    if deferred_reason:
        company["enabled"] = False
        company["source_status"] = deferred_reason
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
