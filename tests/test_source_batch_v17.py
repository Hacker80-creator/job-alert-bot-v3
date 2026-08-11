from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v17 as parsers


class SourceBatchV17Tests(unittest.TestCase):
    @patch("custom_source_parsers_v17.requests.get")
    def test_param_ai_maps_nested_department_jobs(self, get: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": {"Technical": {"jobs": [{
            "id": "uuid-1", "title": "Data Engineer", "req_id": 123,
            "slug": "data-engineer-123", "locations": ["Bengaluru"],
            "description": "<p>Build Python data pipelines.</p>",
            "min_exp": 2, "max_exp": 4,
            "published_on_career_page": True,
        }]}}}
        get.return_value = response
        jobs = parsers.parse_param_ai({
            "name": "Example",
            "url": "https://example.app.param.ai/api/career/get_job/",
            "career_site_url": "https://example.app.param.ai/jobs/",
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Bengaluru", jobs[0].location)
        self.assertEqual("123", jobs[0].requisition_id)
        self.assertIn("Python data pipelines", jobs[0].description)
        self.assertEqual(
            "https://example.app.param.ai/jobs/data-engineer-123", jobs[0].url,
        )

    @patch("custom_source_parsers_v17.requests.Session")
    def test_dayforce_geo_uses_csrf_and_maps_virtual_india(
        self, session_class: Mock,
    ) -> None:
        session = session_class.return_value
        landing = Mock(url="https://jobs.dayforcehcm.com/en-US/acme/candidateportal")
        landing.raise_for_status.return_value = None
        csrf = Mock()
        csrf.raise_for_status.return_value = None
        csrf.json.return_value = {"csrfToken": "token-1"}
        session.get.side_effect = [landing, csrf]
        search = Mock()
        search.raise_for_status.return_value = None
        search.json.return_value = {
            "maxCount": 1,
            "jobPostings": [{
                "jobPostingId": 299, "jobReqId": 60,
                "jobTitle": "Data Engineer", "hasVirtualLocation": True,
                "postingLocations": [{"formattedAddress": "India"}],
                "jobDescription": "<p>Python and SQL</p>",
            }],
        }
        session.post.return_value = search
        jobs = parsers.parse_dayforce_geo({
            "name": "Example", "client_namespace": "acme",
            "job_board": "candidateportal", "culture_code": "en-US",
            "career_site_url": landing.url, "page_size": 25,
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Virtual • India", jobs[0].location)
        self.assertEqual("60", jobs[0].requisition_id)
        self.assertEqual(
            "token-1", session.post.call_args.kwargs["headers"]["X-CSRF-Token"],
        )

    @patch("custom_source_parsers_v17.requests.Session")
    def test_turbohire_uses_anonymous_token_and_maps_job(self, session_class: Mock) -> None:
        session = session_class.return_value
        token = Mock()
        token.raise_for_status.return_value = None
        token.json.return_value = {"access_token": "public-token"}
        session.get.return_value = token
        search = Mock()
        search.raise_for_status.return_value = None
        search.json.return_value = {"Total": 1, "Result": [{
            "JobId": "uuid-1", "JobIdObfuscated": "public-id",
            "JobCode": "REQ-1", "JobTitle": "AI Engineer",
            "Department": "Technology",
            "Location": '[{"Address":"Bengaluru, India"}]',
            "Experience": {"MinExp": 2, "MaxExp": 4},
            "Skills": ["Python", "ML"],
            "JobDescV2": "<p>Build production AI systems.</p>",
        }]}
        session.post.return_value = search
        jobs = parsers.parse_turbohire_api({
            "name": "Example", "org_id": "org-1",
            "career_site_url": "https://example.turbohire.co/dashboardv2",
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Bengaluru, India", jobs[0].location)
        self.assertEqual("REQ-1", jobs[0].requisition_id)
        self.assertIn("Bearer public-token", session.post.call_args.kwargs["headers"]["Authorization"])
        self.assertEqual(
            "https://example.turbohire.co/job/publicjobs/public-id", jobs[0].url,
        )


if __name__ == "__main__":
    unittest.main()
