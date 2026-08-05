from __future__ import annotations

import unittest

import job_monitor_entry_v11


class ProductionV11Tests(unittest.TestCase):
    def test_tavant_uses_transport_compatible_parser(self) -> None:
        companies = {
            item["name"]: item for item in job_monitor_entry_v11.load_final_config()["companies"]
        }
        tavant = companies["Tavant Technologies"]
        self.assertEqual("tavant_zwayam", tavant["ats"])
        self.assertEqual(10, tavant["max_results"])


if __name__ == "__main__":
    unittest.main()
