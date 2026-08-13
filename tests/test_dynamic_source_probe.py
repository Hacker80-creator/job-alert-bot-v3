from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import dynamic_source_probe as probe


class DynamicSourceProbeTests(unittest.TestCase):
    @patch("dynamic_source_probe.source_registry_v44.build_source_overrides")
    def test_override_sources_keeps_only_enabled_generic_pages(self, build: Mock) -> None:
        build.return_value = [
            {"name": "Generic", "url": "https://example/jobs", "ats": "direct_job_html"},
            {"name": "Structured", "url": "https://example/api", "ats": "jibe_api"},
            {
                "name": "Blocked", "url": "https://example/blocked",
                "ats": "direct_job_html", "enabled": False,
            },
        ]

        result = probe.override_sources(Path("catalog.txt"))

        self.assertEqual(["Generic"], [item["name"] for item in result])

    @patch("dynamic_source_probe.requests.get")
    def test_probe_extracts_provider_and_target_links(self, get: Mock) -> None:
        response = Mock()
        response.status_code = 200
        response.url = "https://example.com/careers"
        response.content = b"jobs"
        response.text = """
        <a href="https://jobs.lever.co/example/data-engineer-1">Data Engineer</a>
        <script type="application/ld+json">
          {"@type": "JobPosting", "title": "Data Engineer"}
        </script>
        """
        response.raise_for_status.return_value = None
        get.return_value = response

        result = probe.probe({
            "name": "Example",
            "source_url": "https://example.com/careers",
        })

        self.assertEqual("INSPECTED", result["status"])
        self.assertEqual(1, result["jobposting_count"])
        self.assertEqual(1, len(result["provider_urls"]))
        self.assertEqual(1, len(result["target_links"]))


if __name__ == "__main__":
    unittest.main()
