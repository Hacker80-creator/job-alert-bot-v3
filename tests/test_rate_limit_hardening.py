from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v11 as workday
import job_monitor as bot


class FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class RateLimitHardeningTests(unittest.TestCase):
    def test_post_list_query_retries_transient_rate_limit(self) -> None:
        responses = [FakeResponse(429), FakeResponse(200, {"jobs": [1]})]
        with patch.object(bot.requests, "post", side_effect=responses) as request, patch.object(
            bot.time, "sleep"
        ) as sleep:
            result = bot.get_json("https://example.com/jobs", method="POST")
        self.assertEqual({"jobs": [1]}, result)
        self.assertEqual(2, request.call_count)
        sleep.assert_called_once_with(1)

    def test_get_detail_does_not_amplify_rate_limit(self) -> None:
        with patch.object(
            bot.requests, "get", return_value=FakeResponse(429)
        ) as request, self.assertRaisesRegex(RuntimeError, "429"):
            bot.get_json("https://example.com/job/one")
        request.assert_called_once()

    def test_get_list_retries_transient_timeout(self) -> None:
        with patch.object(
            bot.requests,
            "get",
            side_effect=[
                bot.requests.Timeout("temporary timeout"),
                FakeResponse(200, {"jobs": [1]}),
            ],
        ) as request, patch.object(bot.time, "sleep") as sleep:
            result = bot.get_json("https://example.com/jobs")
        self.assertEqual({"jobs": [1]}, result)
        self.assertEqual(2, request.call_count)
        sleep.assert_called_once_with(1)

    def test_workday_india_skips_nonmatching_location_details(self) -> None:
        company = {
            "name": "Example",
            "url": "https://example.wd1.myworkdayjobs.com/wday/cxs/example/External/jobs",
            "career_site_url": "https://example.wd1.myworkdayjobs.com/External",
            "search_terms": ["data"],
            "max_results_per_term": 20,
        }

        def fake_get_json(url, *, method="GET", payload=None):
            if method == "GET":
                self.fail("nonmatching location must not request job detail")
            if not payload.get("appliedFacets"):
                return {
                    "facets": [{
                        "facetParameter": "locationCountry",
                        "values": [{"descriptor": "India", "id": "india-id"}],
                    }]
                }
            return {
                "total": 1,
                "jobPostings": [{
                    "title": "Data Analyst",
                    "locationsText": "Chennai, India",
                    "externalPath": "/job/Data-Analyst/123",
                }],
            }

        with patch.object(
            workday.bot, "get_json", side_effect=fake_get_json
        ), patch.object(
            workday.bot, "is_target_title", return_value=True
        ), patch.object(
            workday.bot, "has_location_match", return_value=False
        ):
            jobs = workday.parse_workday_india(company)
        self.assertEqual(1, len(jobs))
        self.assertEqual("", jobs[0].description)


if __name__ == "__main__":
    unittest.main()
