from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import job_match_resume
import job_monitor as bot
import merge_job_state
import qa_job_alerts as qa
import custom_source_parsers_v3 as source_parsers_v3
from qa_company_sources import QA_ONLY_COMPANY_NAMES
from qa_role_filter import is_qa_title


ROOT = Path(__file__).parents[1]


class QAAlertTests(unittest.TestCase):
    def make_job(self, title: str, *, description: str = "") -> bot.Job:
        return bot.Job(
            company="Example",
            title=title,
            location="Bengaluru, Karnataka, India",
            url="https://example.test/jobs/qa-1",
            source="Official careers: test",
            description=description,
        )

    def test_requested_qa_titles_are_accepted(self) -> None:
        for title in (
            "QA Engineer",
            "Quality Assurance Engineer",
            "QA Analyst",
            "Software Test Engineer",
            "Manual Tester",
            "Functional Test Engineer",
            "QA Automation Engineer",
            "SDET",
            "Software Development Engineer in Test",
            "API Test Engineer",
            "Performance Test Engineer",
            "Mobile Test Engineer",
            "Validation Engineer",
            "Graduate Engineer Trainee - Testing",
            "QA Intern",
        ):
            with self.subTest(title=title):
                self.assertTrue(is_qa_title(title))

    def test_non_qa_ml_and_plain_automation_titles_are_rejected(self) -> None:
        for title in (
            "Machine Learning Engineer",
            "Data Scientist",
            "Data Analyst",
            "Automation Engineer",
            "Software Engineer",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_qa_title(title))

    def test_qa_scoring_accepts_early_contract_and_internship_roles(self) -> None:
        settings = qa.load_qa_config()["settings"]
        for job in (
            self.make_job("QA Intern"),
            self.make_job("Junior QA Engineer", description="Six-month contract role"),
            self.make_job("Test Engineer", description="Experience: 1-3 years"),
        ):
            with self.subTest(title=job.title):
                score, _ = qa.qa_score_job(job, settings)
                self.assertGreaterEqual(score, 70)

    def test_qa_scoring_rejects_senior_foreign_and_four_year_roles(self) -> None:
        settings = qa.load_qa_config()["settings"]
        cases = (
            self.make_job("Senior QA Engineer"),
            self.make_job("QA Engineer", description="Minimum 4 years required"),
            bot.Job("Example", "QA Engineer", "London, UK", "https://example.test/jobs/2", "test"),
        )
        for job in cases:
            with self.subTest(title=job.title, location=job.location):
                score, _ = qa.qa_score_job(job, settings)
                self.assertEqual(0, score)

    def test_ml_matcher_excludes_qa_titles_but_keeps_ml(self) -> None:
        settings = qa.load_qa_config()["settings"]
        score, reasons = job_match_resume.resume_score_job(
            self.make_job("QA Automation Engineer", description="Selenium Python Jenkins"),
            settings,
        )
        self.assertEqual(0, score)
        self.assertIn("QA/testing roles", reasons[0])
        self.assertFalse(is_qa_title("Machine Learning Engineer"))

    def test_qa_config_reuses_production_and_isolates_extra_companies(self) -> None:
        production = qa.job_monitor_entry_v44.load_final_config()
        qa_config = qa.load_qa_config()
        production_names = {item["name"] for item in production["companies"]}
        qa_names = {item["name"] for item in qa_config["companies"]}
        self.assertTrue(set(QA_ONLY_COMPANY_NAMES).issubset(qa_names))
        self.assertTrue({"TCS", "Infosys", "Wipro"}.isdisjoint(production_names))
        self.assertGreater(len(qa_names), len(production_names))

    def test_qa_zwayam_sources_use_verified_tenant_configuration(self) -> None:
        companies = {
            item["name"]: item for item in qa.load_qa_config()["companies"]
        }
        self.assertEqual("MTUxNzM=", companies["Coforge"]["company_id"])
        self.assertEqual("MTYzNDQ=", companies["Persistent Systems"]["company_id"])
        for name in ("Coforge", "Persistent Systems"):
            with self.subTest(company=name):
                self.assertEqual("zwayam_hardened", companies[name]["ats"])
                self.assertEqual(
                    "{portal}/jobview/{slug}",
                    companies[name]["job_path_template"],
                )

    def test_repaired_sources_use_first_party_machine_readable_feeds(self) -> None:
        companies = {
            item["name"]: item for item in qa.load_qa_config()["companies"]
        }
        self.assertEqual("infosys_api", companies["Infosys"]["ats"])
        self.assertIn("infosysapps.com", companies["Infosys"]["url"])
        self.assertEqual("phenom_content_api", companies["Virtusa"]["ats"])
        self.assertIn("phenompeople.com", companies["Virtusa"]["url"])
        self.assertEqual("icims_html", companies["Expleo"]["ats"])
        self.assertIn("expleo-jobs-in-en.icims.com", companies["Expleo"]["url"])
        self.assertTrue(companies["Expleo"]["minimal_browser_headers"])
        self.assertTrue(companies["Expleo"]["curl_browser_transport"])

    def test_infosys_api_parser_builds_direct_official_job_url(self) -> None:
        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> list[dict]:
                return [{
                    "postingTitle": "QA Engineer",
                    "location": "Bangalore",
                    "referenceCode": "INFSYS-123",
                    "sourceId": 21,
                    "minExperienceLevel": 1,
                    "maxExperienceLevel": 3,
                    "postingDescription": "API and functional testing",
                }]

        original_get = qa.requests.get
        try:
            qa.requests.get = lambda *args, **kwargs: Response()
            jobs = qa.parse_infosys_api({
                "name": "Infosys",
                "url": "https://example.test/infosys-api",
            })
        finally:
            qa.requests.get = original_get
        self.assertEqual(1, len(jobs))
        self.assertEqual("INFSYS-123", jobs[0].requisition_id)
        self.assertEqual(
            "https://career.infosys.com/jobdesc?"
            "jobReferenceCode=INFSYS-123&sourceId=21",
            jobs[0].url,
        )

    def test_phenom_content_parser_builds_verified_virtusa_job_url(self) -> None:
        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "refineSearch": {
                        "totalHits": 1,
                        "data": {"jobs": [{
                            "jobId": "CREQ265293",
                            "title": "QA Engineer",
                            "location": "Bengaluru, Karnataka, India",
                            "experience": "2",
                            "descriptionTeaser": "Functional and API testing",
                        }]},
                    }
                }

        original_get = qa.requests.get
        try:
            qa.requests.get = lambda *args, **kwargs: Response()
            jobs = qa.parse_phenom_content_api({
                "name": "Virtusa",
                "url": "https://example.test/phenom-api",
                "career_site_url": (
                    "https://www.virtusa.com/careers/job-search/global/en"
                ),
                "search_terms": ["QA"],
                "page_size": 10,
            })
        finally:
            qa.requests.get = original_get
        self.assertEqual(1, len(jobs))
        self.assertEqual(
            "https://www.virtusa.com/careers/job-search/global/en/"
            "job/CREQ265293/QA-Engineer",
            jobs[0].url,
        )

    def test_zwayam_parser_supports_company_jobview_urls(self) -> None:
        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "data": {
                        "data": [{
                            "_source": {
                                "jobTitle": "QA Engineer",
                                "jobUrl": "qa-engineer-india-123",
                                "location": "Bengaluru",
                            }
                        }],
                        "hasMoreData": False,
                    }
                }

        original_post = source_parsers_v3.requests.post
        try:
            source_parsers_v3.requests.post = lambda *args, **kwargs: Response()
            jobs = source_parsers_v3.parse_zwayam_hardened({
                "name": "Example",
                "url": "https://public.zwayam.com/jobs/search",
                "career_site_url": "https://careers.example.com",
                "domain": "careers.example.com",
                "company_id": "MTIz",
                "job_path_template": "{portal}/jobview/{slug}",
            })
        finally:
            source_parsers_v3.requests.post = original_post
        self.assertEqual(
            "https://careers.example.com/jobview/qa-engineer-india-123",
            jobs[0].url,
        )

    def test_qa_runtime_uses_separate_webhook_and_state(self) -> None:
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
        original_loader = qa.job_monitor_parallel.load_merged_config
        try:
            qa.configure_runtime()
            self.assertEqual(qa.QA_STATE_FILE, bot.STATE_FILE)
            self.assertEqual(qa.QA_HEALTH_FILE, bot.HEALTH_FILE)
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
            qa.job_monitor_parallel.load_merged_config = original_loader

    def test_qa_workflow_is_independent_and_secret_safe(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "qa-job-alerts.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "37 */2 * * *"', workflow)
        self.assertIn("group: qa-job-alert-bot-persistent-state", workflow)
        self.assertIn("QA_DISCORD_WEBHOOK_URL: ${{ secrets.QA_DISCORD_WEBHOOK_URL }}", workflow)
        self.assertNotIn("DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}", workflow)
        self.assertIn("seen_qa_jobs.json", workflow)
        self.assertIn("qa_scan_health.json", workflow)
        self.assertIn("github.ref_name == 'main'", workflow)

    def test_merge_state_supports_independent_qa_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generated = root / "generated"
            state = root / "state"
            generated.mkdir()
            state.mkdir()
            (generated / "seen_qa_jobs.json").write_text('{"new": {}}', encoding="utf-8")
            (state / "seen_qa_jobs.json").write_text('{"old": {}}', encoding="utf-8")
            (generated / "qa_scan_health.json").write_text('{"ok": true}', encoding="utf-8")
            merge_job_state.merge_state(
                generated,
                state,
                seen_file="seen_qa_jobs.json",
                health_file="qa_scan_health.json",
            )
            self.assertEqual(
                {"new": {}, "old": {}},
                merge_job_state.read_object(state / "seen_qa_jobs.json"),
            )
            self.assertEqual(
                {"ok": True},
                merge_job_state.read_object(state / "qa_scan_health.json"),
            )


if __name__ == "__main__":
    unittest.main()
