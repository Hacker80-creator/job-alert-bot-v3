from __future__ import annotations

import re
import unittest
from pathlib import Path

import job_monitor_entry_v36


class ProductionV36Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v36.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_deel_and_gem(self) -> None:
        self.assertEqual(521, len(self.companies))
        self.assertEqual(512, sum(1 for item in self.companies.values() if item.get("enabled", True)))
        self.assertEqual(559, sum(1 + len(item.get("aliases", [])) for item in self.companies.values()))

    def test_deel_and_gem_sources_are_enabled(self) -> None:
        self.assertEqual("deel_next", self.companies["Klarna"]["ats"])
        self.assertEqual("gem_public", self.companies["Hasura"]["ats"])
        self.assertIn("PromptQL", self.companies["Hasura"]["aliases"])

    def test_workflow_runs_v36_or_newer(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml").read_text(encoding="utf-8")
        entry = re.search(r"python job_monitor_entry_v(\d+)\.py", workflow)
        overrides = re.search(r"--overrides-file source_overrides_v(\d+)\.yaml", workflow)
        self.assertIsNotNone(entry)
        self.assertIsNotNone(overrides)
        self.assertGreaterEqual(int(entry.group(1)), 36)
        self.assertGreaterEqual(int(overrides.group(1)), 34)


if __name__ == "__main__":
    unittest.main()
