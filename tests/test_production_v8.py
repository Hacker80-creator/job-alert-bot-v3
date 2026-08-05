from __future__ import annotations

import unittest

import job_monitor_entry_v8


class ProductionV8Tests(unittest.TestCase):
    def test_microsoft_uses_throttle_aware_parser(self) -> None:
        companies = {
            item["name"]: item for item in job_monitor_entry_v8.load_final_config()["companies"]
        }
        microsoft = companies["Microsoft"]
        self.assertEqual("microsoft_eightfold", microsoft["ats"])
        self.assertEqual(3, microsoft["max_generic_details"])
        self.assertEqual(0.6, microsoft["request_delay_seconds"])


if __name__ == "__main__":
    unittest.main()
