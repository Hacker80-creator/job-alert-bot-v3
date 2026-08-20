from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import job_monitor_entry
import job_monitor_parallel
import source_discovery


class SourceDiscoveryTests(unittest.TestCase):
    @patch("source_discovery.discover_company")
    def test_run_names_probes_explicit_list(self, discover) -> None:
        discover.side_effect = lambda name: {"name": name, "status": "unresolved"}

        result = source_discovery.run_names(["Second", "First"], workers=2)

        self.assertEqual(2, result["requested"])
        self.assertEqual(["First", "Second"], [row["name"] for row in result["results"]])

    def test_identity_matching_rejects_short_brand_collisions(self) -> None:
        self.assertTrue(source_discovery.identity_matches("Datadog", "Careers at Datadog"))
        self.assertTrue(source_discovery.identity_matches("Tavant Technologies", "Tavant"))
        self.assertFalse(source_discovery.identity_matches("Box", "Boxed Careers"))
        self.assertFalse(source_discovery.identity_matches("SAP", "Sapphire"))

    def test_slug_candidates_include_compact_and_hyphenated_forms(self) -> None:
        candidates = source_discovery.slug_candidates("Example Technologies (India)")
        self.assertIn("exampletechnologies", candidates)
        self.assertIn("example-technologies", candidates)
        self.assertIn("example", candidates)

    @patch("source_discovery.get_json")
    def test_empty_smartrecruiters_response_does_not_verify_guessed_slug(
        self, get_json
    ) -> None:
        get_json.return_value = {"content": [], "totalFound": 0}

        result = source_discovery.probe_smartrecruiters(
            object(), "Example", "example"
        )

        self.assertIsNone(result)

    def test_merge_refuses_missing_batch_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "part-0.json").write_text(json.dumps({
                "batch_index": 0,
                "results": [],
            }), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                source_discovery.merge_results(folder, folder / "out.yaml", expected_parts=2)

    def test_merge_writes_only_verified_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = {
                "name": "Example", "kind": "product", "wlb_score": 3,
                "ats": "greenhouse", "slug": "example", "enabled": True,
                "verified_job_count": 2,
            }
            (folder / "part-0.json").write_text(json.dumps({
                "batch_index": 0,
                "results": [
                    {"name": "Example", "status": "verified", "source": source},
                    {"name": "Missing", "status": "unresolved"},
                ],
            }), encoding="utf-8")
            output = folder / "out.yaml"
            with patch.object(
                source_discovery, "DISCOVERED_FILE", folder / "existing.yaml"
            ):
                source_discovery.merge_results(folder, output, expected_parts=1)
            merged = yaml.safe_load(output.read_text(encoding="utf-8"))
            self.assertEqual(["Example"], [item["name"] for item in merged["companies"]])

    def test_workable_parser_maps_public_jobs(self) -> None:
        payload = {"jobs": [{
            "title": "Data Analyst", "location": {"city": "Bengaluru", "country": "India"},
            "url": "https://example.test/job", "description": "Python and SQL",
        }]}
        with patch.object(job_monitor_parallel.bot, "get_json", return_value=payload):
            jobs = job_monitor_parallel.parse_workable({
                "name": "Example", "slug": "example", "wlb_score": 3,
            })
        self.assertEqual(1, len(jobs))
        self.assertEqual("Bengaluru India", jobs[0].location)

    def test_eu_lever_parser_uses_configured_host(self) -> None:
        company = {"name": "Example", "slug": "example", "api_host": "api.eu.lever.co"}
        with patch.object(job_monitor_entry.bot, "get_json", return_value=[] ) as mocked:
            self.assertEqual([], job_monitor_entry.parse_lever_with_region(company))
        self.assertIn("api.eu.lever.co", mocked.call_args.args[0])

    def test_discovery_workflow_is_manual_read_only_and_uses_batches_of_25(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "discover-sources.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("--batch-size 25", workflow)
        self.assertIn("max-parallel: 6", workflow)


if __name__ == "__main__":
    unittest.main()
