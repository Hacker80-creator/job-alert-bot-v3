from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v23 as parsers


class SourceBatchV24Tests(unittest.TestCase):
    @patch("custom_source_parsers_v23.requests.get")
    @patch("custom_source_parsers_v23.requests.post")
    def test_goldman_higher_maps_feed_and_detail(self, post: Mock, get: Mock) -> None:
        listing = Mock()
        listing.json.return_value = {"data": {"roleSearch": {
            "totalCount": 1,
            "items": [{
                "roleId": "role-1", "jobTitle": "Data Analyst",
                "jobFunction": "Engineering", "division": "Global Banking",
                "locations": [{"city": "Bengaluru", "state": "Karnataka", "country": "India"}],
                "skills": ["SQL"], "externalSource": {"sourceId": "154399"},
            }],
        }}}
        listing.raise_for_status.return_value = None
        post.return_value = listing

        detail = Mock()
        detail.text = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({
            "props": {"pageProps": {"role": {
                "jobTitle": "Data Analyst", "division": "Global Banking",
                "jobFunction": "Engineering", "descriptionHtml": "<p>Analyze data with Python</p>",
                "externalSource": {"sourceId": "154399"},
            }}},
        }) + "</script>"
        detail.raise_for_status.return_value = None
        get.return_value = detail

        jobs = parsers.parse_goldman_higher({
            "name": "Goldman Sachs",
            "url": "https://api-higher.gs.com/gateway/api/v1/graphql",
            "career_site_url": "https://higher.gs.com/roles",
            "max_candidate_details": 5,
        })

        self.assertEqual(1, len(jobs))
        self.assertEqual("154399", jobs[0].requisition_id)
        self.assertEqual("https://higher.gs.com/roles/154399", jobs[0].url)
        self.assertIn("Bengaluru", jobs[0].location)
        self.assertIn("Python", jobs[0].description)
        self.assertEqual("Global Banking; Engineering", jobs[0].department)


if __name__ == "__main__":
    unittest.main()
