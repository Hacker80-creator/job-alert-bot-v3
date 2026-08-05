from __future__ import annotations

import unittest

import job_monitor_entry_v6


class ProductionSourceTests(unittest.TestCase):
    def test_unique_verified_counts_and_new_accenture_company(self) -> None:
        companies = {item["name"]: item for item in job_monitor_entry_v6.load_production_config()["companies"]}
        self.assertEqual(249, companies["Accenture"]["verified_job_count"])
        self.assertEqual(393, companies["Rippling"]["verified_job_count"])
        self.assertEqual(4, companies["Accenture"]["wlb_score"])


if __name__ == "__main__":
    unittest.main()
