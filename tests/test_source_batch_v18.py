from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v18 as parsers


class SourceBatchV18Tests(unittest.TestCase):
    @patch("custom_source_parsers_v18.requests.get")
    def test_enphase_api_maps_public_job_fields(self, get: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"rows": [{
            "jid": "job-1", "name": "Data Analyst",
            "location": "Bangalore, India", "category": "Engineering",
            "requisitionid": "9270",
            "description__value": "&lt;p&gt;Python and SQL analytics.&lt;/p&gt;",
        }]}
        get.return_value = response
        jobs = parsers.parse_enphase_api({
            "name": "Enphase Energy",
            "url": "https://enphase.com/api/v2/jobs",
            "detail_url_template": "https://enphase.com/en-in/job/{job_id}",
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Bangalore, India", jobs[0].location)
        self.assertEqual("9270", jobs[0].requisition_id)
        self.assertEqual("Python and SQL analytics.", jobs[0].description)
        self.assertEqual("https://enphase.com/en-in/job/job-1", jobs[0].url)

    @patch("custom_source_parsers_v18.requests.post")
    def test_pega_search_maps_server_rendered_job_card(self, post: Mock) -> None:
        response = Mock(url="https://www.pega.com/about/careers/job-listings?q=data")
        response.raise_for_status.return_value = None
        response.text = """
        <bolt-card-replacement>
          <a href="/about/careers/23766/analyst-ii">Show more</a>
          <h2>Job Category: Business Operations</h2>
          <h3>Analyst II, GTM Analytics &amp; BI</h3>
          <p>Location: India - Karnataka - Bangalore</p>
        </bolt-card-replacement>
        """
        post.return_value = response
        jobs = parsers.parse_pega_html({
            "name": "Pegasystems",
            "url": "https://www.pega.com/about/careers/job-listings",
            "search_terms": ["data"],
            "max_candidate_details": 0,
        })
        self.assertEqual(1, len(jobs))
        self.assertEqual("India - Karnataka - Bangalore", jobs[0].location)
        self.assertEqual("Business Operations", jobs[0].department)
        self.assertEqual("23766", jobs[0].requisition_id)
        self.assertEqual(
            "https://www.pega.com/about/careers/23766/analyst-ii",
            jobs[0].url,
        )


if __name__ == "__main__":
    unittest.main()
