"""Strict discovery entry point that rejects provider wildcard/empty responses."""
from __future__ import annotations

from typing import Any, Callable

import source_discovery as discovery


def require_observed_jobs(
    probe: Callable[..., dict[str, Any] | None],
) -> Callable[..., dict[str, Any] | None]:
    def strict_probe(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
        result = probe(*args, **kwargs)
        if result and int(result.get("verified_job_count") or 0) > 0:
            return result
        return None

    return strict_probe


# Greenhouse exposes board metadata, so a matching board name is sufficient
# even when it temporarily has no openings. Other providers either return a
# wildcard empty response for unknown slugs or lack trustworthy empty-board
# identity metadata, so they must show at least one real posting.
discovery.PROBES = [
    (provider, probe if provider == "greenhouse" else require_observed_jobs(probe))
    for provider, probe in discovery.PROBES
]


if __name__ == "__main__":
    raise SystemExit(discovery.main())
