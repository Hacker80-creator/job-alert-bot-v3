from __future__ import annotations

import html
import json
import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v26 as parsers


class SourceBatchV27Tests(unittest.TestCase):
    @patch("custom_source_parsers_v26.requests.post")
    def test_mynexthire_maps_public_requisition(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"reqDetailsBOList": [{
            "reqId": 218, "reqTitle": "Data Analyst", "location": "Bangalore",
            "locationList": [{"office": "Bangalore"}], "jdDisplay": "Analyze data",
            "buName": "Analytics",
        }]}
        response.raise_for_status.return_value = None
        post.return_value = response
        jobs = parsers.parse_mynexthire({
            "name": "Yulu", "url": "https://example/api",
            "career_site_url": "https://example/employer/jobs/careers",
        })
        self.assertEqual("218", jobs[0].requisition_id)
        self.assertIn("Bangalore", jobs[0].location)
        self.assertIn("p=", jobs[0].url)

    @patch("custom_source_parsers_v26.requests.get")
    def test_zoho_recruit_decodes_embedded_job_list(self, get: Mock) -> None:
        value = html.escape(json.dumps([{
            "id": "89246", "Posting_Title": "Data Analyst", "City": "Bengaluru",
            "Country": "India", "Publish": True, "Job_Opening_Name": "Data Analyst",
        }]), quote=True)
        response = Mock(text=f'<input type="hidden" value="{value}">')
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_zoho_recruit_public({
            "name": "Ultraviolette Automotive", "url": "https://example/jobs/Careers",
            "career_site_url": "https://example/jobs/Careers",
        })
        self.assertEqual("89246", jobs[0].requisition_id)
        self.assertIn("Bengaluru", jobs[0].location)


if __name__ == "__main__":
    unittest.main()
