from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v20 as parsers


class SourceBatchV21Tests(unittest.TestCase):
    @patch("custom_source_parsers_v20.requests.get")
    def test_listing_jsonld_reads_nested_jobpostings(self, get: Mock) -> None:
        response = Mock()
        response.text = """
        <script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[
          {"@type":"Organization","name":"Example"},
          {"@type":"JobPosting","title":"Data Scientist",
           "url":"https://example.com/jobs/42",
           "identifier":{"value":"REQ-42"},
           "description":"Build machine learning models",
           "jobLocation":{"@type":"Place","address":{
             "addressLocality":"Bengaluru","addressCountry":"India"}}}
        ]}
        </script>
        """
        response.raise_for_status.return_value = None
        get.return_value = response

        jobs = parsers.parse_listing_jsonld({
            "name": "Example",
            "url": "https://example.com/careers",
            "wlb_score": 4,
        })

        self.assertEqual(1, len(jobs))
        self.assertEqual("Data Scientist", jobs[0].title)
        self.assertIn("Bengaluru", jobs[0].location)
        self.assertEqual("REQ-42", jobs[0].requisition_id)
        self.assertEqual("https://example.com/jobs/42", jobs[0].url)

    def test_structured_listing_rejects_expired_posting(self) -> None:
        self.assertTrue(parsers._posting_is_stale({
            "validThrough": "2020-01-01T00:00:00+00:00",
        }, max_age_days=0))


if __name__ == "__main__":
    unittest.main()
