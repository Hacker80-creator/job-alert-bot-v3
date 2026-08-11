from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v29


class ProductionV29Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v29.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_verified_ashby_monitors(self) -> None:
        self.assertEqual(497, len(self.companies))
        self.assertEqual(
            487,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_monday_and_fullstory_are_enabled_ashby_sources(self) -> None:
        self.assertEqual("ashby", self.companies["Monday.com"]["ats"])
        self.assertEqual("monday.com", self.companies["Monday.com"]["slug"])
        self.assertEqual("ashby", self.companies["FullStory"]["ats"])
        self.assertEqual("fullstory", self.companies["FullStory"]["slug"])
        self.assertTrue(self.companies["Monday.com"]["enabled"])
        self.assertTrue(self.companies["FullStory"]["enabled"])

    def test_workflow_runs_v29_or_newer(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("python job_monitor_entry_v28.py", workflow)
        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
