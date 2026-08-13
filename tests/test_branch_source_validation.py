from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import branch_source_validation as validation
import job_monitor as bot


class BranchSourceValidationTests(unittest.TestCase):
    def tearDown(self) -> None:
        bot.SCAN_ERRORS.clear()

    @patch("branch_source_validation.job_monitor_parallel.parse_workable")
    @patch("branch_source_validation.custom_source_parsers_v30.fetch_company_jobs_with_custom_v30")
    def test_validate_source_uses_production_workable_adapter(
        self, custom_fetch, workable_fetch
    ) -> None:
        workable_fetch.return_value = [
            bot.Job(
                "Example",
                "Data Analyst",
                "Bangalore",
                "https://apply.workable.com/example/j/1",
                "Official",
            )
        ]

        result = validation.validate_source(
            {"name": "Example", "ats": "workable", "slug": "example"}
        )

        self.assertEqual("WORKING", result["status"])
        self.assertEqual(1, result["job_count"])
        workable_fetch.assert_called_once()
        custom_fetch.assert_not_called()

    @patch("branch_source_validation.time.sleep")
    @patch("branch_source_validation.custom_source_parsers_v30.fetch_company_jobs_with_custom_v30")
    def test_validate_source_retries_swallowed_transient_error(
        self, fetch, sleep
    ) -> None:
        attempts = 0

        def transient_then_success(company):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                bot.SCAN_ERRORS.append(company["name"])
                return []
            return [bot.Job(
                company["name"], "Data Analyst", "Bangalore",
                "https://example/jobs/1", "Official",
            )]

        fetch.side_effect = transient_then_success
        result = validation.validate_source({"name": "Example", "ats": "custom"})

        self.assertEqual("WORKING", result["status"])
        self.assertEqual(2, fetch.call_count)
        sleep.assert_called_once_with(1)

    @patch("branch_source_validation.custom_source_parsers_v30.fetch_company_jobs_with_custom_v30")
    def test_empty_success_is_labeled_as_no_current_match(self, fetch) -> None:
        fetch.return_value = []
        result = validation.validate_source({"name": "Example", "ats": "custom"})
        self.assertEqual("NO_CURRENT_MATCHING_JOBS", result["status"])

    @patch("branch_source_validation.assess_direct_source")
    @patch("branch_source_validation.custom_source_parsers_v30.fetch_company_jobs_with_custom_v30")
    def test_empty_generic_page_remains_unresolved(self, fetch, assess) -> None:
        fetch.return_value = []
        assess.return_value = {
            "monitorable": False,
            "evidence": "no_verifiable_job_records",
        }
        result = validation.validate_source({
            "name": "Example", "ats": "direct_job_html", "url": "https://example/jobs"
        })
        self.assertEqual("UNRESOLVED_DYNAMIC_SOURCE", result["status"])
        self.assertEqual(
            "no_verifiable_job_records", result["monitor_evidence"]["evidence"]
        )

    @patch("branch_source_validation.assess_direct_source")
    @patch("branch_source_validation.custom_source_parsers_v30.fetch_company_jobs_with_custom_v30")
    def test_empty_server_rendered_board_is_still_monitored(self, fetch, assess) -> None:
        fetch.return_value = []
        assess.return_value = {
            "monitorable": True,
            "evidence": "server_rendered_job_links",
            "record_count": 7,
        }
        result = validation.validate_source({
            "name": "Example", "ats": "direct_job_html", "url": "https://example/jobs"
        })
        self.assertEqual("NO_CURRENT_MATCHING_JOBS", result["status"])
        self.assertEqual(7, result["monitor_evidence"]["record_count"])

    @patch("branch_source_validation.requests.get")
    def test_assess_direct_source_accepts_explicit_empty_state(self, get) -> None:
        response = get.return_value
        response.text = "<main>We currently have no open positions.</main>"
        response.url = "https://example/jobs"

        result = validation.assess_direct_source({"url": response.url})

        self.assertTrue(result["monitorable"])
        self.assertEqual("explicit_no_openings", result["evidence"])
        response.raise_for_status.assert_called_once()

    @patch("branch_source_validation.requests.get")
    def test_assess_direct_source_requires_specific_job_link(self, get) -> None:
        response = get.return_value
        response.text = (
            '<a href="/careers">Careers</a>'
            '<a href="/jobs/data-platform-engineer">Data Platform Engineer</a>'
        )
        response.url = "https://example/jobs"

        result = validation.assess_direct_source({"url": response.url})

        self.assertTrue(result["monitorable"])
        self.assertEqual("server_rendered_job_links", result["evidence"])
        self.assertEqual(1, result["record_count"])

    def test_source_names_reads_only_enabled_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.txt"
            path.write_text("Working|https://example.com/jobs\n", encoding="utf-8")
            self.assertEqual(["Working"], validation.source_names(path))

    @patch("branch_source_validation.job_monitor_entry_v44.load_final_config")
    @patch("branch_source_validation.custom_source_parsers_v30.fetch_company_jobs_with_custom_v30")
    def test_run_writes_non_mutating_summary(self, fetch, load_config) -> None:
        fetch.return_value = [
            bot.Job("Example", "Data Analyst", "Bangalore", "https://example/jobs/1", "Official")
        ]
        load_config.return_value = {
            "companies": [{"name": "Example", "ats": "greenhouse", "enabled": True}]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = root / "batch.txt"
            output = root / "summary.json"
            batch.write_text("Example|https://example.com/jobs\n", encoding="utf-8")
            code = validation.run(batch, output, workers=1)
            summary = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(0, code)
        self.assertEqual(1, summary["working"])
        self.assertEqual(0, summary["failed"])
        self.assertEqual("https://example/jobs/1", summary["results"][0]["sample_jobs"][0]["url"])


if __name__ == "__main__":
    unittest.main()
