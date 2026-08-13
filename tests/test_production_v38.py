from __future__ import annotations

import re
import unittest
from pathlib import Path

import job_monitor_entry_v38


class ProductionV38Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v38.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_first_party_sources(self) -> None:
        self.assertEqual(526, len(self.companies))
        self.assertEqual(517, sum(1 for item in self.companies.values() if item.get("enabled", True)))
        self.assertEqual(564, sum(1 + len(item.get("aliases", [])) for item in self.companies.values()))

    def test_sources_are_enabled(self) -> None:
        self.assertEqual("wordpress_job_links", self.companies["CredAble"]["ats"])
        self.assertEqual("dataweave_jobs", self.companies["DataWeave"]["ats"])
        self.assertEqual("skima_html", self.companies["Nykaa"]["ats"])

    def test_workflow_runs_v38_or_newer(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml").read_text(encoding="utf-8")
        entry = re.search(r"python job_monitor_entry_v(\d+)\.py", workflow)
        overrides = re.search(r"--overrides-file (?:source_overrides_v(\d+)\.yaml|verified_sources_v44\.txt)", workflow)
        self.assertIsNotNone(entry)
        self.assertIsNotNone(overrides)
        self.assertGreaterEqual(int(entry.group(1)), 38)
        if overrides.group(1) is not None:
            self.assertGreaterEqual(int(overrides.group(1)), 36)


if __name__ == "__main__":
    unittest.main()
