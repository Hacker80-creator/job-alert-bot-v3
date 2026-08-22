from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v11 as workday
import job_monitor as bot


class FakeResponse:
    def __init__(self, status_code: int, payload=None, *, text="", content_type="application/json"):
        self.status_code = status_code
        self.payload = payload or {}
        self.text = text
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self.text:
            raise ValueError("not JSON")
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

    def test_workday_post_retries_html_then_uses_json(self) -> None:
        responses = [
            FakeResponse(200, text="<!doctype html><title>edge error</title>", content_type="text/html"),
            FakeResponse(200, {"jobPostings": [{"title": "Data Analyst"}]}),
        ]
        url = "https://example.wd1.myworkdayjobs.com/wday/cxs/example/External/jobs"
        with patch.object(bot.requests, "post", side_effect=responses) as request, patch.object(
            bot.time, "sleep"
        ) as sleep:
            result = bot.get_json(url, method="POST", payload={"searchText": "data"})

        self.assertEqual("Data Analyst", result["jobPostings"][0]["title"])
        self.assertEqual(2, request.call_count)
        headers = request.call_args.kwargs["headers"]
        self.assertEqual("application/json", headers["Accept"])
        self.assertEqual("application/json", headers["Content-Type"])
        self.assertEqual("https://example.wd1.myworkdayjobs.com", headers["Origin"])
        self.assertEqual("https://example.wd1.myworkdayjobs.com/External", headers["Referer"])
        self.assertNotIn("SuriJobAlertBot", headers["User-Agent"])
        sleep.assert_called_once_with(1)

    def test_post_invalid_json_fails_clearly_after_bounded_retries(self) -> None:
        response = FakeResponse(200, text="", content_type="text/html")
        response.json = Mock(side_effect=ValueError("not JSON"))
        with patch.object(bot.requests, "post", return_value=response) as request, patch.object(
            bot.time, "sleep"
        ) as sleep, self.assertRaisesRegex(RuntimeError, "empty response.*status 200"):
            bot.get_json("https://example.com/jobs", method="POST")
        self.assertEqual(3, request.call_count)
        self.assertEqual([unittest.mock.call(1), unittest.mock.call(3)], sleep.call_args_list)

    def test_get_invalid_json_is_not_retried(self) -> None:
        response = FakeResponse(200, text="<html>blocked</html>", content_type="text/html")
        with patch.object(bot.requests, "get", return_value=response) as request, self.assertRaisesRegex(
            RuntimeError, "HTML response.*status 200"
        ):
            bot.get_json("https://example.com/job/one")
        request.assert_called_once()

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
