from __future__ import annotations

import unittest

import custom_source_parsers_v6 as parsers
import job_monitor_entry_v14


class ProductionV14Tests(unittest.TestCase):
    def test_iqvia_uses_faceted_official_workday(self) -> None:
        companies = {
            item["name"]: item for item in job_monitor_entry_v14.load_final_config()["companies"]
        }
        iqvia = companies["IQVIA"]
        self.assertEqual("workday_faceted", iqvia["ats"])
        self.assertEqual(3, len(iqvia["applied_facets"]["locations"]))
        self.assertIn("myworkdayjobs.com", iqvia["url"])

    def test_multi_location_label_falls_back_to_path(self) -> None:
        self.assertEqual(
            "Bangalore India",
            parsers._location_from_workday_path(
                "/job/Bangalore-India/Associate-Data-Analyst_R123"
            ),
        )


if __name__ == "__main__":
    unittest.main()
