from __future__ import annotations

import unittest

import custom_source_parsers_v13 as parsers
import job_monitor as bot


class SourceBatchV13Tests(unittest.TestCase):
    def test_excluded_parent_brand_prevents_portal_overlap(self) -> None:
        jobs = [
            bot.Job(
                "Synopsys", "Data Analyst", "Bengaluru",
                "https://careers.synopsys.com/job/one", "test",
            ),
            bot.Job(
                "Synopsys", "Data Analyst - Ansys", "Bengaluru",
                "https://careers.synopsys.com/ansys/job/two", "test",
            ),
        ]
        scoped = parsers.filter_company_scope(
            jobs, {"excluded_keyword": "Ansys"}
        )
        self.assertEqual(["https://careers.synopsys.com/job/one"], [j.url for j in scoped])

    def test_required_parent_brand_keeps_only_matching_records(self) -> None:
        jobs = [
            bot.Job("Ansys", "Data Engineer", "India", "https://x/ansys/1", "test"),
            bot.Job("Ansys", "Data Engineer", "India", "https://x/synopsys/2", "test"),
        ]
        scoped = parsers.filter_company_scope(
            jobs, {"required_keyword": "Ansys"}
        )
        self.assertEqual(["https://x/ansys/1"], [j.url for j in scoped])


if __name__ == "__main__":
    unittest.main()
