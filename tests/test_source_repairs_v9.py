from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

import custom_source_parsers_v3 as parsers
import job_monitor_entry_v9


class SourceRepairV9Tests(unittest.TestCase):
    def test_double_encoded_json_envelope_is_decoded(self) -> None:
        response = Mock()
        response.json.return_value = json.dumps({"code": 200, "data": {"data": []}})
        self.assertEqual([], parsers.decode_json_envelope(response)["data"]["data"])

    def test_repaired_sources_are_enabled(self) -> None:
        companies = {
            item["name"]: item for item in job_monitor_entry_v9.load_final_config()["companies"]
        }
        self.assertEqual("phenom", companies["GE Healthcare"]["ats"])
        self.assertEqual("expedia_html", companies["Expedia Group"]["ats"])
        self.assertEqual("zwayam_hardened", companies["Tavant Technologies"]["ats"])

    def test_expedia_path_location_is_normalized(self) -> None:
        location = parsers._expedia_location_from_path(
            "/job/data-scientist/bangalore-bangalore/R-123/"
        )
        self.assertEqual("bangalore bangalore, India", location)


if __name__ == "__main__":
    unittest.main()
