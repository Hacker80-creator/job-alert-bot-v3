from __future__ import annotations

import unittest

import custom_source_parsers_v8 as parsers
import job_monitor_entry_v16


class ProductionV16Tests(unittest.TestCase):
    def test_expedia_uses_single_request_official_sitemap(self) -> None:
        companies = {
            item["name"]: item for item in job_monitor_entry_v16.load_final_config()["companies"]
        }
        expedia = companies["Expedia Group"]
        self.assertEqual("expedia_sitemap", expedia["ats"])
        self.assertEqual(
            "https://careers.expediagroup.com/jobs-sitemap.xml",
            expedia["url"],
        )

    def test_expedia_slug_preserves_job_level_and_acronyms(self) -> None:
        self.assertEqual(
            "Machine Learning Scientist III",
            parsers._title_from_expedia_slug("machine-learning-scientist-iii"),
        )
        self.assertEqual("Oracle EPM Engineer", parsers._title_from_expedia_slug("oracle-epm-engineer"))


if __name__ == "__main__":
    unittest.main()
