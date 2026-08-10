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

    def test_blr_india_location_alias_is_accepted(self) -> None:
        self.assertTrue(bot.has_location_match(
            "MARKETPLACE ACCELERATION BLR INDIA", self.settings
        ))
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

    def test_internal_ats_api_links_are_never_alerted(self) -> None:
        internal_urls = (
            "https://api.smartrecruiters.com/v1/companies/example/postings/12345",
            "https://tenant.wd1.myworkdayjobs.com/wday/cxs/tenant/site/job/12345",
            "https://example.com/hcmRestApi/resources/latest/jobs/12345",
            "https://boards-api.greenhouse.io/v1/boards/example/jobs/12345",
        )
        for url in internal_urls:
            self.assertFalse(bot.is_public_job_url(url), url)
        self.assertTrue(bot.is_public_job_url("https://example.com/jobs/12345"))

        internal = bot.Job(
            "Example", "Data Analyst", "Bengaluru", internal_urls[0], "test"
        )
        self.assertEqual(bot.filter_and_score([internal], self.settings), [])
    def test_same_job_url_dedupes_when_location_is_enriched(self) -> None:
        first = bot.Job(
            "Example",
            "Data Analyst",
            "Bengaluru",
            "https://example.com/en-US/jobs/12345?utm_source=feed",
            "one",
        )
        second = bot.Job(
            "Example",
            "Data Analyst",
            "Bengaluru; Karnataka; India",
            "https://example.com/jobs/12345",
            "two",
        )
        self.assertNotEqual(first.fingerprint, second.fingerprint)
        self.assertFalse(first.dedupe_keys.isdisjoint(second.dedupe_keys))
        self.assertEqual(len(bot.filter_and_score([first, second], self.settings)), 1)

    def test_apply_url_variant_dedupes_but_distinct_ids_do_not(self) -> None:
        direct = bot.Job(
            "Example", "Data Analyst", "Remote, India",
            "https://example.com/apply/jobs/12345?source=careers", "one",
        )
        same = bot.Job(
            "Example", "Data Analyst", "Remote, India",
            "https://example.com/jobs/12345", "two",
        )
        other = bot.Job(
            "Example", "Data Analyst", "Remote, India",
            "https://example.com/jobs/67890", "three",
        )
        self.assertFalse(direct.dedupe_keys.isdisjoint(same.dedupe_keys))
        self.assertEqual(direct.state_key, same.state_key)
        self.assertNotEqual(direct.state_key, other.state_key)
        self.assertNotEqual(
            bot.make_url_fingerprint(direct.url),
            bot.make_url_fingerprint(other.url),
        )
        self.assertEqual(len(bot.filter_and_score([direct, same, other], self.settings)), 2)

    def test_persisted_state_recognizes_url_variant(self) -> None:
        seen = {
            "legacy-key": {
                "company": "Example",
                "title": "Data Analyst",
                "location": "Bengaluru",
                "url": "https://example.com/en-US/jobs/12345?utm_campaign=old",
            }
        }
        changed = bot.Job(
            "Example",
            "Data Analyst",
            "Bengaluru; Karnataka; India",
            "https://example.com/jobs/12345",
            "test",
        )
        self.assertFalse(changed.dedupe_keys.isdisjoint(bot.state_dedupe_keys(seen)))

    def test_stringified_workday_location_is_cleaned(self) -> None:
        location = bot.flatten_location(
            "{'descriptor': 'India', 'addressLocality': 'Bengaluru', "
            "'addressRegion': 'Karnataka', 'alpha2Code': 'IN'}"
        )
        self.assertEqual(location, "India Bengaluru Karnataka IN")
        enriched = bot.flatten_location(
            "IND - Bangalore, India "
            "{'descriptor': 'India', 'alpha2Code': 'IN'}"
        )
        self.assertEqual(enriched, "IND - Bangalore, India")
        self.assertEqual(
            bot.flatten_location(["IND - Bangalore, India", enriched]),
            "IND - Bangalore, India",
        )

    def test_senior_banking_titles_are_blocked(self) -> None:
        for title in ("AVP Product Analyst", "VP - Data Analyst", "Senior Data Scientist"):
            self.assertTrue(bot.reject_by_seniority(title, "", self.settings)[0])

    def test_repeated_workday_location_and_country_metadata_are_cleaned(self) -> None:
        raw = (
            "IND-Bangalore-TowerE,RMZ Infin; IND-Bangalore-TowerE,RMZ Infin "
            "{'descriptor': 'India', 'alpha2Code': 'IN'}"
        )
        self.assertEqual(
            "IND-Bangalore-TowerE,RMZ Infin", bot.flatten_location(raw)
        )

    def test_nested_workday_location_metadata_is_cleaned(self) -> None:
        raw = [
            "IND-Bangalore-TowerE,RMZ Infin",
            {
                "name": "IND-Bangalore-TowerE,RMZ Infin",
                "descriptor": "India",
                "alpha2Code": "IN",
            },
        ]
        self.assertEqual(
            "IND-Bangalore-TowerE,RMZ Infin", bot.flatten_location(raw)
        )

    def test_workflow_is_serialized_and_every_thirty_minutes(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertIn("group: job-alert-bot-persistent-state", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("always()", workflow)


if __name__ == "__main__":
    unittest.main()
