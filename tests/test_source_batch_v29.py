from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v28 as parsers


class SourceBatchV29Tests(unittest.TestCase):
    @patch("custom_source_parsers_v28.requests.get")
    def test_mediatek_maps_stable_job_id(self, get: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"result": {"data": {"json": {"jobs": [{
            "id": "MTB123",
            "title": "Data Engineer",
            "description": "Build data products",
            "properties": {
                "location": {"code": "Bangalore\t"},
                "category": {"label": "Information Technology"},
            },
        }]}}}}]
        get.return_value = response
        jobs = parsers.parse_mediatek({"name": "MediaTek"})
        self.assertEqual("MTB123", jobs[0].requisition_id)
        self.assertEqual("Bangalore", jobs[0].location)
        self.assertTrue(jobs[0].url.endswith("/MTB123"))

    @patch("custom_source_parsers_v28._nagarro_feed_url", return_value="https://example.test/table?sas=x")
    @patch("custom_source_parsers_v28.requests.get")
    def test_nagarro_marks_wfa_as_remote_india(self, get: Mock, _feed: Mock) -> None:
        response = Mock(headers={})
        response.raise_for_status.return_value = None
        response.json.return_value = {"value": [{
            "Job_Title": "Data Engineer",
            "Job_City": "WFA/Remote",
            "Job_Url": "https://jobs.smartrecruiters.com/Nagarro1/744000123456789",
            "Expertise": "Data Engineering",
            "Level_name": "Senior",
            "index": 42,
        }]}
        get.return_value = response
        jobs = parsers.parse_nagarro({"name": "Nagarro", "url": "https://example.test/careers"})
        self.assertEqual("Remote India", jobs[0].location)
        self.assertEqual("744000123456789", jobs[0].requisition_id)


if __name__ == "__main__":
    unittest.main()
