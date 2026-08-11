from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v16 as parsers


class SourceBatchV16Tests(unittest.TestCase):
    @patch("custom_source_parsers_v16.requests.get")
    def test_applytojob_parser_maps_cards(self, get: Mock) -> None:
        listing = Mock()
        listing.url = "https://example.applytojob.com/"
        listing.text = """
        <ul><li class="list-group-item">
          <h3><a href="/apply/abc/Data-Analyst">Data Analyst</a></h3>
          <ul class="list-group-item-text">
            <li>Bengaluru, India</li><li>Data Science</li>
          </ul>
        </li></ul>
        """
        listing.raise_for_status.return_value = None
        detail = Mock()
        detail.text = '<main><div class="job-description">Python SQL analytics</div></main>'
        detail.raise_for_status.return_value = None
        get.side_effect = [listing, detail]

        jobs = parsers.parse_applytojob_html({
            "name": "Example", "ats": "applytojob_html",
            "url": listing.url, "career_site_url": listing.url,
            "wlb_score": 3,
        })

        self.assertEqual(1, len(jobs))
        self.assertEqual("Data Analyst", jobs[0].title)
        self.assertEqual("Bengaluru, India", jobs[0].location)
        self.assertEqual("Data Science", jobs[0].department)
        self.assertEqual(
            "https://example.applytojob.com/apply/abc/Data-Analyst",
            jobs[0].url,
        )
        self.assertIn("Python SQL", jobs[0].description)

    def test_eightfold_smart_apply_payload_decodes_positions(self) -> None:
        payload = parsers._smart_apply_payload("""
          <code id="smartApplyData" style="display:none">
          {"positions":[{"id":123,"posting_name":"Data Analyst"}]}
          </code>
        """)
        self.assertEqual("Data Analyst", payload["positions"][0]["posting_name"])

    @patch("custom_source_parsers_v16.requests.get")
    def test_jobs2web_rss_ignores_explicit_empty_item(self, get: Mock) -> None:
        response = Mock()
        response.content = b"""<?xml version='1.0'?><rss><channel><item>
          <title>No jobs currently available - Check out our other opportunities.</title>
          <link>https://jobs.example.com</link><guid>0</guid>
        </item></channel></rss>"""
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_jobs2web_rss({
            "name": "Example", "url": "https://jobs.example.com/rss",
            "career_site_url": "https://jobs.example.com", "search_terms": ["data"],
        })
        self.assertEqual([], jobs)

    @patch("custom_source_parsers_v16.bot.parse_workday_search")
    def test_workday_multi_combines_distinct_tenants(self, parse: Mock) -> None:
        parse.side_effect = [
            [parsers.bot.Job(
                company="Example", title="Data Analyst", location="Bengaluru, India",
                url="https://one.example/job/1", source="Official careers: Workday",
            )],
            [parsers.bot.Job(
                company="Example", title="AI Engineer", location="Remote, India",
                url="https://two.example/job/2", source="Official careers: Workday",
            )],
        ]
        jobs = parsers.parse_workday_multi({
            "name": "Example", "ats": "workday_multi", "sources": [
                {"label": "One", "url": "https://one.example/jobs",
                 "career_site_url": "https://one.example"},
                {"label": "Two", "url": "https://two.example/jobs",
                 "career_site_url": "https://two.example"},
            ],
        })
        self.assertEqual(2, len(jobs))
        self.assertEqual(2, parse.call_count)

    @patch("custom_source_parsers_v16.requests.get")
    @patch("custom_source_parsers_v16.bot.parse_html_search")
    def test_direct_job_html_enriches_schema_fields(
        self, parse: Mock, get: Mock,
    ) -> None:
        parse.return_value = [parsers.bot.Job(
            company="Example", title="Data Analyst",
            location="Data Analyst Bengaluru, India", url="https://example.com/job/1",
            source="Official careers: HTML fallback",
        )]
        response = Mock()
        response.text = """
        <script type="application/ld+json">
        {"@type":"JobPosting","title":"Data Analyst","description":"Python SQL analytics","identifier":{"value":"REQ-1"},"jobLocation":{"@type":"Place","address":{"addressLocality":"Bengaluru","addressCountry":"India"}}}
        </script>
        """
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_direct_job_html({
            "name": "Example", "url": "https://example.com/jobs",
            "ats": "direct_job_html",
        })
        self.assertEqual("REQ-1", jobs[0].requisition_id)
        self.assertIn("Bengaluru", jobs[0].location)
        self.assertIn("Python SQL", jobs[0].description)

    @patch("custom_source_parsers_v16.requests.get")
    def test_freshteam_maps_server_rendered_cards(self, get: Mock) -> None:
        response = Mock()
        response.url = "https://example.freshteam.com/jobs"
        response.text = """
        <li class="heading">
          <a class="job-title" href="/jobs/abc/data-analyst">Data Analyst</a>
          <span class="job-location"><span class="location-info">Bangalore, India</span></span>
          <div class="job-list-info"><div class="job-desc">Python and SQL</div></div>
        </li>
        """
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_freshteam_html({
            "name": "Example", "url": response.url,
            "max_candidate_details": 0,
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Bangalore, India", jobs[0].location)
        self.assertEqual(
            "https://example.freshteam.com/jobs/abc/data-analyst",
            jobs[0].url,
        )

    @patch("custom_source_parsers_v16.requests.get")
    def test_trakstar_maps_title_location_and_job_url(self, get: Mock) -> None:
        response = Mock()
        response.url = "https://example.hire.trakstar.com/"
        response.text = """
        <article class="js-careers-page-job-list-item">
          <a href="/jobs/fk123/">Apply</a>
          <span class="js-job-list-opening-name" title="AI Engineer">AI Engineer</span>
          <span class="js-job-list-opening-loc" title="Bengaluru, India"></span>
        </article>
        """
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_trakstar_html({
            "name": "Example", "url": response.url,
            "max_candidate_details": 0,
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("AI Engineer", jobs[0].title)
        self.assertEqual("Bengaluru, India", jobs[0].location)
        self.assertEqual(
            "https://example.hire.trakstar.com/jobs/fk123/", jobs[0].url,
        )

    @patch("custom_source_parsers_v16.requests.Session")
    def test_ripplehire_uses_json_api_and_enriches_details(
        self, session_class: Mock,
    ) -> None:
        session = session_class.return_value
        landing = Mock(url="https://example.ripplehire.com/candidate/?token=t")
        landing.raise_for_status.return_value = None
        language = Mock()
        language.raise_for_status.return_value = None
        language.json.return_value = {"companyDefaultLang": "en"}
        detail = Mock()
        detail.raise_for_status.return_value = None
        detail.json.return_value = {
            "jobVO": {"jobDesc": "Build Python analytics products"},
        }
        session.get.side_effect = [landing, language, detail]
        search = Mock()
        search.raise_for_status.return_value = None
        search.json.return_value = {
            "totalJobCount": 1,
            "jobVoList": [{
                "jobSeq": "123", "jobTitle": "Data Scientist",
                "locations": "Bengaluru, India", "jobReqExp": "3 - 5 Years",
                "jobCode": "REQ-123", "businessUnit": "Data & AI",
            }],
        }
        session.post.return_value = search
        jobs = parsers.parse_ripplehire({
            "name": "Example",
            "url": "https://example.ripplehire.com/candidate/",
            "career_site_url": "https://example.ripplehire.com/candidate/?token=t#list",
            "token": "t", "page_size": 100, "max_candidate_details": 1,
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("REQ-123", jobs[0].requisition_id)
        self.assertIn("Python analytics", jobs[0].description)
        self.assertEqual("application/json", session.post.call_args.kwargs["headers"]["Accept"])


if __name__ == "__main__":
    unittest.main()
