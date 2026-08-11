from __future__ import annotations

import re
import unittest
from pathlib import Path

import job_monitor_entry_v37


class ProductionV37Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v37.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_goldman_and_infineon(self) -> None:
        self.assertEqual(523, len(self.companies))
        self.assertEqual(514, sum(1 for item in self.companies.values() if item.get("enabled", True)))
        self.assertEqual(561, sum(1 + len(item.get("aliases", [])) for item in self.companies.values()))

    def test_goldman_and_infineon_sources_are_enabled(self) -> None:
        self.assertEqual("goldman_higher", self.companies["Goldman Sachs"]["ats"])
        self.assertEqual("eightfold", self.companies["Infineon Technologies"]["ats"])
        self.assertEqual("infineon.com", self.companies["Infineon Technologies"]["domain"])

    def test_workflow_runs_v37_or_newer(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml").read_text(encoding="utf-8")
        entry = re.search(r"python job_monitor_entry_v(\d+)\.py", workflow)
        overrides = re.search(r"--overrides-file source_overrides_v(\d+)\.yaml", workflow)
        self.assertIsNotNone(entry)
        self.assertIsNotNone(overrides)
        self.assertGreaterEqual(int(entry.group(1)), 37)
        self.assertGreaterEqual(int(overrides.group(1)), 35)


if __name__ == "__main__":
    unittest.main()
