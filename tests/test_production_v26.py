from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v26


class ProductionV26Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v26.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_dynamic_ats_batch(self) -> None:
        self.assertEqual(485, len(self.companies))
        self.assertEqual(
            475,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_param_dayforce_and_turbohire_sources_are_enabled(self) -> None:
        expected = {
            "Josh Software": "param_ai",
            "MoneyGram": "dayforce_geo",
            "Ola": "turbohire_api",
        }
        for name, ats in expected.items():
            with self.subTest(company=name):
                self.assertTrue(self.companies[name]["enabled"])
                self.assertEqual(ats, self.companies[name]["ats"])
        self.assertIn("Ola Electric", self.companies["Ola"]["aliases"])

    def test_mismatched_cleartrip_source_is_not_promoted(self) -> None:
        self.assertNotIn("Cleartrip", self.companies)

    def test_workflow_runs_v26(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("python job_monitor_entry_v26.py", workflow)
        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
