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
        self.assertEqual(263, len(source_registry_v44._catalog_rows()))
        self.assertEqual(54, len(source_registry_v44.deferred_source_names()))
        self.assertEqual(261, len(source_registry_v44.build_source_overrides()))
        self.assertEqual(801, len(self.companies))
        self.assertEqual(
            792,
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
            "Molecular Connections": "wordpress_post_type",
            "New York Life India": "successfactors_search",
            "Signalchip": "signalchip_wordpress",
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
