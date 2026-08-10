from __future__ import annotations

import unittest
from pathlib import Path

import yaml

import promote_runtime_sources as promotion


class RuntimeSourcePromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = yaml.safe_load(
            (Path(__file__).parents[1] / "career_source_promotable.yaml").read_text(
                encoding="utf-8"
            )
        )
        cls.reviewed = promotion.build_reviewed(raw["companies"])
        cls.by_name = {item["name"]: item for item in cls.reviewed}

    def test_118_candidates_become_111_unique_scanners(self) -> None:
        self.assertEqual(111, len(self.reviewed))
        identities = [promotion.source_identity(item) for item in self.reviewed]
        self.assertEqual(len(identities), len(set(identities)))

    def test_parent_portals_are_scanned_once(self) -> None:
        expected = {
            "Cisco": ["Cisco Meraki", "Duo Security", "Splunk"],
            "Raytheon Technologies": ["Collins Aerospace", "Pratt & Whitney"],
            "Palo Alto Networks": ["CyberArk"],
            "Hewlett Packard Enterprise": ["Juniper Networks"],
            "UnitedHealth Group": ["Optum"],
        }
        for canonical, aliases in expected.items():
            self.assertEqual(aliases, self.by_name[canonical]["aliases"])
            for alias in aliases:
                self.assertNotIn(alias, self.by_name)

    def test_existing_parent_sources_are_upgraded_not_duplicated(self) -> None:
        self.assertEqual("phenom", self.by_name["Cisco"]["ats"])
        self.assertEqual("workday_india", self.by_name["LSEG"]["ats"])
        self.assertEqual("workday_search", self.by_name["Broadcom"]["ats"])
        self.assertEqual("workday_india", self.by_name["Shell"]["ats"])

    def test_synopsys_excludes_ansys_scope(self) -> None:
        self.assertEqual("Ansys", self.by_name["Synopsys"]["excluded_keyword"])


if __name__ == "__main__":
    unittest.main()
