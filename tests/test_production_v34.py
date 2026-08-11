from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v34


class ProductionV34Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v34.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_recovered_board_batch(self) -> None:
        self.assertEqual(512, len(self.companies))
        self.assertEqual(503, sum(1 for item in self.companies.values() if item.get("enabled", True)))
        self.assertEqual(548, sum(1 + len(item.get("aliases", [])) for item in self.companies.values()))

    def test_recovered_boards_are_enabled(self) -> None:
        self.assertEqual("ripplehire", self.companies["Tata Technologies"]["ats"])
        self.assertEqual("ripplehire", self.companies["UST"]["ats"])
        self.assertEqual("zoho_careers_html", self.companies["Yubi"]["ats"])
        self.assertEqual(1000, self.companies["UST"]["max_results"])

    def test_workflow_runs_v34_or_newer(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml").read_text(encoding="utf-8")
        self.assertNotIn("python job_monitor_entry_v33.py", workflow)


if __name__ == "__main__":
    unittest.main()
