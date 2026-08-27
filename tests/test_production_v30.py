from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v30


class ProductionV30Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v30.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_next_dynamic_batch(self) -> None:
        self.assertEqual(502, len(self.companies))
        self.assertEqual(
            492,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )
        self.assertEqual(
            535,
            sum(1 + len(item.get("aliases", [])) for item in self.companies.values()),
        )

    def test_verified_dynamic_sources_are_enabled(self) -> None:
        expected = {
            "Epic Systems": "avature_html",
            "HSBC": "avature_html",
            "IKEA Digital": "talentbrew_html",
            "Novo Nordisk": "successfactors_search",
            "Siemens": "avature_html",
        }
        for name, ats in expected.items():
            with self.subTest(name=name):
                self.assertEqual(ats, self.companies[name]["ats"])
                self.assertTrue(self.companies[name]["enabled"])
        self.assertIn(
            "Siemens Digital Industries Software",
            self.companies["Siemens"]["aliases"],
        )

    def test_workflow_runs_v30_or_newer(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("python job_monitor_entry_v29.py", workflow)
        self.assertIn('cron: "7 */2 * * *"', workflow)
        self.assertIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
