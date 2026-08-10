from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import career_source_validation as validation


class FakeResponse:
    def __init__(self, payload, status_code=200, url="https://example.com"):
        self._payload = payload
        self.status_code = status_code
        self.url = url
        self.text = ""
        self.headers = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.post_url = ""
        self.post_body = None

    def post(self, url, json=None, **kwargs):
        self.post_url = url
        self.post_body = json
        return FakeResponse(self.payload, url=url)


class CareerSourceValidationTests(unittest.TestCase):
    def test_complete_mapping_is_unique_and_canonical(self) -> None:
        records = validation.read_mappings()
        self.assertEqual(432, len(records))
        self.assertEqual(432, len({item["name"].casefold() for item in records}))
        self.assertEqual(26, sum(
            bool(item["declared_no_public_board"]) for item in records
        ))
        self.assertIn("Dassault Systèmes", {item["name"] for item in records})

    def test_explicit_no_public_board_never_touches_network(self) -> None:
        record = {
            "name": "Example",
            "submitted_name": "Example",
            "declared_no_public_board": True,
        }
        with patch.object(validation.requests, "Session") as session:
            result = validation.classify_company(record)
        session.assert_not_called()
        self.assertEqual("NO_PUBLIC_BOARD", result["status"])

    def test_workday_source_discovers_india_facet(self) -> None:
        session = FakeSession({
            "total": 12,
            "jobPostings": [{"title": "Data Analyst"}],
            "facets": [{
                "facetParameter": "locationCountry",
                "values": [{"descriptor": "India", "id": "india-id"}],
            }],
        })
        result = validation.probe_workday(
            session,
            "Example",
            "https://example.wd1.myworkdayjobs.com/External?locationCountry=india-id",
        )
        self.assertIsNotNone(result)
        self.assertEqual("WORKING", result["status"])
        self.assertEqual("workday_india", result["source"]["ats"])
        self.assertEqual(
            "https://example.wd1.myworkdayjobs.com/wday/cxs/example/External/jobs",
            session.post_url,
        )

    def test_known_resolution_is_used_before_blocked_top_level_page(self) -> None:
        resolved = {
            "status": "WORKING",
            "provider": "ashby",
            "job_count": 3,
            "source": {"name": "Chronosphere", "ats": "ashby", "slug": "chronospherejobs"},
        }
        with patch.object(validation, "run_provider", return_value=resolved) as probe:
            result = validation.classify_company({
                "name": "Chronosphere",
                "source_url": "https://chronosphere.io/careers/",
                "declared_no_public_board": False,
            })
        self.assertEqual("WORKING", result["status"])
        self.assertTrue(result["discovered_from_official_page"])
        probe.assert_called_once()

    def test_merge_refuses_missing_parallel_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "part-0.json").write_text(json.dumps({
                "batch_index": 0,
                "results": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "missing batch artifacts"):
                validation.merge_results(
                    root, root / "runtime.yaml", expected_parts=2
                )

    def test_workflow_is_manual_read_only_and_has_18_batches(self) -> None:
        workflow = (
            Path(__file__).parents[1]
            / ".github"
            / "workflows"
            / "validate-career-sources.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("max-parallel: 18", workflow)
        self.assertIn("--expected-parts 18", workflow)
        self.assertIn("batch: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]", workflow)


if __name__ == "__main__":
    unittest.main()