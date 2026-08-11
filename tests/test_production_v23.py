from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v23


class ProductionV23Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v23.load_final_config()
        self.companies = {
            item["name"]: item for item in self.config["companies"]
        }

    def test_registry_is_unique_and_enabled_count_is_explicit(self) -> None:
        self.assertEqual(423, len(self.config["companies"]))
        self.assertEqual(423, len(self.companies))
        self.assertEqual(
            413,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_recovered_sources_use_parser_supported_official_feeds(self) -> None:
        expected = {
            "Acko": ("kula_html", "careers.kula.ai/acko?jobs=true"),
            "Acer": ("successfactors_search", "careers.acer.com/search/"),
            "Aptiv": ("workday_india", "/wday/cxs/aptiv/APTIV_CAREERS/jobs"),
            "Automation Anywhere": ("workday_india", "/wday/cxs/automationanywhere/"),
            "Birlasoft": ("successfactors_search", "jobs.birlasoft.com/search/"),
            "BlackLine": ("workday_search", "/wday/cxs/blackline/BlackLineCareers/jobs"),
            "Boehringer Ingelheim": ("successfactors_search", "jobs.boehringer-ingelheim.com/search/"),
            "Box": ("greenhouse", "boxinc"),
            "Bristol Myers Squibb": ("workday_india", "/wday/cxs/bristolmyerssquibb/BMS/jobs"),
            "Chainalysis": ("ashby", "chainalysis-careers"),
            "Chevron": ("talentbrew_html", "careers.chevron.com/search-jobs"),
            "Clari": ("lever", "clari"),
            "Pocket FM": ("lever", "pocketfm"),
        }
        for name, (ats, identity) in expected.items():
            with self.subTest(company=name):
                company = self.companies[name]
                self.assertTrue(company["enabled"])
                self.assertEqual(ats, company["ats"])
                source_identity = " ".join(
                    str(company.get(key, ""))
                    for key in ("url", "slug", "career_site_url")
                )
                self.assertIn(identity, source_identity)
                self.assertNotEqual("html_search", company["ats"])

    def test_alternate_labels_reuse_working_parent_sources(self) -> None:
        expected_aliases = {
            "CVS Health": "Aetna",
            "Amgen India": "Amgen",
            "Boeing": "Boeing India",
            "Bosch Group": "Bosch Global Software Technologies",
            "Cadence": "Cadence Design Systems",
            "Fivetran": "Census",
        }
        for parent, alias in expected_aliases.items():
            with self.subTest(parent=parent, alias=alias):
                company = self.companies[parent]
                self.assertTrue(company["enabled"])
                self.assertIn(alias, company["aliases"])

    def test_workflow_runs_v23_on_the_existing_half_hour_schedule(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("python job_monitor_entry_v23.py", workflow)
        self.assertNotIn("python job_monitor_entry_v22.py", workflow)


if __name__ == "__main__":
    unittest.main()
