from __future__ import annotations

import unittest

import custom_source_parsers_v7 as parsers
import job_monitor_entry_v15


class ProductionV15Tests(unittest.TestCase):
    def test_iqvia_multi_location_uses_verified_facet_label(self) -> None:
        companies = {
            item["name"]: item for item in job_monitor_entry_v15.load_final_config()["companies"]
        }
        iqvia = companies["IQVIA"]
        self.assertEqual("Bangalore, India", iqvia["facet_location_label"])
        self.assertEqual(3, len(iqvia["applied_facets"]["locations"]))

    def test_multi_location_label_is_detected(self) -> None:
        self.assertTrue(parsers._is_multi_location_label("2 Locations"))
        self.assertFalse(parsers._is_multi_location_label("Bangalore, India"))


if __name__ == "__main__":
    unittest.main()
