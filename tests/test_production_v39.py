from __future__ import annotations

import re
import unittest
from pathlib import Path

import job_monitor_entry_v39


class ProductionV39Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v39.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_four_sources_and_moj_alias(self) -> None:
        self.assertEqual(530, len(self.companies))
        self.assertEqual(521, sum(1 for item in self.companies.values() if item.get("enabled", True)))
        self.assertEqual(569, sum(1 + len(item.get("aliases", [])) for item in self.companies.values()))

    def test_sources_are_enabled(self) -> None:
        self.assertEqual("urban_company", self.companies["Urban Company"]["ats"])
        self.assertEqual("sharechat_careers", self.companies["ShareChat"]["ats"])
        self.assertIn("Moj", self.companies["ShareChat"]["aliases"])
        self.assertEqual("river_careers", self.companies["River Mobility"]["ats"])
        self.assertEqual("keka_embed", self.companies["Scrut Automation"]["ats"])

    def test_workflow_runs_v39_or_newer(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml").read_text(encoding="utf-8")
        entry = re.search(r"python job_monitor_entry_v(\d+)\.py", workflow)
        overrides = re.search(r"--overrides-file (?:source_overrides_v(\d+)\.yaml|verified_sources_v44\.txt)", workflow)
        self.assertIsNotNone(entry)
        self.assertIsNotNone(overrides)
        self.assertGreaterEqual(int(entry.group(1)), 39)
        if overrides.group(1) is not None:
            self.assertGreaterEqual(int(overrides.group(1)), 37)


if __name__ == "__main__":
    unittest.main()
