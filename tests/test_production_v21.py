from __future__ import annotations

import unittest
from pathlib import Path

import job_monitor_entry_v21


class ProductionV21Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = job_monitor_entry_v21.load_final_config()
        self.companies = {
            item["name"]: item for item in self.config["companies"]
        }

    def test_registry_is_unique_and_counts_are_expected(self) -> None:
        self.assertEqual(410, len(self.companies))
        self.assertEqual(
            402,
            sum(1 for item in self.companies.values() if item.get("enabled", True)),
        )

    def test_parent_portals_replace_subsidiary_scanners(self) -> None:
        expected = {
            "Cisco": ("phenom", ["Cisco Meraki", "Duo Security", "Splunk"]),
            "Raytheon Technologies": ("phenom", ["Collins Aerospace", "Pratt & Whitney"]),
            "Palo Alto Networks": ("workday_search", ["CyberArk"]),
            "Hewlett Packard Enterprise": ("phenom", ["Juniper Networks"]),
            "UnitedHealth Group": ("talentbrew_html", ["Optum"]),
        }
        for canonical, (ats, aliases) in expected.items():
            with self.subTest(company=canonical):
                self.assertEqual(ats, self.companies[canonical]["ats"])
                self.assertEqual(aliases, self.companies[canonical]["aliases"])
                for alias in aliases:
                    self.assertNotIn(alias, self.companies)

    def test_synopsys_and_ansys_share_one_scanner(self) -> None:
        self.assertNotIn("Ansys", self.companies)
        self.assertEqual(["Ansys"], self.companies["Synopsys"]["aliases"])

    def test_workflow_runs_v21_every_half_hour_with_write_permission(self) -> None:
        workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "job-alerts.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertIn("contents: write", workflow)
        self.assertRegex(workflow, r"python job_monitor_entry_v\d+\.py")
        self.assertIn('MAX_SOURCE_WORKERS: "16"', workflow)


if __name__ == "__main__":
    unittest.main()
