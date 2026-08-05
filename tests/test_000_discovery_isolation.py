"""Keep discovery merge unit tests independent of the production registry."""
from __future__ import annotations

import unittest
from pathlib import Path

import source_discovery


# unittest discovers files in sorted order. Point discovery tests at a missing
# registry so merge fixtures do not silently inherit production companies.
source_discovery.DISCOVERED_FILE = Path("__unit_test_no_discovered_sources__.yaml")


class DiscoveryTestIsolation(unittest.TestCase):
    def test_registry_override_is_test_only(self) -> None:
        self.assertFalse(source_discovery.DISCOVERED_FILE.exists())


if __name__ == "__main__":
    unittest.main()
