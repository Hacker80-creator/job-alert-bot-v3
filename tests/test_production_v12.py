from __future__ import annotations

import unittest

import job_monitor_entry_v12


class ProductionV12Tests(unittest.TestCase):
    def test_tavant_uses_browser_compatible_transport(self) -> None:
        companies = {
            item["name"]: item for item in job_monitor_entry_v12.load_final_config()["companies"]
        }
        self.assertEqual(
            "tavant_browser_transport", companies["Tavant Technologies"]["ats"]
        )


if __name__ == "__main__":
    unittest.main()
