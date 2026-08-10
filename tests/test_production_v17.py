from __future__ import annotations

import unittest

import job_monitor_entry_v17


class ProductionV17Tests(unittest.TestCase):
    def test_four_stale_sources_use_current_first_party_feeds(self) -> None:
        companies = {
            item["name"]: item for item in job_monitor_entry_v17.load_final_config()["companies"]
        }
        self.assertEqual("oracle_hcm", companies["Uber"]["ats"])
        self.assertEqual("UberCareers", companies["Uber"]["site_number"])
        self.assertEqual("nutanix_sitemap", companies["Nutanix"]["ats"])
        self.assertEqual("coindcx_next_data", companies["CoinDCX"]["ats"])
        self.assertEqual("siemens_avature", companies["Siemens Healthineers"]["ats"])

    def test_override_preserves_unique_source_registry(self) -> None:
        companies = job_monitor_entry_v17.load_final_config()["companies"]
        names = [str(item["name"]).casefold() for item in companies]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(261, len(companies))
        self.assertEqual(260, sum(1 for item in companies if item.get("enabled", True)))


if __name__ == "__main__":
    unittest.main()
