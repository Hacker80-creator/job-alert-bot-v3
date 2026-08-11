from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v24 as parsers


class SourceBatchV25Tests(unittest.TestCase):
    @patch("custom_source_parsers_v24.requests.get")
    def test_wordpress_job_links_uses_detail_fields(self, get: Mock) -> None:
        listing = Mock(text='<a href="/jobs/data-analyst/">Data Analyst</a>', url="https://example.com/career/")
        listing.raise_for_status.return_value = None
        detail = Mock(text='<main><h1>Data Analyst</h1><p>Build dashboards</p><p>Location Bangalore Employment Type Full Time</p></main>', url="https://example.com/jobs/data-analyst/")
        detail.raise_for_status.return_value = None
        get.side_effect = [listing, detail]
        jobs = parsers.parse_wordpress_job_links({"name": "Example", "url": "https://example.com/career/"})
        self.assertEqual(1, len(jobs))
        self.assertEqual("Bangalore", jobs[0].location)
        self.assertEqual("data-analyst", jobs[0].requisition_id)

    @patch("custom_source_parsers_v24.requests.get")
    def test_skima_html_reads_uuid_and_location(self, get: Mock) -> None:
        response = Mock(text='''
        <div data-pagination-container data-last-page="1"></div>
        <div><a href="/74e803d6-59c3-4430-a10d-9c8199a170af">Data Analyst</a>
        <div><span>Bengaluru</span><span>Full Time</span></div></div>
        ''')
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_skima_html({
            "name": "Nykaa", "url": "https://careers.nykaa.com/",
            "career_site_url": "https://careers.nykaa.com/",
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Bengaluru", jobs[0].location)
        self.assertEqual("74e803d6-59c3-4430-a10d-9c8199a170af", jobs[0].requisition_id)


if __name__ == "__main__":
    unittest.main()
