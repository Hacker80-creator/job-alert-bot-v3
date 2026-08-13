from __future__ import annotations

import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
