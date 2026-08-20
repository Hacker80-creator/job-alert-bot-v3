from __future__ import annotations

import unittest
from unittest.mock import patch

import job_monitor as bot


class FakeResponse:
    def __init__(self, status_code: int, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class EightfoldRateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company = {
            "name": "Example",
            "ats": "eightfold",
            "url": "https://careers.example.com/api/pcsx/search",
            "career_site_url": "https://careers.example.com/careers",
            "domain": "example.com",
            "search_terms": ["data"],
            "search_locations": ["India"],
            "max_results_per_search": 20,
            "rate_limit_attempts": 3,
            "rate_limit_base_delay_seconds": 0,
            "rate_limit_max_delay_seconds": 0,
        }

    def test_persistent_429_keeps_jobs_collected_from_earlier_page(self) -> None:
        positions = [
            {
                "id": f"job-{index}",
                "name": "Accounting Specialist",
                "locations": ["Bengaluru, Karnataka, India"],
            }
            for index in range(10)
        ]
        responses = [
            FakeResponse(200, {"data": {"positions": positions, "count": 20}}),
            FakeResponse(429),
            FakeResponse(429),
            FakeResponse(429),
        ]
        with patch.object(bot.requests, "get", side_effect=responses) as request, patch.object(
            bot.time, "sleep"
        ):
            jobs = bot.parse_eightfold(self.company)
        self.assertEqual(10, len(jobs))
        self.assertEqual(4, request.call_count)
        self.assertEqual("job-0", jobs[0].url.split("/job/")[1].split("?")[0])

    def test_temporary_429_retries_and_recovers(self) -> None:
        responses = [
            FakeResponse(429, headers={"Retry-After": "1"}),
            FakeResponse(200, {"data": {"positions": [], "count": 0}}),
        ]
        with patch.object(bot.requests, "get", side_effect=responses) as request, patch.object(
            bot.time, "sleep"
        ) as sleep:
            payload = bot._eightfold_search_json(self.company, {"query": "data"})
        self.assertEqual({"data": {"positions": [], "count": 0}}, payload)
        self.assertEqual(2, request.call_count)
        sleep.assert_called_once_with(0)

    def test_persistent_403_is_treated_as_temporary_throttle(self) -> None:
        responses = [FakeResponse(403), FakeResponse(403), FakeResponse(403)]
        with patch.object(bot.requests, "get", side_effect=responses) as request, patch.object(
            bot.time, "sleep"
        ):
            payload = bot._eightfold_search_json(self.company, {"query": "data"})
        self.assertIsNone(payload)
        self.assertEqual(3, request.call_count)


if __name__ == "__main__":
    unittest.main()
