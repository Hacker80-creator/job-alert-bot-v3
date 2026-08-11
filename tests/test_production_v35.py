from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v35


class ProductionV35Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v35.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_zwayam_and_keka_batch(self) -> None:
        self.assertEqual(519, len(self.companies))
        self.assertEqual(510, sum(1 for item in self.companies.values() if item.get("enabled", True)))
        self.assertEqual(556, sum(1 + len(item.get("aliases", [])) for item in self.companies.values()))

    def test_sources_are_machine_readable(self) -> None:
        for name in ("Cyient", "Curefit", "Info Edge", "Livspace", "Torry Harris Integration Solutions"):
            self.assertEqual("tavant_browser_transport", self.companies[name]["ats"])
        for name in ("Jupiter Money", "Open Financial Technologies"):
            self.assertEqual("keka_embed", self.companies[name]["ats"])
        self.assertIn("Naukri.com", self.companies["Info Edge"]["aliases"])

    def test_workflow_runs_v35_or_newer(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml").read_text(encoding="utf-8")
        self.assertNotIn("python job_monitor_entry_v34.py", workflow)


if __name__ == "__main__":
    unittest.main()
