from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v27


class ProductionV27Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v27.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_verified_ats_batch(self) -> None:
        self.assertEqual(493, len(self.companies))
        self.assertEqual(
            483,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_verified_workday_and_greenhouse_sources_are_enabled(self) -> None:
        expected = {
            "DataRobot": "workday_search",
            "FactSet": "workday_search",
            "Franklin Templeton": "workday_search",
            "Unity": "workday_search",
            "Deutsche Bank": "workday_search",
            "Morningstar": "workday_search",
            "Ocado Technology": "greenhouse",
            "Weights & Biases": "greenhouse",
        }
        for name, ats in expected.items():
            with self.subTest(company=name):
                self.assertTrue(self.companies[name]["enabled"])
                self.assertEqual(ats, self.companies[name]["ats"])
        self.assertIn("W&B", self.companies["Weights & Biases"]["aliases"])

    def test_workflow_runs_v27(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("python job_monitor_entry_v27.py", workflow)
        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
