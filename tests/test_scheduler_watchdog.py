from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import github_scheduler_watchdog as watchdog


ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)


def run_record(
    created_at: datetime,
    *,
    branch: str = "main",
    event: str = "schedule",
    status: str = "completed",
) -> dict:
    return {
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "head_branch": branch,
        "event": event,
        "status": status,
    }


class FakeClient:
    def __init__(
        self,
        runs: dict[str, list[dict]],
        *,
        fail_dispatch: set[str] | None = None,
    ) -> None:
        self.runs = runs
        self.dispatched: list[str] = []
        self.fail_dispatch = fail_dispatch or set()

    def list_main_runs(self, workflow_file: str) -> list[dict]:
        return self.runs.get(workflow_file, [])

    def dispatch_main(self, workflow_file: str) -> None:
        if workflow_file in self.fail_dispatch:
            raise RuntimeError("simulated dispatch failure")
        self.dispatched.append(workflow_file)


class SchedulerWatchdogTests(unittest.TestCase):
    def test_parse_github_time_is_utc(self) -> None:
        parsed = watchdog.parse_github_time("2026-08-27T16:27:06Z")
        self.assertEqual(timezone.utc, parsed.tzinfo)
        self.assertEqual(16, parsed.hour)

    def test_all_recent_workflows_do_not_dispatch(self) -> None:
        recent = NOW - timedelta(minutes=90)
        client = FakeClient({
            workflow: [run_record(recent)]
            for _, workflow in watchdog.TARGET_WORKFLOWS
        })
        selected = watchdog.run_watchdog(
            client, now=NOW, max_age_minutes=130
        )
        self.assertEqual([], selected)
        self.assertEqual([], client.dispatched)

    def test_every_stale_workflow_is_dispatched_oldest_first(self) -> None:
        client = FakeClient({
            "job-alerts.yml": [run_record(NOW - timedelta(minutes=150))],
            "qa-job-alerts.yml": [run_record(NOW - timedelta(minutes=180))],
            "sap-bi-job-alerts.yml": [run_record(NOW - timedelta(minutes=140))],
        })
        selected = watchdog.run_watchdog(
            client, now=NOW, max_age_minutes=130
        )
        expected = [
            "qa-job-alerts.yml",
            "job-alerts.yml",
            "sap-bi-job-alerts.yml",
        ]
        self.assertEqual(expected, selected)
        self.assertEqual(expected, client.dispatched)

    def test_every_missing_workflow_is_dispatched_per_check(self) -> None:
        client = FakeClient({})
        selected = watchdog.run_watchdog(
            client, now=NOW, max_age_minutes=130
        )
        expected = [workflow for _, workflow in watchdog.TARGET_WORKFLOWS]
        self.assertEqual(expected, selected)
        self.assertEqual(expected, client.dispatched)

    def test_feature_branch_runs_do_not_make_a_scanner_fresh(self) -> None:
        client = FakeClient({
            "job-alerts.yml": [
                run_record(NOW - timedelta(minutes=10), branch="feature/test")
            ],
            "qa-job-alerts.yml": [run_record(NOW - timedelta(minutes=10))],
            "sap-bi-job-alerts.yml": [run_record(NOW - timedelta(minutes=10))],
        })
        selected = watchdog.run_watchdog(
            client, now=NOW, max_age_minutes=130
        )
        self.assertEqual(["job-alerts.yml"], selected)

    def test_queued_or_manual_main_run_counts_as_fresh(self) -> None:
        client = FakeClient({
            "job-alerts.yml": [
                run_record(
                    NOW - timedelta(minutes=5),
                    event="workflow_dispatch",
                    status="queued",
                )
            ],
            "qa-job-alerts.yml": [run_record(NOW - timedelta(minutes=5))],
            "sap-bi-job-alerts.yml": [run_record(NOW - timedelta(minutes=5))],
        })
        self.assertEqual(
            [],
            watchdog.run_watchdog(client, now=NOW, max_age_minutes=130)
        )

    def test_dry_run_never_dispatches(self) -> None:
        client = FakeClient({})
        selected = watchdog.run_watchdog(
            client,
            now=NOW,
            max_age_minutes=130,
            dry_run=True,
        )
        self.assertEqual(
            [workflow for _, workflow in watchdog.TARGET_WORKFLOWS],
            selected,
        )
        self.assertEqual([], client.dispatched)

    def test_one_dispatch_failure_does_not_block_other_stale_scanners(self) -> None:
        client = FakeClient(
            {},
            fail_dispatch={"qa-job-alerts.yml"},
        )
        with self.assertRaisesRegex(RuntimeError, "qa-job-alerts.yml"):
            watchdog.run_watchdog(client, now=NOW, max_age_minutes=130)
        self.assertEqual(
            ["job-alerts.yml", "sap-bi-job-alerts.yml"],
            client.dispatched,
        )

    def test_workflow_has_redundant_off_peak_schedule_and_write_scope(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "scheduler-watchdog.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('cron: "11,26,41,56 * * * *"', workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("WATCHDOG_MAX_AGE_MINUTES: \"130\"", workflow)
        self.assertIn(
            "github.ref_name == 'main' && github.event_name != 'push'",
            workflow,
        )
        self.assertIn("github.ref_name != 'main'", workflow)
        self.assertIn("- feature/github-scheduler-watchdog", workflow)
        self.assertIn("- fix/watchdog-dispatch-all-stale", workflow)
        self.assertIn("workflow_run:", workflow)
        self.assertIn("Recover stale scanners", workflow)
        self.assertIn("- Bangalore product data job alerts", workflow)
        self.assertIn("- Bangalore QA job alerts", workflow)
        self.assertIn("- Bangalore SAP and BI job alerts", workflow)

    def test_target_workflows_support_dispatch_and_keep_native_schedule(self) -> None:
        expected = {
            "job-alerts.yml": 'cron: "7 */2 * * *"',
            "qa-job-alerts.yml": 'cron: "37 */2 * * *"',
            "sap-bi-job-alerts.yml": 'cron: "7 1-23/2 * * *"',
        }
        for workflow_file, cron in expected.items():
            with self.subTest(workflow=workflow_file):
                text = (
                    ROOT / ".github" / "workflows" / workflow_file
                ).read_text(encoding="utf-8")
                self.assertIn("workflow_dispatch:", text)
                self.assertIn(cron, text)


if __name__ == "__main__":
    unittest.main()
