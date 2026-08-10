"""Merge a completed scan's state into the latest state from GitHub main."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def merge_seen_state(
    latest_main: dict[str, Any], generated: dict[str, Any]
) -> dict[str, Any]:
    """Return the union while preserving main's original first-seen records."""
    merged = dict(generated)
    merged.update(latest_main)
    return merged


def merge_state(generated_dir: Path, state_dir: Path) -> None:
    latest_seen = read_object(state_dir / "seen_jobs.json")
    generated_seen = read_object(generated_dir / "seen_jobs.json")
    write_object(
        state_dir / "seen_jobs.json",
        merge_seen_state(latest_seen, generated_seen),
    )

    generated_health_path = generated_dir / "scan_health.json"
    if generated_health_path.exists():
        write_object(
            state_dir / "scan_health.json",
            read_object(generated_health_path),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated-dir", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    merge_state(args.generated_dir, args.state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())