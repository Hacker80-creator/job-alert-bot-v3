from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v27 as parsers


class SourceBatchV28Tests(unittest.TestCase):
    @patch("custom_source_parsers_v27.requests.get")
    def test_rupeek_uses_curated_linkedin_id(self, get: Mock) -> None:
        response = Mock(text='''<a href="https://www.linkedin.com/jobs/view/data-analyst-at-rupeek-4442607939">
        Data Analyst Location: Bengaluru, Karnataka, India 2 hours ago</a>''')
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_rupeek_official({"name": "Rupeek", "url": "https://rupeek.com/about/careers"})
        self.assertEqual("4442607939", jobs[0].requisition_id)
        self.assertEqual("Bengaluru, Karnataka, India", jobs[0].location)

    @patch("custom_source_parsers_v27.requests.get")
    def test_times_internet_maps_card_fields(self, get: Mock) -> None:
        listing = Mock(text='''<a href="/careers/job-detail/abc123">Data Analyst LOCATION: Bengaluru BUSINESS: Analytics EXPERIENCE: 2 - 4 Years</a>''')
        listing.raise_for_status.return_value = None
        detail = Mock(text="<main>Analyze customer data</main>")
        detail.raise_for_status.return_value = None
        get.side_effect = [listing, detail]
        jobs = parsers.parse_times_internet({"name": "Times Internet", "url": "https://timesinternet.in/careers/job-list"})
        self.assertEqual("Data Analyst", jobs[0].title)
        self.assertEqual("Bengaluru", jobs[0].location)
        self.assertEqual("abc123", jobs[0].requisition_id)


if __name__ == "__main__":
    unittest.main()
