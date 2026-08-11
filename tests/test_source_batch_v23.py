from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v22 as parsers


class SourceBatchV23Tests(unittest.TestCase):
    def test_deel_postings_decodes_next_payload(self) -> None:
        payload = '22:{"jobPostings":[{"id":"post-1","title":"Data Analyst"}],"tail":true}'
        page = '<script>self.__next_f.push(' + json.dumps([1, payload]) + ')</script>'
        jobs = parsers._deel_postings(page)
        self.assertEqual("post-1", jobs[0]["id"])

    @patch("custom_source_parsers_v22.requests.post")
    def test_gem_public_maps_description_and_remote_india(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"data": {"oatsExternalJobPostings": {"jobPostings": [{
            "id": "internal", "extId": "external", "title": "Forward Deployed Analyst",
            "descriptionHtml": "<p>Analyze enterprise data</p>",
            "locations": [{"name": "Remote - India", "isoCountry": "IND", "isRemote": True}],
            "job": {"requisitionId": "R36", "department": {"name": "FDE"}},
        }]}}}
        response.raise_for_status.return_value = None
        post.return_value = response

        jobs = parsers.parse_gem_public({
            "name": "Hasura", "slug": "promptql",
            "career_site_url": "https://jobs.gem.com/promptql", "wlb_score": 4,
        })

        self.assertEqual(1, len(jobs))
        self.assertIn("Remote - India", jobs[0].location)
        self.assertIn("enterprise data", jobs[0].description)
        self.assertEqual("R36", jobs[0].requisition_id)


if __name__ == "__main__":
    unittest.main()
