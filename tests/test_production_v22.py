from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v22


class ProductionV22Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v22.load_final_config()
        self.companies = {
            item["name"]: item for item in self.config["companies"]
        }

    def test_registry_is_unique_and_enabled_count_is_explicit(self) -> None:
        self.assertEqual(410, len(self.companies))
        self.assertEqual(
            400,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_zero_result_legacy_sources_use_live_official_feeds(self) -> None:
        expected = {
            "PayPal": ("eightfold", "paypal.eightfold.ai/api/pcsx/search"),
            "Adobe": ("workday_search", "/wday/cxs/adobe/"),
            "Mastercard": ("workday_search", "/wday/cxs/mastercard/"),
            "Philips": ("workday_search", "/wday/cxs/philips/"),
            "Oracle": ("oracle_hcm", "recruitingCEJobRequisitions"),
            "Google": ("google_careers_html", "/applications/jobs/results/"),
            "CGI": ("njoyn_html", "cgi.njoyn.com/"),
            "Salesforce": ("workday_search", "/wday/cxs/salesforce/"),
            "Akamai": ("oracle_hcm", "recruitingCEJobRequisitions"),
            "HubSpot": ("greenhouse", "hubspotjobs"),
            "MakeMyTrip": ("makemytrip_api", "/api/jobs"),
            "Zoho": ("zoho_careers_html", "zohocorp.com/jobs/Careers"),
            "Booking.com": ("jibe_api", "jobs.booking.com/api/jobs"),
            "OneStream": ("ukg_jobboard", "LoadSearchResults"),
            "Walmart Global Tech": ("walmart_graphql", "careers.walmart.com/api/graphql"),
        }
        for name, (ats, url_part) in expected.items():
            with self.subTest(company=name):
                company = self.companies[name]
                self.assertTrue(company["enabled"])
                self.assertEqual(ats, company["ats"])
                source_identity = " ".join(str(company.get(key, "")) for key in (
                    "url", "slug", "career_site_url"
                ))
                self.assertIn(url_part, source_identity)
                self.assertNotEqual("html_search", company["ats"])

    def test_sources_without_public_boards_are_not_fake_scanners(self) -> None:
        for name in ("Myntra", "FreshToHome", "Flipkart"):
            with self.subTest(company=name):
                company = self.companies[name]
                self.assertFalse(company["enabled"])
                self.assertIn(company["source_status"], {
                    "no_public_board", "login_required", "dynamic_no_direct_urls",
                })
                self.assertTrue(company["source_note"])

    def test_workflow_runs_v22_every_half_hour_with_write_permission(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("python job_monitor_entry_v22.py", workflow)
        entry = (Path(__file__).parents[1] / "job_monitor_entry_v22.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "custom_source_parsers_v14.fetch_company_jobs_with_custom_v14",
            entry,
        )
        self.assertIn('MAX_SOURCE_WORKERS: "16"', workflow)


if __name__ == "__main__":
    unittest.main()