from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v20


class ProductionV20Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.companies = {
            item["name"]: item
            for item in job_monitor_entry_v20.load_final_config()["companies"]
        }

    def test_registry_is_unique_and_counts_are_expected(self) -> None:
        self.assertEqual(305, len(self.companies))
        self.assertEqual(
            297,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_verified_source_assignments(self) -> None:
        expected = {
            "Dream11": "trakstar_rss",
            "Autodesk": "workday_india",
            "Chegg": "workday_india",
            "Arm": "talentbrew_html",
            "AstraZeneca": "talentbrew_html",
            "Alstom": "successfactors_search",
            "Adidas": "successfactors_search",
            "Baker Hughes": "phenom",
            "Allianz Technology": "phenom",
            "BNY Mellon": "oracle_hcm",
            "C3 AI": "greenhouse",
            "Affine": "sensehq_next_data",
        }
        for name, ats in expected.items():
            with self.subTest(company=name):
                self.assertEqual(ats, self.companies[name]["ats"])
                self.assertTrue(self.companies[name]["enabled"])

    def test_unsafe_or_unverified_sources_are_not_scanned(self) -> None:
        expected_status = {
            "Zepto": "fallback_only",
            "BlackBuck": "fallback_only",
            "Bounce": "fallback_only",
            "Capillary Technologies": "fallback_only",
            "Carrefour": "fallback_only",
            "Cartesian Consulting": "fallback_only",
            "BluSmart": "disabled",
        }
        for name, status in expected_status.items():
            with self.subTest(company=name):
                self.assertFalse(self.companies[name]["enabled"])
                self.assertEqual(status, self.companies[name]["source_status"])

    def test_census_is_covered_by_existing_fivetran_source(self) -> None:
        self.assertIn("Fivetran", self.companies)
        self.assertTrue(self.companies["Fivetran"]["enabled"])
        self.assertNotIn("Census", self.companies)

    def test_v20_entry_binds_the_v11_parser(self) -> None:
        source = (Path(__file__).parents[1] / "job_monitor_entry_v20.py" ).read_text(encoding="utf-8")
        self.assertIn("custom_source_parsers_v11.fetch_company_jobs_with_custom_v11", source)

    def test_workflow_runs_v20_entry_point(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('cron: "7 */2 * * *"', workflow)
        self.assertIn("permissions:", workflow)
        self.assertIn("contents: write", workflow)
        self.assertRegex(workflow, r"python job_monitor_entry_v\d+\.py")


if __name__ == "__main__":
    unittest.main()
