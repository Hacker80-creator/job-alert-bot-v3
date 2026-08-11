from __future__ import annotations

import re
import unittest
from pathlib import Path

import job_monitor_entry_v42


class ProductionV42Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v42.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_two_sources(self) -> None:
        self.assertEqual(539, len(self.companies))
        self.assertEqual(530, sum(1 for item in self.companies.values() if item.get("enabled", True)))
        self.assertEqual(578, sum(1 + len(item.get("aliases", [])) for item in self.companies.values()))

    def test_sources_are_enabled(self) -> None:
        expected = {"MediaTek": "mediatek", "Nagarro": "nagarro_azure"}
        for name, ats in expected.items():
            self.assertEqual(ats, self.companies[name]["ats"])

    def test_workflow_runs_v42_or_newer(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml").read_text(encoding="utf-8")
        entry = re.search(r"python job_monitor_entry_v(\d+)\.py", workflow)
        overrides = re.search(r"--overrides-file source_overrides_v(\d+)\.yaml", workflow)
        self.assertIsNotNone(entry)
        self.assertIsNotNone(overrides)
        self.assertGreaterEqual(int(entry.group(1)), 42)
        self.assertGreaterEqual(int(overrides.group(1)), 40)


if __name__ == "__main__":
    unittest.main()
