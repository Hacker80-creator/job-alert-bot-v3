from __future__ import annotations

import unittest
from pathlib import Path

import source_discovery_strict


class StrictDiscoveryTests(unittest.TestCase):
    def test_non_greenhouse_empty_results_are_rejected(self) -> None:
        wrapped = source_discovery_strict.require_observed_jobs(
            lambda *_args, **_kwargs: {"ats": "smartrecruiters", "verified_job_count": 0}
        )
        self.assertIsNone(wrapped(None, "Example", "example"))

    def test_observed_jobs_are_accepted(self) -> None:
        expected = {"ats": "ashby", "verified_job_count": 3}
        wrapped = source_discovery_strict.require_observed_jobs(
            lambda *_args, **_kwargs: expected
        )
        self.assertIs(expected, wrapped(None, "Example", "example"))

    def test_strict_workflow_is_manual_and_read_only(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "discover-sources-strict.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("source_discovery_strict.py", workflow)
        self.assertIn("--batch-size 25", workflow)


if __name__ == "__main__":
    unittest.main()
