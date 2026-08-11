from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v21 as parsers


class SourceBatchV22Tests(unittest.TestCase):
    @patch("custom_source_parsers_v21.requests.get")
    def test_keka_embed_maps_public_job_record(self, get: Mock) -> None:
        response = Mock()
        response.json.return_value = [{
            "id": 42,
            "title": "AI/ML Lead",
            "description": "<p>Build production AI systems</p>",
            "departmentName": "Engineering",
            "jobNumber": "JOB-42",
            "experience": "4+",
            "jobLocations": [{
                "name": "Bengaluru", "state": "KA", "countryName": "India",
            }],
            "skillNames": ["Python", "Machine Learning"],
        }]
        response.raise_for_status.return_value = None
        get.return_value = response

        jobs = parsers.parse_keka_embed({
            "name": "Example",
            "career_site_url": "https://example.keka.com/careers/",
            "identifier": "board-id",
            "wlb_score": 4,
        })

        self.assertEqual(1, len(jobs))
        self.assertEqual("AI/ML Lead", jobs[0].title)
        self.assertIn("Bengaluru", jobs[0].location)
        self.assertIn("Python", jobs[0].description)
        self.assertEqual("JOB-42", jobs[0].requisition_id)
        self.assertEqual("https://example.keka.com/careers/jobdetails/42", jobs[0].url)


if __name__ == "__main__":
    unittest.main()
