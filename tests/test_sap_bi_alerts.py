from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import job_monitor as bot
import job_monitor_parallel
import merge_job_state
import qa_job_alerts
import sap_bi_job_alerts as sap_bi
from qa_role_filter import is_qa_title
from sap_bi_role_filter import (
    SAP_BI_ROLE_PHRASES,
    SAP_BI_SEARCH_TERMS,
    is_sap_bi_title,
    is_senior_sap_bi_title,
)


ROOT = Path(__file__).parents[1]


class SapBiAlertTests(unittest.TestCase):
    def make_job(
        self,
        title: str,
        *,
        description: str = "",
        location: str = "Bengaluru, Karnataka, India",
    ) -> bot.Job:
        return bot.Job(
            company="Example",
            title=title,
            location=location,
            url="https://example.test/jobs/sap-bi-1",
            source="Official careers: test",
            description=description,
        )

    def test_every_requested_title_is_in_the_strict_vocabulary(self) -> None:
        self.assertGreaterEqual(len(SAP_BI_ROLE_PHRASES), 59)
        for title in SAP_BI_ROLE_PHRASES:
            with self.subTest(title=title):
                self.assertTrue(is_sap_bi_title(title))

    def test_common_title_formatting_variants_are_accepted(self) -> None:
        for title in (
            "SAP UI5/Fiori Developer",
            "SAP BTP Extension Developer - Associate",
            "Power BI Developer (Junior)",
            "SQL Reporting Analyst - Contract",
            "Junior Data Engineer, India",
        ):
            with self.subTest(title=title):
                self.assertTrue(is_sap_bi_title(title))

    def test_unrelated_ml_qa_and_software_titles_are_rejected(self) -> None:
        for title in (
            "Machine Learning Engineer",
            "Data Scientist",
            "QA Automation Engineer",
            "Software Test Engineer",
            "Full Stack Developer",
            "Python Developer",
            "Data Engineer",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_sap_bi_title(title))

    def test_senior_titles_are_detected_separately(self) -> None:
        for title in (
            "Senior Power BI Developer",
            "Lead SAP Fiori Developer",
            "Principal Data Analyst",
        ):
            with self.subTest(title=title):
                self.assertTrue(is_sap_bi_title(title))
                self.assertTrue(is_senior_sap_bi_title(title))

    def test_scoring_accepts_requested_early_career_roles(self) -> None:
        settings = sap_bi.load_sap_bi_config()["settings"]
        cases = (
            self.make_job(
                "SAP UI5/Fiori Developer",
                description="1.5 years experience with SAP UI5, Fiori and OData",
            ),
            self.make_job(
                "Power BI Analyst",
                description="Associate role using Power BI, DAX and SQL",
            ),
            self.make_job(
                "Application Support Engineer",
                description="Contract role with application support and incident management",
                location="Remote, India",
            ),
            self.make_job("Data Analyst", description="1-2 years, SQL and reporting"),
        )
        for job in cases:
            with self.subTest(title=job.title):
                score, reasons = sap_bi.sap_bi_score_job(job, settings)
                self.assertGreaterEqual(score, 70)
                self.assertTrue(any("approved SAP/BI role" in reason for reason in reasons))

    def test_scoring_rejects_wrong_location_seniority_and_experience(self) -> None:
        settings = sap_bi.load_sap_bi_config()["settings"]
        cases = (
            self.make_job("Power BI Developer", location="London, UK"),
            self.make_job("Senior Power BI Developer"),
            self.make_job(
                "SAP Fiori Developer",
                description="Minimum 5 years of SAP Fiori experience required",
            ),
            self.make_job("QA Engineer"),
        )
        for job in cases:
            with self.subTest(title=job.title, location=job.location):
                score, _ = sap_bi.sap_bi_score_job(job, settings)
                self.assertEqual(0, score)

    def test_qa_and_sap_bi_title_vocabularies_are_separate(self) -> None:
        self.assertTrue(is_qa_title("QA Engineer"))
        self.assertFalse(is_sap_bi_title("QA Engineer"))
        self.assertTrue(is_sap_bi_title("SAP Fiori Developer"))
        self.assertFalse(is_qa_title("SAP Fiori Developer"))

    def test_config_reuses_exact_existing_combined_company_registry(self) -> None:
        combined = qa_job_alerts.load_qa_config()
        configured = sap_bi.load_sap_bi_config()
        combined_names = {item["name"] for item in combined["companies"]}
        configured_names = {item["name"] for item in configured["companies"]}
        self.assertEqual(combined_names, configured_names)
        self.assertGreaterEqual(
            len([item for item in configured["companies"] if item.get("enabled", True)]),
            750,
        )
        for company in configured["companies"]:
            self.assertEqual(list(SAP_BI_SEARCH_TERMS), company["search_terms"])
            if "zwayam_search_terms" in company:
                self.assertEqual(
                    list(SAP_BI_SEARCH_TERMS), company["zwayam_search_terms"]
                )

    def test_html_parser_keeps_only_requested_titles(self) -> None:
        html = """
        <ul>
          <li>Bengaluru, India <a href="/jobs/1">Power BI Developer</a></li>
          <li>Bengaluru, India <a href="/jobs/2">QA Engineer</a></li>
        </ul>
        """
        original_get_html = bot.get_html
        try:
            bot.get_html = lambda _url: html
            jobs = sap_bi.parse_sap_bi_html_search({
                "name": "Example",
                "url": "https://example.test/careers",
            })
        finally:
            bot.get_html = original_get_html
        self.assertEqual(1, len(jobs))
        self.assertEqual("Power BI Developer", jobs[0].title)
        self.assertEqual("https://example.test/jobs/1", jobs[0].url)

    def test_infosys_parser_queries_all_terms_and_deduplicates_jobs(self) -> None:
        requested_terms: list[str] = []

        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> list[dict]:
                return [{
                    "postingTitle": "Power BI Developer",
                    "location": "Bangalore",
                    "referenceCode": "INFSYS-BI-123",
                    "sourceId": 21,
                    "minExperienceLevel": 1,
                    "maxExperienceLevel": 3,
                    "postingDescription": "Power BI and SQL",
                }]

        def fake_get(url: str, **_kwargs: object) -> Response:
            requested_terms.extend(parse_qs(urlsplit(url).query).get("searchText", []))
            return Response()

        original_get = sap_bi.requests.get
        try:
            sap_bi.requests.get = fake_get
            jobs = sap_bi.parse_infosys_api({
                "name": "Infosys",
                "url": "https://example.test/careers?sourceId=1%2C21&searchText=QA",
                "search_terms": ["SAP UI5", "Power BI"],
            })
        finally:
            sap_bi.requests.get = original_get
        self.assertEqual(["SAP UI5", "Power BI"], requested_terms)
        self.assertEqual(1, len(jobs))
        self.assertEqual("INFSYS-BI-123", jobs[0].requisition_id)

    def test_runtime_uses_only_sap_bi_webhook_and_state(self) -> None:
        original_webhook = bot.DISCORD_WEBHOOK_URL
        original_state = bot.STATE_FILE
        original_health = bot.HEALTH_FILE
        original_title_matcher = bot.is_target_title
        original_scorer = bot.score_job
        original_html_parser = bot.parse_html_search
        original_workday_parser = bot.parse_workday_search
        original_smartrecruiters_parser = bot.parse_smartrecruiters
        original_lever_parser = bot.parse_lever
        original_fetch = bot.fetch_company_jobs
        original_loader = job_monitor_parallel.load_merged_config
        try:
            sap_bi.configure_runtime()
            self.assertEqual(sap_bi.SAP_BI_STATE_FILE, bot.STATE_FILE)
            self.assertEqual(sap_bi.SAP_BI_HEALTH_FILE, bot.HEALTH_FILE)
            self.assertNotEqual(qa_job_alerts.QA_STATE_FILE, bot.STATE_FILE)
            self.assertNotEqual(ROOT / "state" / "seen_jobs.json", bot.STATE_FILE)
        finally:
            bot.DISCORD_WEBHOOK_URL = original_webhook
            bot.STATE_FILE = original_state
            bot.HEALTH_FILE = original_health
            bot.is_target_title = original_title_matcher
            bot.score_job = original_scorer
            bot.parse_html_search = original_html_parser
            bot.parse_workday_search = original_workday_parser
            bot.parse_smartrecruiters = original_smartrecruiters_parser
            bot.parse_lever = original_lever_parser
            bot.fetch_company_jobs = original_fetch
            job_monitor_parallel.load_merged_config = original_loader

    def test_workflow_is_independent_secret_safe_and_two_hourly(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "sap-bi-job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('cron: "7 1-23/2 * * *"', workflow)
        self.assertIn("- feature/sap-bi-job-alerts", workflow)
        self.assertIn("group: sap-bi-job-bot-persistent-state", workflow)
        self.assertIn(
            "SAP_BI_DISCORD_WEBHOOK_URL: "
            "${{ secrets.SAP_BI_DISCORD_WEBHOOK_URL }}",
            workflow,
        )
        self.assertNotIn("${{ secrets.DISCORD_WEBHOOK_URL }}", workflow)
        self.assertNotIn("${{ secrets.QA_DISCORD_WEBHOOK_URL }}", workflow)
        self.assertIn("seen_sap_bi_jobs.json", workflow)
        self.assertIn("sap_bi_scan_health.json", workflow)
        self.assertIn("github.ref_name == 'main'", workflow)
        self.assertIn("github.ref_name != 'main'", workflow)
        self.assertIn("permissions:\n  contents: write", workflow)

    def test_merge_state_supports_independent_sap_bi_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generated = root / "generated"
            state = root / "state"
            generated.mkdir()
            state.mkdir()
            (generated / "seen_sap_bi_jobs.json").write_text(
                '{"new": {}}', encoding="utf-8"
            )
            (state / "seen_sap_bi_jobs.json").write_text(
                '{"old": {}}', encoding="utf-8"
            )
            (generated / "sap_bi_scan_health.json").write_text(
                '{"ok": true}', encoding="utf-8"
            )
            merge_job_state.merge_state(
                generated,
                state,
                seen_file="seen_sap_bi_jobs.json",
                health_file="sap_bi_scan_health.json",
            )
            self.assertEqual(
                {"new": {}, "old": {}},
                merge_job_state.read_object(state / "seen_sap_bi_jobs.json"),
            )
            self.assertEqual(
                {"ok": True},
                merge_job_state.read_object(state / "sap_bi_scan_health.json"),
            )


if __name__ == "__main__":
    unittest.main()
