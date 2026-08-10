from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v18


class ProductionV18Tests(unittest.TestCase):
    def test_dell_and_intel_use_verified_first_party_sources(self) -> None:
        companies = {
            item["name"]: item
            for item in job_monitor_entry_v18.load_final_config()["companies"]
        }
        self.assertEqual("oracle_hcm", companies["Dell Technologies"]["ats"])
        self.assertEqual("careers", companies["Dell Technologies"]["site_number"])
        self.assertEqual("workday_faceted", companies["Intel"]["ats"])
        self.assertEqual(
            ["1e4a4eb3adf101f44070f976bf8184cf"],
            companies["Intel"]["applied_facets"]["locations"],
        )
        self.assertIn("DevOps", companies["Qualcomm"]["search_terms"])

    def test_registry_counts_and_resume_profile_are_current(self) -> None:
        config = job_monitor_entry_v18.load_final_config()
        companies = config["companies"]
        names = [str(item["name"]).casefold() for item in companies]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(263, len(companies))
        self.assertEqual(262, sum(1 for item in companies if item.get("enabled", True)))
        self.assertIn("Jenkins", config["settings"]["target_profile"])
        self.assertIn("Platform Engineer", config["settings"]["target_profile"])

    def test_workflow_runs_resume_aware_entry_point(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("python job_monitor_entry_v18.py", workflow)


if __name__ == "__main__":
    unittest.main()
