from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v25 as parsers


class SourceBatchV26Tests(unittest.TestCase):
    @patch("custom_source_parsers_v25.requests.post")
    def test_urban_company_maps_stable_job_code(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"jobs": [{
            "job_id": "uuid", "job_code": "UCL-42", "job_title": "Data Analyst",
            "location": ["Bengaluru, Karnataka, India"], "parent_department": "Data",
            "job_description": "<p>Analyze data</p>", "apply_url": "https://apply.example/uuid",
        }]}
        response.raise_for_status.return_value = None
        post.return_value = response
        jobs = parsers.parse_urban_company({"name": "Urban Company", "url": "https://example/jobs"})
        self.assertEqual("UCL-42", jobs[0].requisition_id)
        self.assertIn("Bengaluru", jobs[0].location)
        self.assertEqual("Analyze data", jobs[0].description)

    @patch("custom_source_parsers_v25.requests.get")
    def test_sharechat_maps_grouped_jobs(self, get: Mock) -> None:
        response = Mock()
        response.json.return_value = {"data": {"careersList": [{
            "title": "Engineering", "data": [{
                "requisitionId": 2422, "requisitionTitle": "Machine Learning Engineer",
                "officeLocationNames": ["Bangalore"], "orgUnitName": "Engineering",
            }],
        }], "hasNext": False}}
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_sharechat_careers({"name": "ShareChat", "url": "https://example/api"})
        self.assertEqual("2422", jobs[0].requisition_id)
        self.assertIn("sharechat.mynexthire.com", jobs[0].url)

    @patch("custom_source_parsers_v25.requests.get")
    def test_river_maps_department_groups(self, get: Mock) -> None:
        response = Mock()
        response.json.return_value = {"data": {"Analytics": [{
            "requisitionId": 608, "requisitionTitle": "Data Analyst",
            "officeLocationNames": ["River HQ, Bengaluru"], "orgUnitName": "Analytics",
        }]}}
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_river_careers({"name": "River Mobility", "url": "https://example/api"})
        self.assertEqual("608", jobs[0].requisition_id)
        self.assertIn("current-openings/608", jobs[0].url)


if __name__ == "__main__":
    unittest.main()
