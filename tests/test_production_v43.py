from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v43


class ProductionV43Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v43.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_four_sources(self) -> None:
        self.assertEqual(543, len(self.companies))
        self.assertEqual(534, sum(1 for item in self.companies.values() if item.get("enabled", True)))
        self.assertEqual(582, sum(1 + len(item.get("aliases", [])) for item in self.companies.values()))

    def test_sources_are_enabled(self) -> None:
        expected = {
            "Robosoft Technologies": "robosoft_html",
            "Kuku FM": "listing_jsonld",
            "Marlabs": "successfactors_search",
            "Indegene": "successfactors_search",
        }
        for name, ats in expected.items():
            self.assertEqual(ats, self.companies[name]["ats"])
        self.assertEqual(180, self.companies["Kuku FM"]["max_posting_age_days"])

    def test_workflow_runs_v43(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml").read_text(encoding="utf-8")
        self.assertIn("python job_monitor_entry_v43.py", workflow)
        self.assertIn("source_overrides_v41.yaml", workflow)


if __name__ == "__main__":
    unittest.main()
