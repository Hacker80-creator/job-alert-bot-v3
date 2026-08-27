from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v32


class ProductionV32Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v32.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_next_official_boards(self) -> None:
        self.assertEqual(507, len(self.companies))
        self.assertEqual(
            498,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )
        self.assertEqual(
            543,
            sum(1 + len(item.get("aliases", [])) for item in self.companies.values()),
        )

    def test_new_official_sources_are_enabled(self) -> None:
        self.assertEqual("greenhouse", self.companies["Take-Two Interactive"]["ats"])
        self.assertEqual("taketwo", self.companies["Take-Two Interactive"]["slug"])
        self.assertEqual("jibe_api", self.companies["Schneider Electric"]["ats"])
        self.assertEqual(
            {"country": "India"},
            self.companies["Schneider Electric"]["query_params"],
        )
        self.assertEqual("direct_job_html", self.companies["Grammarly"]["ats"])
        self.assertEqual(
            "verified_no_current_jobs",
            self.companies["Grammarly"]["source_status"],
        )
        self.assertIn("Superhuman", self.companies["Grammarly"]["aliases"])
        for name in ("Take-Two Interactive", "Schneider Electric", "Grammarly"):
            self.assertTrue(self.companies[name]["enabled"])

    def test_workflow_runs_v32_or_newer(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("python job_monitor_entry_v31.py", workflow)
        self.assertIn('cron: "7 */2 * * *"', workflow)
        self.assertIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
