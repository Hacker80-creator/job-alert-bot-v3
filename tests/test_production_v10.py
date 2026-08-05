from __future__ import annotations

import unittest

import job_monitor_entry_v10


class ProductionV10Tests(unittest.TestCase):
    def test_tavant_scan_is_bounded_to_newest_page(self) -> None:
        companies = {
            item["name"]: item for item in job_monitor_entry_v10.load_final_config()["companies"]
        }
        tavant = companies["Tavant Technologies"]
        self.assertEqual("zwayam_hardened", tavant["ats"])
        self.assertEqual(10, tavant["max_results"])
        self.assertEqual(20, tavant["read_timeout_seconds"])


if __name__ == "__main__":
    unittest.main()
