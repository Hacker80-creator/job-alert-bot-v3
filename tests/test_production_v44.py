from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import custom_source_parsers_v30
import job_monitor_entry_v44
import source_registry_v44


class ProductionV44Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v44.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_catalog_and_registry_counts(self) -> None:
        self.assertEqual(261, len(source_registry_v44._catalog_rows()))
        self.assertEqual(56, len(source_registry_v44.deferred_source_names()))
        self.assertEqual(259, len(source_registry_v44.build_source_overrides()))
        self.assertEqual(799, len(self.companies))
        self.assertEqual(
            790,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_standard_ats_are_derived(self) -> None:
        expected = {
            "Tessolve": "darwinbox_v2",
            "TheMathCompany": "peoplestrong",
            "Dassault Systèmes": "dassault_xml",
            "Eightfold AI": "eightfold",
            "Ameriprise Financial": "ameriprise_html",
            "Intuitive Surgical": "smartrecruiters",
            "Kimberly-Clark": "workday_search",
            "KaleidEO": "kaleideo_wordpress",
            "New York Life India": "successfactors_search",
            "redBus": "trakstar_html",
            "SpotDraft": "ashby",
            "Smarsh": "lever",
            "Netradyne": "smartrecruiters",
            "GlobalFoundries": "workday_search",
            "Landmark Group": "oracle_hcm",
            "Innominds": "workable",
            "Mudrex": "freshteam_html",
            "Digantara": "kula_html",
            "Qure.ai": "zoho_recruit_public",
            "GalaxEye Space": "zoho_recruit_public",
            "HealthPlix": "zoho_recruit_public",
            "GoKwik": "keka_embed",
            "SatSure": "keka_embed",
            "Moneyview": "darwinbox_v2",
            "LeadSquared": "darwinbox_v2",
            "Porter": "darwinbox_v2",
            "Sonata Software": "darwinbox_v2",
            "ClearTax": "darwinbox_v2",
            "FarEye": "direct_job_html",
            "Blackhawk Network": "icims_html",
            "MaxLinear": "icims_html",
            "Waters Corporation": "icims_html",
            "SiMa.ai": "jobvite_html",
            "CoinSwitch": "recruiterflow_html",
            "HDFC ERGO": "peoplestrong",
            "GreyOrange": "tavant_browser_transport",
            "Gnani.ai": "gnani_api",
            "Addverb": "hrone_html",
            "Digit Insurance": "darwinbox_v2",
            "Spinny": "darwinbox_v2",
            "Tata 1mg": "darwinbox_v2",
            "Evalueserve": "evalueserve_html",
            "Accenture": "workday_search",
            "AIG": "workday_search",
            "Bureau": "ashby",
            "CloudSEK": "greenhouse",
            "Danaher": "workday_search",
            "Dozee": "lever",
            "General Mills": "workday_search",
            "Labcorp": "workday_search",
            "Pixxel": "darwinbox_v2",
            "Procter & Gamble": "workday_search",
            "Saks Global": "workday_search",
            "Scopely": "greenhouse",
            "Thomson Reuters": "workday_search",
            "Unilever": "workday_search",
            "Cargill": "talentbrew_html",
            "Hero MotoCorp": "successfactors_search",
            "Lupin": "successfactors_search",
            "Reckitt": "successfactors_search",
            "Sun Pharma": "talentbrew_html",
            "Tata Motors": "successfactors_search",
            "Zurich Insurance Group": "successfactors_search",
            "CynLr": "freshteam_html",
            "Eka Software Solutions": "freshteam_html",
            "Haptik": "freshteam_html",
            "CoRover": "static_job_links",
            "Credo Semiconductor": "static_job_links",
            "Dhruva Space": "static_job_links",
            "Facilio": "static_job_links",
            "HomeLane": "static_job_links",
            "InVideo": "static_job_links",
            "Lemnisk": "static_job_links",
            "ProductDossier": "static_job_links",
            "Rapyd": "static_job_links",
            "Sumo Digital India": "static_job_links",
            "Tata Elxsi": "static_job_links",
        }
        for name, ats in expected.items():
            self.assertEqual(ats, self.companies[name]["ats"])

    def test_parent_aliases_are_preserved(self) -> None:
        self.assertIn("Apptio", self.companies["IBM"]["aliases"])
        self.assertIn("Cytiva", self.companies["Danaher"]["aliases"])
        self.assertIn("Beckman Coulter", self.companies["Danaher"]["aliases"])
        self.assertIn("Flutura", self.companies["Accenture"]["aliases"])
        self.assertIn("Saankhya Labs", self.companies["Tejas Networks"]["aliases"])

    def test_workflow_runs_v44(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml").read_text(encoding="utf-8")
        self.assertIn("python job_monitor_entry_v44.py", workflow)
        self.assertIn("verified_sources_v44.txt", workflow)

    @patch("custom_source_parsers_v30.requests.get")
    def test_static_job_links_keep_card_title_and_stable_id(self, get: Mock) -> None:
        listing = Mock()
        listing.url = "https://example.com/careers"
        listing.text = (
            '<div class="job-card"><h3>Data Engineer</h3>'
            '<a href="/jobs/abc-123/apply">Apply Now</a></div>'
        )
        listing.raise_for_status.return_value = None
        detail = Mock()
        detail.url = "https://example.com/jobs/abc-123/apply"
        detail.text = (
            '<main><h1>Apply at Example</h1>'
            '<div class="job-location">Bengaluru, India</div></main>'
        )
        detail.raise_for_status.return_value = None
        get.side_effect = [listing, detail]
        jobs = custom_source_parsers_v30.parse_static_job_links({
            "name": "Example",
            "ats": "static_job_links",
            "url": listing.url,
            "job_url_pattern": r"^https://example\.com/jobs/[^/]+/apply$",
            "wlb_score": 3,
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Data Engineer", jobs[0].title)
        self.assertEqual("abc-123", jobs[0].requisition_id)
        self.assertEqual("Bengaluru, India", jobs[0].location)


if __name__ == "__main__":
    unittest.main()
