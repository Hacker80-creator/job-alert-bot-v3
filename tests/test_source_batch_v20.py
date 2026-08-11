from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v19 as sitemap


class SourceBatchV20Tests(unittest.TestCase):
    @patch("custom_source_parsers_v19.requests.get")
    def test_next_sitemap_parser_reads_embedded_job_fields(
        self, get: Mock,
    ) -> None:
        listing = Mock()
        listing.content = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
          <url><loc>https://career.globant.com/job/Business-Analyst/78907</loc></url>
          <url><loc>https://career.globant.com/job/Java-Developer/10000</loc></url>
        </urlset>"""
        listing.raise_for_status.return_value = None

        detail = Mock()
        detail.text = r"""
        <main>Build analytics products with Python and SQL.</main>
        <script>self.__next_f.push([1,"{\"data\":{\"location\":\"Bengaluru, India\",\"jobReqId\":\"78907\",\"jobTitle\":\"Business Analyst\",\"area\":[{\"label\":\"Data and AI\"}]}}"])</script>
        """
        detail.raise_for_status.return_value = None
        get.side_effect = [listing, detail]

        jobs = sitemap.parse_next_sitemap({
            "name": "Globant",
            "url": "https://career.globant.com/sitemap.xml",
            "max_job_pages": 10,
            "wlb_score": 3,
        })

        self.assertEqual(1, len(jobs))
        self.assertEqual("Business Analyst", jobs[0].title)
        self.assertEqual("Bengaluru, India", jobs[0].location)
        self.assertEqual("78907", jobs[0].requisition_id)
        self.assertEqual("Data and AI", jobs[0].department)
        self.assertEqual(
            "https://career.globant.com/job/Business-Analyst/78907",
            jobs[0].url,
        )


if __name__ == "__main__":
    unittest.main()
