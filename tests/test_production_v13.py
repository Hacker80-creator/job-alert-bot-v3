from __future__ import annotations

import unittest

import job_monitor_entry_v13


class ProductionV13Tests(unittest.TestCase):
    def test_expedia_search_is_rate_bounded(self) -> None:
        companies = {
            item["name"]: item for item in job_monitor_entry_v13.load_final_config()["companies"]
        }
        expedia = companies["Expedia Group"]
        self.assertEqual(["machine learning", "data"], expedia["search_terms"])
        self.assertEqual(1, expedia["max_pages_per_term"])
        self.assertEqual(5, expedia["max_details"])


if __name__ == "__main__":
    unittest.main()
