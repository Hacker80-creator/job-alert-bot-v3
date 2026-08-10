from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from merge_job_state import merge_seen_state, merge_state


class StateMergeTests(unittest.TestCase):
    def test_remote_seen_records_win_and_generated_records_are_added(self) -> None:
        latest = {
            "same": {"first_seen_utc": "2026-08-10T19:30:00Z"},
            "remote-only": {"title": "Already delivered"},
        }
        generated = {
            "same": {"first_seen_utc": "2026-08-10T19:46:00Z"},
            "generated-only": {"title": "New alert"},
        }
        merged = merge_seen_state(latest, generated)
        self.assertEqual(
            "2026-08-10T19:30:00Z", merged["same"]["first_seen_utc"]
        )
        self.assertIn("remote-only", merged)
        self.assertIn("generated-only", merged)

    def test_state_directories_are_merged_without_losing_health(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            generated = root / "generated"
            current = root / "state"
            generated.mkdir()
            current.mkdir()
            (current / "seen_jobs.json").write_text(
                json.dumps({"remote": {"title": "Old"}}), encoding="utf-8"
            )
            (generated / "seen_jobs.json").write_text(
                json.dumps({"new": {"title": "New"}}), encoding="utf-8"
            )
            health = {"failed_sources": [], "official_source_count": 400}
            (generated / "scan_health.json").write_text(
                json.dumps(health), encoding="utf-8"
            )

            merge_state(generated, current)

            seen = json.loads((current / "seen_jobs.json").read_text(encoding="utf-8"))
            saved_health = json.loads(
                (current / "scan_health.json").read_text(encoding="utf-8")
            )
            self.assertEqual({"remote", "new"}, set(seen))
            self.assertEqual(health, saved_health)


if __name__ == "__main__":
    unittest.main()