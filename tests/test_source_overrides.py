from __future__ import annotations

import unittest
from pathlib import Path

import yaml

import job_monitor_entry_v2


class SourceOverrideTests(unittest.TestCase):
    def test_eight_verified_repairs_and_no_test_uber_source(self) -> None:
        path = Path(__file__).parents[1] / "source_overrides.yaml"
        companies = (yaml.safe_load(path.read_text(encoding="utf-8")) or {})["companies"]
        self.assertEqual(8, len(companies))
        names = {item["name"] for item in companies}
        self.assertEqual(
            {"CRED", "Confluent", "Freshworks", "Meesho", "Notion", "OpenAI", "Snowflake", "Swiggy"},
            names,
        )
        self.assertNotIn("Uber", names)

    def test_override_preserves_ranking_metadata(self) -> None:
        config = {"companies": [{
            "name": "Example", "kind": "product", "wlb_score": 5,
            "ats": "greenhouse", "slug": "old", "enabled": True,
        }]}
        updated = job_monitor_entry_v2.apply_overrides(config, [{
            "name": "Example", "ats": "ashby", "slug": "new", "enabled": True,
        }])
        company = updated["companies"][0]
        self.assertEqual("ashby", company["ats"])
        self.assertEqual("new", company["slug"])
        self.assertEqual(5, company["wlb_score"])


if __name__ == "__main__":
    unittest.main()
