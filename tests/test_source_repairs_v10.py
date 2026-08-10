from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v10 as parsers


class SourceRepairV10Tests(unittest.TestCase):
    @patch("custom_source_parsers_v10.requests.get")
    def test_atlassian_listing_parser_maps_first_party_payload(self, get: Mock) -> None:
        response = Mock()
        response.json.return_value = [{
            "portalJobPost": {
                "portalUrl": "https://globalcareers-atlassian.icims.com/jobs/123/job"
            },
            "title": "Machine Learning Engineer",
            "locations": ["Bengaluru, India", "Remote - India"],
            "category": "Engineering",
            "overview": "<p>Build ML services.</p>",
            "responsibilities": "<p>Use Python.</p>",
            "qualifications": "<p>Two years of experience.</p>",
            "compensation": "Competitive",
        }]
        get.return_value = response

        jobs = parsers.parse_atlassian_listings({
            "name": "Atlassian",
            "url": "https://www.atlassian.com/endpoint/careers/listings",
            "wlb_score": 5,
        })

        self.assertEqual(1, len(jobs))
        self.assertEqual("Machine Learning Engineer", jobs[0].title)
        self.assertEqual("Bengaluru, India; Remote - India", jobs[0].location)
        self.assertEqual("Engineering", jobs[0].department)
        self.assertIn("Use Python", jobs[0].description)
        self.assertEqual("Competitive", jobs[0].salary_text)

    @patch("custom_source_parsers_v10.requests.get")
    def test_successfactors_parser_enriches_only_relevant_local_jobs(self, get: Mock) -> None:
        listing = Mock()
        listing.text = """
        <table><tbody>
          <tr class="data-row">
            <td class="colTitle"><span class="jobTitle hidden-phone">
              <a class="jobTitle-link" href="/job/Bengaluru-Data-Scientist/1/">Data Scientist</a>
            </span></td>
            <td class="colLocation"><span class="jobLocation">Bengaluru, India</span></td>
            <td class="colFacility"><span class="jobFacility">Data</span></td>
          </tr>
          <tr class="data-row">
            <td class="colTitle"><span class="jobTitle hidden-phone">
              <a class="jobTitle-link" href="/job/Remote-Account-Manager/2/">Account Manager</a>
            </span></td>
            <td class="colLocation"><span class="jobLocation">Remote, US</span></td>
            <td class="colFacility"><span class="jobFacility">Sales</span></td>
          </tr>
        </tbody></table>
        """
        detail = Mock()
        detail.text = '<div class="jobdescription"><p>Python and analytics.</p></div>'
        get.side_effect = [listing, detail]

        jobs = parsers.parse_successfactors_html({
            "name": "Chargebee",
            "url": "https://jobs.chargebee.com/search/?q=&locationsearch=",
            "wlb_score": 4,
        })

        self.assertEqual(2, len(jobs))
        self.assertEqual("Python and analytics.", jobs[0].description)
        self.assertEqual("", jobs[1].description)
        self.assertEqual(2, get.call_count)


if __name__ == "__main__":
    unittest.main()
