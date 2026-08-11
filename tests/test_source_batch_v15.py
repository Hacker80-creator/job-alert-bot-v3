from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v15 as parsers


class SourceBatchV15Tests(unittest.TestCase):
    @patch("custom_source_parsers_v15.requests.get")
    @patch("custom_source_parsers_v15.requests.post")
    def test_avature_parser_maps_direct_job_detail_links(self, post: Mock, get: Mock) -> None:
        listing = Mock()
        listing.url = "https://jobs.example.com/en_US/careers/SearchJobs"
        listing.text = """
        <article class="article--result">
          <h3><a href="/en_US/careers/JobDetail/Data-Analyst/123">Data Analyst</a></h3>
          <span class="list-item-location">Bengaluru, Karnataka, India</span>
          <span class="list-item-family">Data</span>
        </article>
        """
        listing.raise_for_status.return_value = None
        post.return_value = listing
        detail = Mock()
        detail.text = '<article class="article--details"><div class="article__content">Python SQL analytics</div></article>'
        detail.raise_for_status.return_value = None
        get.return_value = detail

        jobs = parsers.parse_avature_html({
            "name": "Example", "url": listing.url, "ats": "avature_html",
            "search_terms": ["data"], "wlb_score": 3,
        })

        self.assertEqual(1, len(jobs))
        self.assertEqual("Data Analyst", jobs[0].title)
        self.assertEqual("Bengaluru, Karnataka, India", jobs[0].location)
        self.assertEqual("https://jobs.example.com/en_US/careers/JobDetail/Data-Analyst/123", jobs[0].url)
        self.assertIn("Python SQL", jobs[0].description)

    @patch("custom_source_parsers_v15.requests.get")
    @patch("custom_source_parsers_v15.requests.post")
    def test_avature_parser_supports_folder_detail_and_schema_location(
        self, post: Mock, get: Mock,
    ) -> None:
        listing = Mock()
        listing.url = "https://jobs.example.com/en_US/jobs/Jobs"
        listing.text = """
        <article class="article--result">
          <h3><a href="/en_US/jobs/FolderDetail/Data-Analyst/123">Data Analyst</a></h3>
        </article>
        """
        listing.raise_for_status.return_value = None
        post.return_value = listing
        detail = Mock()
        detail.text = """
        <article class="article--details"><div class="article__content">Python SQL</div></article>
        <script type="application/ld+json">
        {"@type":"JobPosting","title":"Data Analyst","jobLocation":{"@type":"Place","address":{"addressLocality":"Bengaluru","addressCountry":"India"}}}
        </script>
        """
        detail.raise_for_status.return_value = None
        get.return_value = detail

        jobs = parsers.parse_avature_html({
            "name": "Example", "url": listing.url, "ats": "avature_html",
            "search_terms": ["data"], "wlb_score": 3,
        })

        self.assertEqual(1, len(jobs))
        self.assertIn("Bengaluru", jobs[0].location)
        self.assertIn("Python SQL", jobs[0].description)


if __name__ == "__main__":
    unittest.main()
