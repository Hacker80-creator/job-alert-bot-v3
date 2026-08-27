from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v25


class ProductionV25Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v25.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_second_dynamic_batch(self) -> None:
        self.assertEqual(482, len(self.companies))
        self.assertEqual(
            472,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_second_dynamic_batch_is_enabled(self) -> None:
        expected = {
            "H2O.ai": "applytojob_html",
            "John Deere": "jobs2web_rss",
            "Locus": "smartrecruiters",
            "Magna International": "workday_search",
            "Nokia": "oracle_hcm",
            "Siemens Energy": "avature_html",
            "STMicroelectronics": "eightfold_html",
            "Texas Instruments": "oracle_hcm",
        }
        for name, ats in expected.items():
            with self.subTest(company=name):
                self.assertTrue(self.companies[name]["enabled"])
                self.assertEqual(ats, self.companies[name]["ats"])

    def test_third_dynamic_batch_is_enabled(self) -> None:
        expected = {
            "AMD": "jibe_api",
            "Costco Wholesale": "jibe_api",
            "DocuSign": "jibe_api",
            "ET Money": "zoho_careers_html",
            "Ganit": "zoho_careers_html",
            "GitHub": "jibe_api",
            "Global Payments": "workday_multi",
            "Increff": "zoho_careers_html",
            "Intercom": "greenhouse",
            "Intercontinental Exchange": "jibe_api",
            "Keysight Technologies": "jibe_api",
            "Netflix": "eightfold_html",
            "Presidio": "ukg_jobboard",
            "Principal Financial Group": "jibe_api",
            "Snap": "workday_search",
            "ZS Associates": "jibe_api",
        }
        for name, ats in expected.items():
            with self.subTest(company=name):
                self.assertTrue(self.companies[name]["enabled"])
                self.assertEqual(ats, self.companies[name]["ats"])

    def test_parent_aliases_are_preserved_and_extended(self) -> None:
        self.assertIn("Xilinx", self.companies["AMD"]["aliases"])
        for alias in ("MuleSoft", "Slack", "Tableau", "Informatica"):
            self.assertIn(alias, self.companies["Salesforce"]["aliases"])

    def test_fourth_dynamic_batch_is_enabled(self) -> None:
        expected = {
            "Hitachi Energy": "workday_search",
            "Qatar Airways Technology": "avature_html",
            "Remitly": "workday_search",
            "TotalEnergies": "avature_html",
            "Trellix": "workday_search",
            "Vanguard": "workday_search",
        }
        for name, ats in expected.items():
            with self.subTest(company=name):
                self.assertTrue(self.companies[name]["enabled"])
                self.assertEqual(ats, self.companies[name]["ats"])

    def test_workflow_runs_v25(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertRegex(workflow, r"python job_monitor_entry_v(?:2[5-9]|[3-9]\d+)\.py")
        self.assertIn('cron: "7 */2 * * *"', workflow)
        self.assertIn("contents: write", workflow)

    def test_fifth_dynamic_batch_is_enabled(self) -> None:
        expected = {
            "Equifax": "direct_job_html",
            "Etsy": "direct_job_html",
            "Gramener": "direct_job_html",
            "Indium Software": "direct_job_html",
            "Macquarie Group": "avature_html",
            "Novartis": "direct_job_html",
            "Salesloft": "greenhouse",
            "SentinelOne": "direct_job_html",
            "Shopify": "direct_job_html",
        }
        for name, ats in expected.items():
            with self.subTest(company=name):
                self.assertTrue(self.companies[name]["enabled"])
                self.assertEqual(ats, self.companies[name]["ats"])

    def test_sixth_dynamic_batch_is_enabled(self) -> None:
        expected = {
            "CitiusTech": "ripplehire",
            "Dream Sports": "trakstar_html",
            "Ninjacart": "freshteam_html",
            "Wells Fargo": "direct_job_html",
        }
        for name, ats in expected.items():
            with self.subTest(company=name):
                self.assertTrue(self.companies[name]["enabled"])
                self.assertEqual(ats, self.companies[name]["ats"])


if __name__ == "__main__":
    unittest.main()
