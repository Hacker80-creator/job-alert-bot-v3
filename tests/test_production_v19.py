from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v19


class ProductionV19Tests(unittest.TestCase):
    def test_atlassian_and_chargebee_use_live_first_party_sources(self) -> None:
        companies = {
            item["name"]: item
            for item in job_monitor_entry_v19.load_final_config()["companies"]
        }
        self.assertEqual("atlassian_listings", companies["Atlassian"]["ats"])
        self.assertEqual("successfactors_html", companies["Chargebee"]["ats"])
        self.assertTrue(companies["Atlassian"]["enabled"])
        self.assertTrue(companies["Chargebee"]["enabled"])

    def test_registry_counts_are_preserved(self) -> None:
        companies = job_monitor_entry_v19.load_final_config()["companies"]
        names = [str(item["name"]).casefold() for item in companies]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(263, len(companies))
        self.assertEqual(262, sum(1 for item in companies if item.get("enabled", True)))

    def test_workflow_runs_v19_entry_point(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("python job_monitor_entry_v19.py", workflow)


if __name__ == "__main__":
    unittest.main()
