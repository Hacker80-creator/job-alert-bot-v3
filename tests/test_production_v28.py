from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v28


class ProductionV28Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v28.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_public_api_batch(self) -> None:
        self.assertEqual(495, len(self.companies))
        self.assertEqual(
            485,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_enphase_and_pega_sources_are_enabled(self) -> None:
        self.assertEqual("enphase_api", self.companies["Enphase Energy"]["ats"])
        self.assertEqual("pega_html", self.companies["Pegasystems"]["ats"])
        self.assertTrue(self.companies["Enphase Energy"]["enabled"])
        self.assertTrue(self.companies["Pegasystems"]["enabled"])

    def test_workflow_runs_v28_or_newer(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertRegex(workflow, r"python job_monitor_entry_v(?:2[8-9]|[3-9]\d+)\.py")
        self.assertIn('cron: "7 */2 * * *"', workflow)
        self.assertIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
