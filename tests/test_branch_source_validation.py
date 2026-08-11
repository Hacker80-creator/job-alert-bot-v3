from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import branch_source_validation as validation
import job_monitor as bot


class BranchSourceValidationTests(unittest.TestCase):
    def test_source_names_reads_only_enabled_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.yaml"
            path.write_text(
                "companies:\n"
                "  - name: Working\n"
                "    enabled: true\n"
                "  - name: Disabled\n"
                "    enabled: false\n",
                encoding="utf-8",
            )
            self.assertEqual(["Working"], validation.source_names(path))

    @patch("branch_source_validation.job_monitor_entry_v32.load_final_config")
    @patch("branch_source_validation.custom_source_parsers_v19.fetch_company_jobs_with_custom_v19")
    def test_run_writes_non_mutating_summary(self, fetch, load_config) -> None:
        fetch.return_value = [
            bot.Job("Example", "Data Analyst", "Bangalore", "https://example/jobs/1", "Official")
        ]
        load_config.return_value = {
            "companies": [{"name": "Example", "ats": "greenhouse", "enabled": True}]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = root / "batch.yaml"
            output = root / "summary.json"
            batch.write_text("companies:\n  - name: Example\n", encoding="utf-8")
            code = validation.run(batch, output, workers=1)
            summary = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(0, code)
        self.assertEqual(1, summary["working"])
        self.assertEqual(0, summary["failed"])
        self.assertEqual("https://example/jobs/1", summary["results"][0]["sample_jobs"][0]["url"])


if __name__ == "__main__":
    unittest.main()
