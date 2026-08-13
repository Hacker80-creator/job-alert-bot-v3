from __future__ import annotations

import re
import unittest
from pathlib import Path

import job_monitor_entry_v33


class ProductionV33Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v33.load_final_config()
        self.companies = {item["name"]: item for item in self.config["companies"]}

    def test_registry_counts_include_structured_listing_batch(self) -> None:
        self.assertEqual(509, len(self.companies))
        self.assertEqual(
            500,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )
        self.assertEqual(
            545,
            sum(1 + len(item.get("aliases", [])) for item in self.companies.values()),
        )

    def test_healthifyme_and_moengage_are_enabled(self) -> None:
        self.assertEqual("listing_jsonld", self.companies["HealthifyMe"]["ats"])
        self.assertEqual("trakstar_html", self.companies["MoEngage"]["ats"])
        self.assertTrue(self.companies["HealthifyMe"]["enabled"])
        self.assertTrue(self.companies["MoEngage"]["enabled"])

    def test_workflow_runs_v33_or_newer(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        entry = re.search(r"python job_monitor_entry_v(\d+)\.py", workflow)
        overrides = re.search(r"--overrides-file (?:source_overrides_v(\d+)\.yaml|verified_sources_v44\.txt)", workflow)
        self.assertIsNotNone(entry)
        self.assertIsNotNone(overrides)
        self.assertGreaterEqual(int(entry.group(1)), 33)
        if overrides.group(1) is not None:
            self.assertGreaterEqual(int(overrides.group(1)), 31)


if __name__ == "__main__":
    unittest.main()
