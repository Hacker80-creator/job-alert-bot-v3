"""Recover GitHub Actions scanners when native cron events are dropped."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


TARGET_WORKFLOWS = (
    ("ML/data", "job-alerts.yml"),
    ("QA", "qa-job-alerts.yml"),
    ("SAP/BI", "sap-bi-job-alerts.yml"),
)


@dataclass(frozen=True)
class WorkflowStatus:
    label: str
    workflow_file: str
    latest_run_utc: datetime | None
    latest_event: str = ""
    latest_status: str = ""


class ActionsClient(Protocol):
    def list_main_runs(self, workflow_file: str) -> list[dict[str, Any]]: ...
    def dispatch_main(self, workflow_file: str) -> None: ...


def parse_github_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class GitHubActionsClient:
    def __init__(self, repository: str, token: str, api_url: str) -> None:
        if not repository or "/" not in repository:
            raise ValueError("GITHUB_REPOSITORY must use owner/repository format")
        if not token:
            raise ValueError("GITHUB_TOKEN is required")
        self.repository = repository
        self.token = token
        self.api_url = api_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.api_url}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "job-alert-scheduler-watchdog",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                response_body = response.read()
                return response.status, (
                    json.loads(response_body) if response_body else {}
                )
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(
                f"GitHub API {method} {path} failed with {exc.code}: {detail}"
            ) from exc

    def list_main_runs(self, workflow_file: str) -> list[dict[str, Any]]:
        encoded_file = quote(workflow_file, safe="")
        path = (
            f"/repos/{self.repository}/actions/workflows/{encoded_file}/runs"
            "?branch=main&per_page=10"
        )
        status, data = self._request("GET", path)
        if status != 200 or not isinstance(data, dict):
            raise RuntimeError(
                f"Unexpected GitHub workflow-runs response status: {status}"
            )
        runs = data.get("workflow_runs") or []
        if not isinstance(runs, list):
            raise RuntimeError("GitHub workflow-runs response was not a list")
        return [run for run in runs if isinstance(run, dict)]

    def dispatch_main(self, workflow_file: str) -> None:
        encoded_file = quote(workflow_file, safe="")
        path = (
            f"/repos/{self.repository}/actions/workflows/{encoded_file}/dispatches"
        )
        status, _ = self._request("POST", path, {"ref": "main"})
        # GitHub's API versions have returned either 204 or a 200 response
        # containing the newly created workflow run.
        if status not in {200, 204}:
            raise RuntimeError(
                f"Unexpected workflow-dispatch response status: {status}"
            )


def latest_main_status(
    label: str,
    workflow_file: str,
    runs: list[dict[str, Any]],
) -> WorkflowStatus:
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    for run in runs:
        if str(run.get("head_branch") or "") != "main":
            continue
        created_at = run.get("created_at")
        if not created_at:
            continue
        candidates.append((parse_github_time(str(created_at)), run))
    if not candidates:
        return WorkflowStatus(label, workflow_file, None)
    created, run = max(candidates, key=lambda item: item[0])
    return WorkflowStatus(
        label,
        workflow_file,
        created,
        str(run.get("event") or ""),
        str(run.get("status") or ""),
    )


def find_stale_workflows(
    client: ActionsClient,
    *,
    now: datetime,
    max_age_minutes: int,
) -> list[WorkflowStatus]:
    cutoff = now.astimezone(timezone.utc) - timedelta(minutes=max_age_minutes)
    statuses = [
        latest_main_status(label, workflow_file, client.list_main_runs(workflow_file))
        for label, workflow_file in TARGET_WORKFLOWS
    ]
    stale = [
        status
        for status in statuses
        if status.latest_run_utc is None or status.latest_run_utc < cutoff
    ]
    return sorted(
        stale,
        key=lambda status: status.latest_run_utc or datetime.min.replace(
            tzinfo=timezone.utc
        ),
    )


def run_watchdog(
    client: ActionsClient,
    *,
    now: datetime,
    max_age_minutes: int = 130,
    dry_run: bool = False,
) -> str | None:
    stale = find_stale_workflows(
        client,
        now=now,
        max_age_minutes=max_age_minutes,
    )
    if not stale:
        print(
            "WATCHDOG_OK: all scanners have a main-branch run within "
            f"{max_age_minutes} minutes"
        )
        return None

    selected = stale[0]
    age = (
        "never"
        if selected.latest_run_utc is None
        else str(int((now - selected.latest_run_utc).total_seconds() // 60))
        + " minutes"
    )
    print(
        f"WATCHDOG_STALE: {selected.label} latest main run age={age}; "
        f"stale_count={len(stale)}"
    )
    if dry_run:
        print(f"WATCHDOG_DRY_RUN: would dispatch {selected.workflow_file}")
    else:
        client.dispatch_main(selected.workflow_file)
        print(f"WATCHDOG_DISPATCHED: {selected.workflow_file} on main")
    return selected.workflow_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=int(os.getenv("WATCHDOG_MAX_AGE_MINUTES", "130")),
    )
    args = parser.parse_args()
    if args.max_age_minutes < 30:
        parser.error("--max-age-minutes must be at least 30")

    client = GitHubActionsClient(
        os.getenv("GITHUB_REPOSITORY", ""),
        os.getenv("GITHUB_TOKEN", ""),
        os.getenv("GITHUB_API_URL", "https://api.github.com"),
    )
    run_watchdog(
        client,
        now=datetime.now(timezone.utc),
        max_age_minutes=args.max_age_minutes,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
