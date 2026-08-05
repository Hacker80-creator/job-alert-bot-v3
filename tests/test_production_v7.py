from __future__ import annotations

import unittest

import job_monitor_entry_v7


class ProductionV7Tests(unittest.TestCase):
    def test_microsoft_uses_current_official_feed(self) -> None:
        companies = {
            item["name"]: item for item in job_monitor_entry_v7.load_final_config()["companies"]
        }
        microsoft = companies["Microsoft"]
        self.assertEqual("eightfold", microsoft["ats"])
        self.assertEqual(
            "https://apply.careers.microsoft.com/api/pcsx/search", microsoft["url"]
        )
        self.assertEqual("microsoft.com", microsoft["domain"])


if __name__ == "__main__":
    unittest.main()
