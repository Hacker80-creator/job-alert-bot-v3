from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v31


class ProductionV31Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v31.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_recovered_sources(self) -> None:
        self.assertEqual(504, len(self.companies))
        self.assertEqual(
            495,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )
        self.assertEqual(
            539,
            sum(1 + len(item.get("aliases", [])) for item in self.companies.values()),
        )

    def test_recovered_sources_are_enabled(self) -> None:
        self.assertEqual("turbohire_api", self.companies["Flipkart"]["ats"])
        self.assertIn("Cleartrip", self.companies["Flipkart"]["aliases"])
        self.assertTrue(self.companies["Flipkart"]["enabled"])
        self.assertEqual("next_sitemap", self.companies["Globant"]["ats"])
        self.assertEqual(
            "direct_job_html", self.companies["Willis Towers Watson"]["ats"]
        )
        self.assertIn("WTW", self.companies["Willis Towers Watson"]["aliases"])

    def test_workflow_runs_v31(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("python job_monitor_entry_v31.py", workflow)
        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
