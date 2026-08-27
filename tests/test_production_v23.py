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
        self.assertEqual(435, len(self.config["companies"]))
        self.assertEqual(435, len(self.companies))
        self.assertEqual(
            425,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_recovered_sources_use_parser_supported_official_feeds(self) -> None:
        expected = {
            "Acko": ("kula_html", "careers.kula.ai/acko?jobs=true"),
            "Amdocs": ("eightfold", "jobs.amdocs.com/api/pcsx/search"),
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
            "Domo": ("workday_search", "/wday/cxs/domo/DomoCareers/jobs"),
            "Ericsson": ("eightfold", "jobs.ericsson.com/api/pcsx/search"),
            "FedEx": ("workday_india", "/wday/cxs/fedex/FXE-MEISA-External/jobs"),
            "GE Vernova": ("workday_search", "/wday/cxs/gevernova/Vernova_ExternalSite/jobs"),
            "HP Inc.": ("eightfold", "apply.hp.com/api/pcsx/search"),
            "Innovaccer": ("workable", "api/accounts/innovaccer"),
            "Lam Research": ("eightfold", "lamresearch.eightfold.ai/api/pcsx/search"),
            "Nike": ("workday_search", "/wday/cxs/nike/nke/jobs"),
            "Pocket FM": ("lever", "pocketfm"),
            "Quantiphi": ("workday_search", "/wday/cxs/quantiphi/Careers_at_Quantiphi/jobs"),
            "Revvity": ("talentbrew_html", "jobs.revvity.com/search-jobs"),
            "S&P Global": ("workday_india", "/wday/cxs/spgi/SPGI_Careers/jobs"),
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
            "Google": "Looker",
            "MakeMyTrip": "Goibibo",
            "Oracle": "Oracle Health",
            "Twilio": "Segment",
        }
        for parent, alias in expected_aliases.items():
            with self.subTest(parent=parent, alias=alias):
                company = self.companies[parent]
                self.assertTrue(company["enabled"])
                self.assertIn(alias, company["aliases"])

        self.assertEqual(
            ["MuleSoft", "Slack", "Tableau"],
            self.companies["Salesforce"]["aliases"],
        )

    def test_workflow_runs_v23_on_the_existing_half_hour_schedule(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('cron: "7 */2 * * *"', workflow)
        self.assertIn("contents: write", workflow)
        self.assertRegex(workflow, r"python job_monitor_entry_v\d+\.py")


if __name__ == "__main__":
    unittest.main()
