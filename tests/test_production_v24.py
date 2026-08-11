from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v24


class ProductionV24Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v24.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_avature_batch(self) -> None:
        self.assertEqual(439, len(self.companies))
        self.assertEqual(
            429,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_avature_sources_are_enabled(self) -> None:
        for name in ("Bloomberg", "Electronic Arts", "Lenovo", "Tesco Bengaluru"):
            with self.subTest(company=name):
                company = self.companies[name]
                self.assertTrue(company["enabled"])
                self.assertEqual("avature_html", company["ats"])
                self.assertIn("careers", company["url"].casefold())

    def test_workflow_runs_v24(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertRegex(workflow, r"python job_monitor_entry_v(?:2[4-9]|[3-9]\d+)\.py")
        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
