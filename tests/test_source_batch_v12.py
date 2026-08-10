from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v12 as parsers


class SourceBatchV12Tests(unittest.TestCase):
    def test_kula_maps_server_rendered_job_card(self) -> None:
        html = """
        <div class="card">
          <div><p>DevOps Engineer</p>
          <p>Engineering • Bengaluru, Karnataka, India • Full Time • Hybrid</p></div>
          <a href="/example/12616/">Apply Now</a>
        </div>
        """
        response = Mock(text=html)
        response.raise_for_status = Mock()
        company = {
            "name": "Example",
            "url": "https://careers.kula.ai/example",
            "career_site_url": "https://careers.kula.ai/example",
        }
        with patch.object(parsers.requests, "get", return_value=response), patch.object(
            parsers.bot, "is_target_title", return_value=False
        ):
            jobs = parsers.parse_kula_html(company)
        self.assertEqual(1, len(jobs))
        self.assertEqual("DevOps Engineer", jobs[0].title)
        self.assertEqual("Bengaluru, Karnataka, India", jobs[0].location)
        self.assertEqual("Engineering", jobs[0].department)
        self.assertTrue(jobs[0].url.endswith("/example/12616/"))

    def test_paylocity_maps_location_description_and_salary(self) -> None:
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = {
            "jobs": [{
                "jobId": 7,
                "title": "Data Analyst",
                "applyUrl": "https://example.com/apply/7",
                "description": "<p>Python and SQL analytics</p>",
                "requirements": "One year experience",
                "salaryDescription": "INR 8-12 LPA",
                "hiringDepartment": "Product",
                "jobLocation": {
                    "locationDisplayName": "Hybrid - Bengaluru India",
                    "city": "Bengaluru",
                },
            }]
        }
        with patch.object(parsers.requests, "get", return_value=response):
            jobs = parsers.parse_paylocity_feed({
                "name": "Example",
                "url": "https://example.com/feed",
            })
        self.assertEqual(1, len(jobs))
        self.assertIn("Python and SQL", jobs[0].description)
        self.assertIn("Bengaluru", jobs[0].location)
        self.assertEqual("INR 8-12 LPA", jobs[0].salary_text)

    def test_cohesity_enriches_local_target_job(self) -> None:
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = {
            "job_data": {
                "Engineering": [{
                    "JobID": "abc",
                    "req_id": "R1",
                    "title": "Data Analyst",
                    "primaryLocation": "Bangalore - India",
                    "AdditionalLocations": "",
                    "country": "India",
                    "jobUrl": (
                        "https://cohesity.wd5.myworkdayjobs.com/"
                        "Cohesity_Careers/job/Bangalore/Data-Analyst_R1/apply"
                    ),
                    "careerSiteDept": "Engineering",
                }]
            }
        }
        with patch.object(parsers.requests, "get", return_value=response), patch.object(
            parsers.bot, "is_target_title", return_value=True
        ), patch.object(
            parsers.bot, "has_location_match", return_value=True
        ), patch.object(
            parsers.bot,
            "get_json",
            return_value={
                "jobPostingInfo": {
                    "jobDescription": "Python SQL analytics role",
                    "externalUrl": "https://example.com/job/R1",
                }
            },
        ) as detail:
            jobs = parsers.parse_cohesity_feed({
                "name": "Cohesity",
                "url": "https://www.cohesity.com/bin/cohesity/open-positions",
            })
        self.assertEqual(1, len(jobs))
        self.assertIn("Python SQL", jobs[0].description)
        self.assertEqual("https://example.com/job/R1", jobs[0].url)
        self.assertIn("/wday/cxs/cohesity/Cohesity_Careers/job/", detail.call_args.args[0])


if __name__ == "__main__":
    unittest.main()