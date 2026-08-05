from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import job_monitor as bot


class ReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = bot.load_config()
        cls.settings = cls.config["settings"]

    def test_latest_company_allowlist_is_loaded(self) -> None:
        names = bot.approved_company_names(self.config)
        self.assertGreaterEqual(len(names), 781)
        for required in ("LSEG", "JPMorgan Chase", "Morgan Stanley", "Moody's", "ABB", "CGI"):
            self.assertIn(required, names)

    def test_remote_india_is_accepted_but_foreign_remote_is_not(self) -> None:
        self.assertTrue(bot.has_location_match("Remote, India", self.settings))
        self.assertTrue(bot.has_location_match("India - Remote", self.settings))
        self.assertFalse(bot.has_location_match("Remote, United States", self.settings))

    def test_duplicate_fingerprint_ignores_url_changes(self) -> None:
        first = bot.Job("Example", "Data Analyst", "Bengaluru", "https://example/a", "one")
        second = bot.Job("Example", "Data Analyst", "Bengaluru", "https://example/b?tracking=1", "two")
        self.assertEqual(first.fingerprint, second.fingerprint)
        filtered = bot.filter_and_score([first, second], self.settings)
        self.assertEqual(len(filtered), 1)

    def test_seen_state_round_trip_keeps_duplicate_key(self) -> None:
        original_state_file = bot.STATE_FILE
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                bot.STATE_FILE = Path(temp_dir) / "seen_jobs.json"
                job = bot.Job("Example", "Data Analyst", "Remote, India", "https://example/job", "test")
                stored = {
                    job.fingerprint: {
                        "first_seen_utc": "2026-01-01T00:00:00+00:00",
                        "company": job.company,
                        "title": job.title,
                        "location": job.location,
                        "url": job.url,
                    }
                }
                bot.save_seen(stored)
                self.assertIn(job.fingerprint, bot.load_seen())
        finally:
            bot.STATE_FILE = original_state_file

    def test_senior_banking_titles_are_blocked(self) -> None:
        for title in ("AVP Product Analyst", "VP - Data Analyst", "Senior Data Scientist"):
            self.assertTrue(bot.reject_by_seniority(title, "", self.settings)[0])

    def test_workflow_is_serialized_and_every_thirty_minutes(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertIn("group: job-alert-bot-persistent-state", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("always()", workflow)


if __name__ == "__main__":
    unittest.main()
