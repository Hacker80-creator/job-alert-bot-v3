from __future__ import annotations

import unittest

import promote_discovered_sources as promotion


class PromotionTests(unittest.TestCase):
    def test_rejects_unrelated_greenhouse_board(self) -> None:
        source = {
            "name": "McAfee", "ats": "greenhouse", "enabled": True,
            "verified_job_count": 5, "verified_name": "McAfee Heating and Air Conditioning",
        }
        self.assertIn("does not match", promotion.rejection_reason(source) or "")

    def test_accepts_greenhouse_generic_board_suffix(self) -> None:
        source = {
            "name": "Backblaze", "ats": "greenhouse", "enabled": True,
            "verified_job_count": 2, "verified_name": "Backblaze External Website",
        }
        self.assertIsNone(promotion.rejection_reason(source))

    def test_rejects_unproven_recruitee_identity(self) -> None:
        source = {
            "name": "Meta", "ats": "recruitee", "enabled": True,
            "verified_job_count": 1, "verified_name": "meta",
        }
        self.assertIn("does not prove", promotion.rejection_reason(source) or "")

    def test_rejects_known_lever_test_board(self) -> None:
        source = {
            "name": "LinkedIn", "ats": "lever", "enabled": True,
            "verified_job_count": 23,
        }
        self.assertIn("known test", promotion.rejection_reason(source) or "")


if __name__ == "__main__":
    unittest.main()
