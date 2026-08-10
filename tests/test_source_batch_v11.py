from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v11 as parsers


class SourceBatchV11Tests(unittest.TestCase):
    def test_workday_discovers_india_facet_and_reads_detail(self) -> None:
        company = {
            "name": "Example",
            "ats": "workday_india",
            "url": "https://example.wd1.myworkdayjobs.com/wday/cxs/example/External/jobs",
            "career_site_url": "https://example.wd1.myworkdayjobs.com/en-US/External",
            "search_terms": ["data"],
            "max_results_per_term": 20,
        }

        def fake_get_json(url, *, method="GET", payload=None):
            if method == "GET":
                return {
                    "jobPostingInfo": {
                        "jobDescription": "Python SQL analytics role",
                        "location": "Bengaluru, Karnataka, India",
                        "externalUrl": "https://example.com/apply/123",
                    }
                }
            if not payload.get("appliedFacets"):
                return {
                    "facets": [{
                        "facetParameter": "locationCountry",
                        "values": [{"descriptor": "India", "id": "india-id"}],
                    }]
                }
            self.assertEqual({"locationCountry": ["india-id"]}, payload["appliedFacets"])
            return {
                "total": 1,
                "jobPostings": [{
                    "title": "Data Analyst",
                    "locationsText": "Bengaluru, India",
                    "externalPath": "/job/Data-Analyst/123",
                }],
            }

        with patch.object(parsers.bot, "get_json", side_effect=fake_get_json), patch.object(
            parsers.bot, "is_target_title", return_value=True
        ):
            jobs = parsers.parse_workday_india(company)

        self.assertEqual(1, len(jobs))
        self.assertEqual("https://example.com/apply/123", jobs[0].url)
        self.assertIn("Python SQL", jobs[0].description)
        self.assertIn("Bengaluru", jobs[0].location)

    def test_talentbrew_reads_jobposting_json_ld(self) -> None:
        company = {
            "name": "Example",
            "url": "https://careers.example.com/search-jobs",
            "career_site_url": "https://careers.example.com/search-jobs",
            "search_terms": ["data"],
            "max_pages_per_term": 1,
        }
        search_html = """
        <ul><li>
          <a data-job-id="123" href="/job/bengaluru/data-analyst/123">
            <h2>Data Analyst</h2>
          </a>
          <span class="job-location">Bengaluru, India</span>
        </li></ul>
        """
        posting = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Data Analyst",
            "description": "Python SQL reporting and analytics",
            "url": "https://careers.example.com/job/bengaluru/data-analyst/123",
            "identifier": {
                "@type": "PropertyValue",
                "value": "JR2026517898",
            },
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "addressLocality": "Bengaluru",
                    "addressRegion": "Karnataka",
                    "addressCountry": "India",
                },
            },
        }
        detail_html = (
            '<script type="application/ld+json">'
            + json.dumps(posting)
            + "</script>"
        )
        responses = []
        for body in (search_html, detail_html):
            response = Mock()
            response.text = body
            response.raise_for_status = Mock()
            responses.append(response)

        with patch.object(parsers.requests, "get", side_effect=responses), patch.object(
            parsers.bot, "is_target_title", return_value=True
        ), patch.object(parsers.bot, "has_location_match", return_value=True):
            jobs = parsers.parse_talentbrew_html(company)

        self.assertEqual(1, len(jobs))
        self.assertIn("Python SQL", jobs[0].description)
        self.assertIn("Bengaluru", jobs[0].location)
        self.assertEqual("JR2026517898", jobs[0].requisition_id)

    def test_successfactors_search_reads_rows_and_description(self) -> None:
        company = {
            "name": "Example",
            "url": "https://jobs.example.com/search/",
            "career_site_url": "https://jobs.example.com/",
            "search_terms": ["data"],
            "max_pages_per_term": 1,
        }
        search_html = """
        <table><tr class="data-row">
          <td><span class="jobTitle hidden-phone">
            <a class="jobTitle-link" href="/job/123">Data Analyst</a>
          </span></td>
          <td class="colLocation"><span class="jobLocation">Bangalore, KA, IN</span></td>
          <td class="colFacility"><span class="jobFacility">Analytics</span></td>
        </tr></table>
        """
        detail_html = '<div class="jobdescription">Python SQL Power BI analytics</div>'
        responses = []
        for body in (search_html, detail_html):
            response = Mock()
            response.text = body
            response.raise_for_status = Mock()
            responses.append(response)

        with patch.object(parsers.requests, "get", side_effect=responses), patch.object(
            parsers.bot, "is_target_title", return_value=True
        ), patch.object(parsers.bot, "has_location_match", return_value=True):
            jobs = parsers.parse_successfactors_search(company)

        self.assertEqual(1, len(jobs))
        self.assertEqual("https://jobs.example.com/job/123", jobs[0].url)
        self.assertIn("Python SQL", jobs[0].description)

    def test_sensehq_reads_open_jobs_and_experience(self) -> None:
        company = {
            "name": "Affine",
            "url": "https://affine.sensehq.com/careers",
            "career_site_url": "https://affine.sensehq.com/careers",
        }
        payload = {
            "props": {
                "pageProps": {
                    "jobsData": {
                        "rows": [{
                            "id": 123,
                            "job_status": "open",
                            "title": "Data Analyst",
                            "location": "Bengaluru, India",
                            "workplace_type": "Hybrid",
                            "experience_start": 1,
                            "experience_end": 3,
                            "description_external": "Python SQL analytics",
                            "department": "Data Science",
                        }]
                    }
                }
            }
        }
        response = Mock()
        response.text = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script>"
        )
        response.raise_for_status = Mock()
        with patch.object(parsers.requests, "get", return_value=response):
            jobs = parsers.parse_sensehq_next_data(company)

        self.assertEqual(1, len(jobs))
        self.assertIn("1 to 3 years", jobs[0].description)
        self.assertTrue(jobs[0].url.endswith("?jobId=123"))

    def test_trakstar_drops_abandoned_old_jobs(self) -> None:
        company = {
            "name": "Dream11",
            "url": "https://dream11.hire.trakstar.com/jobfeeds/dream11",
            "max_age_days": 180,
        }
        rss = b"""<?xml version="1.0"?>
        <rss><channel><item>
          <title>Data Analyst</title>
          <link>https://example.com/job/1</link>
          <pubDate>Mon, 01 Jun 2015 00:00:00 +0000</pubDate>
          <description>Old opening</description>
        </item></channel></rss>"""
        response = Mock()
        response.content = rss
        response.raise_for_status = Mock()
        with patch.object(parsers.requests, "get", return_value=response):
            jobs = parsers.parse_trakstar_rss(company)
        self.assertEqual([], jobs)


if __name__ == "__main__":
    unittest.main()