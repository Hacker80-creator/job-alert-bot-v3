"""Company sources that are exclusive to the QA alert pipeline."""
from __future__ import annotations

from copy import deepcopy

from qa_role_filter import QA_SEARCH_TERMS


_QA_ONLY_SOURCES = [
    {"name": "TCS", "ats": "qa_html_search", "url": "https://ibegin.tcsapps.com/candidate/jobs/search"},
    {
        "name": "Infosys",
        "ats": "infosys_api",
        "url": (
            "https://intapgateway.infosysapps.com/careersci/search/"
            "intapjbsrch/getCareerSearchJobs?sourceId=1,21&searchText=QA"
        ),
        "career_site_url": (
            "https://career.infosys.com/joblist?"
            "companyhiringtype=IL&countrycode=IN"
        ),
    },
    {"name": "Wipro", "ats": "qa_html_search", "url": "https://careers.wipro.com/search/?q=test&locationsearch=India"},
    {"name": "Cognizant", "ats": "qa_html_search", "url": "https://careers.cognizant.com/global-en/jobs/"},
    {"name": "HCLTech", "ats": "qa_html_search", "url": "https://careers.hcltech.com/search/?q=test&locationsearch=India"},
    {"name": "Capgemini", "ats": "qa_html_search", "url": "https://www.capgemini.com/careers/join-capgemini/job-search/"},
    {"name": "Tech Mahindra", "ats": "qa_html_search", "url": "https://careers.techmahindra.com/"},
    {"name": "LTIMindtree", "ats": "qa_html_search", "url": "https://careers.ltm.com/"},
    {
        "name": "Mphasis",
        "ats": "ripplehire",
        "url": "https://mphasis.ripplehire.com/candidate/",
        "career_site_url": "https://mphasis.ripplehire.com/candidate/?token=ty4DfyWddnOrtpclQeia&source=CAREERSITE#list",
        "token": "ty4DfyWddnOrtpclQeia",
        "source": "CAREERSITE",
    },
    {
        "name": "Coforge",
        "ats": "zwayam_hardened",
        "url": "https://public.zwayam.com/jobs/search",
        "career_site_url": "https://careers.coforge.com/coforge",
        "domain": "careers.coforge.com",
        "company_id": "MTUxNzM=",
        "tenant_group_id": "G1",
        "multipart_form": True,
        "browser_user_agent": "Mozilla/5.0",
        "job_path_template": "{portal}/jobview/{slug}",
        "zwayam_search_terms": ["QA", "test", "quality"],
        "read_timeout_seconds": 30,
        # The newest matching page is enough for a two-hour monitor and avoids
        # Zwayam's intermittently slow historical pagination.
        "max_results_per_term": 10,
    },
    {
        "name": "Hexaware",
        "ats": "oracle_hcm",
        "url": "https://fa-etqo-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "career_site_url": "https://fa-etqo-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1",
        "site_number": "CX_1",
    },
    {
        "name": "Persistent Systems",
        "ats": "zwayam_hardened",
        "url": "https://public.zwayam.com/jobs/search",
        "career_site_url": "https://careers.persistent.com",
        "domain": "careers.persistent.com",
        "company_id": "MTYzNDQ=",
        "multipart_form": True,
        "browser_user_agent": "Mozilla/5.0",
        "job_path_template": "{portal}/jobview/{slug}",
        "zwayam_search_terms": ["QA", "test", "quality"],
        "read_timeout_seconds": 30,
        "max_results_per_term": 10,
    },
    {"name": "EPAM Systems", "ats": "qa_html_search", "url": "https://careers.epam.com/en/jobs/india"},
    {"name": "GlobalLogic", "ats": "qa_html_search", "url": "https://www.globallogic.com/in/career-search-page/"},
    {
        "name": "Virtusa",
        "ats": "phenom_content_api",
        "url": (
            "https://content-us.phenompeople.com/api/"
            "VIRVIRGLOBAL/refineSearch"
        ),
        "career_site_url": (
            "https://www.virtusa.com/careers/job-search/global/en"
        ),
        "site_id": "VIRVIRGLOBAL",
        "locale": "en_global",
        "page_size": 50,
        "max_pages_per_term": 2,
    },
    {"name": "Encora", "ats": "greenhouse", "slug": "encora10", "career_site_url": "https://job-boards.greenhouse.io/encora10"},
    {
        "name": "Expleo",
        "ats": "icims_html",
        "url": "https://expleo-jobs-in-en.icims.com/jobs/search",
        "career_site_url": "https://expleo-jobs-in-en.icims.com/",
        "max_pages": 10,
        "minimal_browser_headers": True,
        "curl_browser_transport": True,
        "curl_user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36"
        ),
    },
    {
        "name": "Qualitest",
        "aliases": ["QualityAI", "QualityAI / Qualitest"],
        "ats": "successfactors_search",
        "url": "https://careers.quality-ai.com/search/",
    },
    {"name": "TestingXperts", "ats": "smartrecruiters", "slug": "TestingXperts", "career_site_url": "https://careers.smartrecruiters.com/TestingXperts"},
    {"name": "TestYantra", "ats": "breezy", "url": "https://test-yantra-eu-2.breezy.hr/json", "career_site_url": "https://test-yantra-eu-2.breezy.hr/"},
    {"name": "Qapitol", "ats": "qa_html_search", "url": "https://qapitol.ai/careers"},
    {"name": "Maveric Systems", "ats": "qa_html_search", "url": "https://career44.sapsf.com/career?company=mavericsys"},
    {"name": "TestMu AI", "aliases": ["LambdaTest"], "ats": "qa_html_search", "url": "https://www.testmuai.com/career/"},
    {
        "name": "Testsigma",
        "ats": "no_public_board",
        "url": "https://www.linkedin.com/company/testsigma/jobs/",
        "enabled": False,
        "disabled_reason": "No reliable standalone official public job board was verified.",
    },
    {
        "name": "Tricentis",
        "ats": "workday_india",
        "url": "https://tricentis.wd1.myworkdayjobs.com/wday/cxs/tricentis/Tricentis_Careers/jobs",
        "career_site_url": "https://tricentis.wd1.myworkdayjobs.com/Tricentis_Careers",
    },
    {"name": "Katalon", "ats": "qa_html_search", "url": "https://katalon.com/careers/all-jobs"},
]


def build_qa_only_sources() -> list[dict]:
    sources = deepcopy(_QA_ONLY_SOURCES)
    for source in sources:
        source.setdefault("kind", "qa_only")
        source.setdefault("wlb_score", 3)
        source.setdefault("enabled", True)
        source.setdefault("search_terms", list(QA_SEARCH_TERMS))
        source.setdefault("search_location", "India")
        source.setdefault("max_pages_per_term", 2)
        source.setdefault("max_results_per_term", 60)
        source.setdefault("max_candidate_details", 20)
    return sources


QA_ONLY_COMPANY_NAMES = tuple(source["name"] for source in _QA_ONLY_SOURCES)
