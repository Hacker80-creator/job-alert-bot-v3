from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v29 as parsers


class SourceBatchV30Tests(unittest.TestCase):
    @patch("custom_source_parsers_v29.requests.get")
    def test_robosoft_maps_card_and_detail(self, get: Mock) -> None:
        listing = Mock(text='''
        <div><h3>Data Engineer</h3><div><span>India</span><span>Bengaluru</span>
        <span>Hybrid</span></div><a href="/careers/data-engineer"></a></div>
        ''')
        listing.raise_for_status.return_value = None
        detail = Mock(text="<main>Build analytics products</main>")
        detail.raise_for_status.return_value = None
        get.side_effect = [listing, detail]
        jobs = parsers.parse_robosoft({
            "name": "Robosoft Technologies",
            "url": "https://www.robosoftin.com/careers",
        })
        self.assertEqual("Data Engineer", jobs[0].title)
        self.assertEqual("India, Bengaluru, Hybrid", jobs[0].location)
        self.assertEqual("data-engineer", jobs[0].requisition_id)
        self.assertEqual("Build analytics products", jobs[0].description)


if __name__ == "__main__":
    unittest.main()
