from __future__ import annotations

import unittest
from pathlib import Path

import yaml

import job_monitor_entry_v3


class SecondSourceOverrideTests(unittest.TestCase):
    def test_four_verified_repairs(self) -> None:
        path = Path(__file__).parents[1] / "source_overrides_v2.yaml"
        companies = (yaml.safe_load(path.read_text(encoding="utf-8")) or {})["companies"]
        self.assertEqual(4, len(companies))
        self.assertEqual(
            {"BrowserStack", "Razorpay", "Target", "Zoom"},
            {item["name"] for item in companies},
        )
        self.assertTrue(all(item.get("verified_job_count", 0) > 0 for item in companies))

    def test_full_loader_applies_both_override_batches(self) -> None:
        config = job_monitor_entry_v3.load_config_with_all_overrides()
        companies = {item["name"]: item for item in config["companies"]}
        self.assertEqual("ashby", companies["OpenAI"]["ats"])
        self.assertEqual("workday_search", companies["BrowserStack"]["ats"])
        self.assertEqual("razorpaysoftwareprivatelimited", companies["Razorpay"]["slug"])
        self.assertEqual("workday_search", companies["Target"]["ats"])
        self.assertEqual("https://careers.zoom.us/jobs/search", companies["Zoom"]["url"])


if __name__ == "__main__":
    unittest.main()
