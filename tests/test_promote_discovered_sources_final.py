from __future__ import annotations

import unittest

import promote_discovered_sources as promotion
import promote_discovered_sources_final  # noqa: F401 - applies final policy


class FinalPromotionTests(unittest.TestCase):
    def test_honeycomb_io_board_is_accepted(self) -> None:
        source = {
            "name": "Honeycomb", "ats": "greenhouse", "enabled": True,
            "verified_job_count": 16, "verified_name": "Honeycomb.io",
        }
        self.assertIsNone(promotion.rejection_reason(source))

    def test_unrelated_porter_board_is_rejected(self) -> None:
        source = {"name": "Porter", "ats": "lever", "enabled": True, "verified_job_count": 26}
        self.assertIn("known test", promotion.rejection_reason(source) or "")

    def test_unrelated_bounce_board_is_rejected(self) -> None:
        source = {"name": "Bounce", "ats": "ashby", "enabled": True, "verified_job_count": 16}
        self.assertIn("known test", promotion.rejection_reason(source) or "")


if __name__ == "__main__":
    unittest.main()
