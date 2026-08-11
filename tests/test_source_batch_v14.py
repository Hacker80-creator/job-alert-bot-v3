from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import custom_source_parsers_v14 as parsers


class FakeResponse:
    def __init__(self, text: str, url: str, payload=None) -> None:
        self.text = text
        self.url = url
        self._payload = payload

    def json(self):
        if self._payload is not None:
            return self._payload
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        return None


class FakeGoogleSession:
    def get(self, url, **kwargs):
        if kwargs.get("params") is not None:
            return FakeResponse(
                '<base href="/about/careers/applications/">'
                '<a href="jobs/results/123456-data-analyst?location=Bengaluru&q=data">'
                '<span>Learn more</span></a>',
                "https://www.google.com/about/careers/applications/jobs/results/",
            )
        return FakeResponse(
            "<main><h1>Data Analyst</h1><p>Use Python and SQL. "
            "This is an early career role in Bengaluru.</p></main>",
            url,
        )


class SourceBatchV14Tests(unittest.TestCase):
    @patch("custom_source_parsers_v14.requests.get")
    @patch("custom_source_parsers_v14.requests.Session")
    def test_google_reads_server_rendered_job_links_and_details(
        self, session_cls, get
    ) -> None:
        session_cls.return_value = FakeGoogleSession()
        detail_html = (
            "<main><h1>Data Analyst</h1><p>Use Python and SQL. "
            "This is an early career role in Bengaluru. "
            + "Build reliable analytics and machine-learning systems. " * 5
            + "</p></main>"
        )
        get.return_value = FakeResponse(
            detail_html,
            "https://www.google.com/about/careers/applications/jobs/results/"
            "123456-data-analyst",
        )
        jobs = parsers.parse_google_careers_html({
            "name": "Google",
            "url": "https://www.google.com/about/careers/applications/jobs/results/",
            "search_terms": ["data"],
            "max_pages_per_term": 1,
            "max_details": 5,
            "wlb_score": 4,
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Data Analyst", jobs[0].title)
        self.assertEqual("Bengaluru, Karnataka, India", jobs[0].location)
        self.assertIn("Python and SQL", jobs[0].description)
        self.assertIn("/jobs/results/123456-data-analyst", jobs[0].url)

    @patch("custom_source_parsers_v14.requests.get")
    def test_makemytrip_uses_live_list_and_direct_apply_url(self, get) -> None:
        get.side_effect = [
            FakeResponse("", "https://careers.makemytrip.com/api/jobs", {
                "allJobs": [{
                    "job_id": "abc123",
                    "job_title": "Data Analyst",
                    "location": ["Bangalore, Karnataka, India"],
                    "experience_from": "1",
                    "experience_to": "3",
                    "department": "Analytics",
                }],
            }),
            FakeResponse("", "https://careers.makemytrip.com/api/jobDetails", {
                "data": {
                    "applyUrl": "https://gommt.darwinbox.in/ms/candidatev2/job/abc123",
                    "job_decription": "Use Python and SQL for product analytics.",
                },
            }),
        ]
        jobs = parsers.parse_makemytrip_api({
            "name": "MakeMyTrip",
            "url": "https://careers.makemytrip.com/api/jobs",
            "career_site_url": "https://careers.makemytrip.com",
            "detail_url": "https://careers.makemytrip.com/api/jobDetails",
            "wlb_score": 3,
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Data Analyst", jobs[0].title)
        self.assertIn("darwinbox.in", jobs[0].url)
        self.assertIn("Python and SQL", jobs[0].description)

    @patch("custom_source_parsers_v14.requests.get")
    def test_zoho_reads_embedded_official_jobs_payload(self, get) -> None:
        payload = json.dumps([{
            "id": "193779000000000001",
            "Posting_Title": "Data Analyst",
            "Country1": "India",
            "Remote_Job": True,
            "Publish": True,
            "Job_Description": "Use Python and SQL.",
            "Job_Type": "Full time",
        }])
        get.return_value = FakeResponse(
            f"<html><input id='jobs' type='hidden' value='{payload}'></html>",
            "https://careers.zohocorp.com/jobs/Careers",
        )
        jobs = parsers.parse_zoho_careers_html({
            "name": "Zoho",
            "url": "https://careers.zohocorp.com/jobs/Careers",
            "career_site_url": "https://careers.zohocorp.com/jobs/Careers",
            "wlb_score": 4,
        })
        self.assertEqual(1, len(jobs))
        self.assertIn("Remote India", jobs[0].location)
        self.assertTrue(jobs[0].url.endswith("193779000000000001"))
    @patch("custom_source_parsers_v14.requests.get")
    def test_cgi_reads_njoyn_job_table_rows(self, get) -> None:
        get.return_value = FakeResponse(
            """
            <table><tr>
              <td><a href="/corp/xweb/xweb.asp?page=JobDetails&amp;Jobid=J123">
                J123</a></td>
              <td>Data Analyst</td>
              <td>Analytics and Emerging Digital Technologies</td>
              <td>Bangalore</td>
              <td name="CountryCell">India</td>
            </tr></table>
            """,
            "https://cgi.njoyn.com/corp/xweb/xweb.asp?page=joblisting",
        )
        jobs = parsers.parse_njoyn_html({
            "name": "CGI",
            "url": "https://cgi.njoyn.com/corp/xweb/xweb.asp?page=joblisting",
            "wlb_score": 3,
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Data Analyst", jobs[0].title)
        self.assertEqual("Bangalore, India", jobs[0].location)
        self.assertIn("JobDetails", jobs[0].url)
        self.assertEqual(
            "Analytics and Emerging Digital Technologies",
            jobs[0].department,
        )


    @patch("custom_source_parsers_v14.requests.get")
    def test_booking_reads_jibe_api_with_direct_apply_link(self, get) -> None:
        get.return_value = FakeResponse("", "https://jobs.booking.com/api/jobs", {
            "jobs": [{"data": {
                "req_id": "30001",
                "title": "Data Analyst",
                "full_location": "Bangalore, India",
                "description": "Use Python and SQL for analytics.",
                "apply_url": "https://careers-workingatbooking.icims.com/jobs/30001/login",
                "external": True,
                "category": ["Data & Analytics"],
            }}],
            "totalCount": 1,
        })
        jobs = parsers.parse_jibe_api({
            "name": "Booking.com",
            "url": "https://jobs.booking.com/api/jobs",
            "career_site_url": "https://jobs.booking.com/booking/jobs",
            "page_size": 100,
            "query_params": {"country": "India"},
            "wlb_score": 4,
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Bangalore, India", jobs[0].location)
        self.assertIn("/30001/", jobs[0].url)
        self.assertEqual("India", get.call_args.kwargs["params"]["country"])

    @patch("custom_source_parsers_v14.requests.post")
    def test_onestream_reads_ukg_public_search(self, post) -> None:
        post.return_value = FakeResponse("", "https://recruiting.ultipro.com/", {
            "opportunities": [{
                "Id": "00000000-1111-2222-3333-444444444444",
                "Title": "Data Analyst",
                "JobCategoryName": "AI & Operational Analytics",
                "Locations": [{
                    "LocalizedName": "Bangalore, India",
                    "Address": {"City": "Bangalore", "Country": {"Name": "India"}},
                }],
                "BriefDescription": "Use Python and SQL.",
            }],
            "totalCount": 1,
        })
        jobs = parsers.parse_ukg_jobboard({
            "name": "OneStream",
            "url": "https://recruiting.ultipro.com/example/LoadSearchResults",
            "career_site_url": "https://recruiting.ultipro.com/example",
            "page_size": 50,
            "wlb_score": 3,
        })
        self.assertEqual(1, len(jobs))
        self.assertIn("Bangalore", jobs[0].location)
        self.assertIn("opportunityId=", jobs[0].url)

    @patch("custom_source_parsers_v14.requests.post")
    def test_walmart_reads_search_and_verifies_active_detail(self, post) -> None:
        post.side_effect = [
            FakeResponse("", "https://careers.walmart.com/api/graphql", {
                "data": {"jobSearch": {"searchResults": [{
                    "jobId": "R-1234567",
                    "jobTitle": "Data Analyst",
                    "brand": "Walmart",
                    "location": [{"storeName": "BANGALORE BLR INDIA"}],
                }]}}
            }),
            FakeResponse("", "https://careers.walmart.com/api/graphql", {
                "data": {"bulkUnifiedJobDetails": [{
                    "jobId": "R-1234567",
                    "active": True,
                    "title": "Data Analyst",
                    "description": "Use Python and SQL for product analytics.",
                }]}
            }),
        ]
        jobs = parsers.parse_walmart_graphql({
            "name": "Walmart Global Tech",
            "url": "https://careers.walmart.com/api/graphql",
            "career_site_url": "https://careers.walmart.com",
            "search_query_id": "search-id",
            "detail_query_id": "detail-id",
            "search_terms": ["data"],
            "max_results_per_term": 20,
            "wlb_score": 4,
        })
        self.assertEqual(1, len(jobs))
        self.assertIn("Python and SQL", jobs[0].description)
        self.assertEqual(
            "https://careers.walmart.com/job/R-1234567", jobs[0].url
        )

if __name__ == "__main__":
    unittest.main()
