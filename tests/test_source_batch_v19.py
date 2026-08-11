from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v11 as talentbrew
import custom_source_parsers_v15 as avature


class SourceBatchV19Tests(unittest.TestCase):
    @patch("custom_source_parsers_v15.requests.get")
    @patch("custom_source_parsers_v15.requests.post")
    def test_avature_parser_supports_hsbc_pipeline_detail_links(
        self, post: Mock, get: Mock,
    ) -> None:
        listing = Mock()
        listing.url = "https://mycareer.hsbc.com/en_GB/external/SearchJobs/"
        listing.text = """
        <article class="article--result">
          <h3><a href="/en_GB/external/PipelineDetail/Data-Analyst/270067">Data Analyst</a></h3>
        </article>
        """
        listing.raise_for_status.return_value = None
        post.return_value = listing
        detail = Mock()
        detail.text = """
        <article class="article--details">
          <div class="article__content">Python SQL analytics</div>
          <div class="article__content__view__field view-icon--location">
            <div class="article__content__view__field__value">Bangalore, India</div>
          </div>
        </article>
        """
        detail.raise_for_status.return_value = None
        get.return_value = detail

        jobs = avature.parse_avature_html({
            "name": "HSBC",
            "url": listing.url,
            "search_terms": ["data"],
            "wlb_score": 3,
        })

        self.assertEqual(1, len(jobs))
        self.assertEqual("Data Analyst", jobs[0].title)
        self.assertEqual("Bangalore, India", jobs[0].location)
        self.assertIn("/PipelineDetail/Data-Analyst/270067", jobs[0].url)

    @patch("custom_source_parsers_v11.requests.get")
    def test_talentbrew_parser_reads_ikea_card_fields(self, get: Mock) -> None:
        listing = Mock()
        listing.url = "https://jobs.ikea.com/en/search-jobs?k=data&p=1"
        listing.text = """
        <li class="job-list__item">
          <a class="job-list__anchor" data-job-id="351514"
             href="/en/job/bengaluru/business-analyst/24107/351514">
            <span class="job-list__anchor-arrow-text visually-hidden">View job</span>
            <span class="job-list__title">Business Analyst</span>
            <ul class="job-list__info Bengaluru">
              <li><span class="job-list__location">Bangalore, Karnataka, India</span></li>
              <li><span class="job-list__categories">IT &amp; Digital Solutions</span></li>
            </ul>
          </a>
        </li>
        """
        listing.raise_for_status.return_value = None
        get.return_value = listing

        jobs = talentbrew.parse_talentbrew_html({
            "name": "IKEA Digital",
            "url": "https://jobs.ikea.com/en/search-jobs",
            "search_terms": ["data"],
            "max_pages_per_term": 2,
            "max_candidate_details": 0,
            "wlb_score": 4,
        })

        self.assertEqual(1, len(jobs))
        self.assertEqual("Business Analyst", jobs[0].title)
        self.assertEqual("Bangalore, Karnataka, India", jobs[0].location)
        self.assertEqual("IT & Digital Solutions", jobs[0].department)


if __name__ == "__main__":
    unittest.main()
