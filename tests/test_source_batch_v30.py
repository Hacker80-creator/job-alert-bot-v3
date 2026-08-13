from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import custom_source_parsers_v30 as parsers


class SourceBatchV30Tests(unittest.TestCase):
    @patch("custom_source_parsers_v30.requests.get")
    def test_dassault_maps_xml_card(self, get: Mock) -> None:
        response = Mock(content=b'''<Answer><Hits><Hit>
          <Meta name="card_id"><MetaString name="JOB-42" /></Meta>
          <Meta name="content_lang"><MetaString name="en" /></Meta>
          <Meta name="content_title"><MetaString name="Data Engineer" /></Meta>
          <Meta name="content_info_2_value"><MetaString name="Bengaluru" /></Meta>
          <Meta name="content_cta_1_url"><MetaString name="https://3ds.example/JOB-42" /></Meta>
          <Meta name="content_summary"><MetaString name="Build analytics" /></Meta>
        </Hit></Hits></Answer>''')
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_dassault_xml({
            "name": "Dassault Systèmes", "url": "https://3ds.example/api",
            "search_terms": ["data"], "max_pages_per_term": 1,
        })
        self.assertEqual("Data Engineer", jobs[0].title)
        self.assertEqual("Bengaluru", jobs[0].location)
        self.assertEqual("JOB-42", jobs[0].requisition_id)

    @patch("custom_source_parsers_v30.requests.post")
    def test_peoplestrong_maps_public_requisition(self, post: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": [{
            "requisitionId": 1818950,
            "jobTitle": "Lead AI Engineer",
            "jobDetailUrl": "https://mathco.example/job/MCP_LAE_1818950",
            "locationHierarchyComplete": "India>India>India",
            "organizationUnit": "MathCo India",
        }]}
        post.return_value = response
        jobs = parsers.parse_peoplestrong({
            "name": "TheMathCompany", "url": "https://mathco.example/api",
        })
        self.assertEqual("Lead AI Engineer", jobs[0].title)
        self.assertEqual("1818950", jobs[0].requisition_id)

    @patch("custom_source_parsers_v30.requests.post")
    def test_darwinbox_maps_stable_job_code(self, post: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": [{
            "id": "abc123",
            "title": "Data Analyst",
            "locations": "Bengaluru, India",
            "department_name": "Analytics",
            "internal_job_code": "JOB_1072",
        }]}
        post.return_value = response
        jobs = parsers.parse_darwinbox_v2({
            "name": "Tessolve",
            "url": "https://tessolve.example/ms/candidateapi/job/alljobs",
            "career_site_url": (
                "https://tessolve.example/ms/candidatev2/main/careers/allJobs"
            ),
            "company_id": "main",
        })
        self.assertEqual("Data Analyst", jobs[0].title)
        self.assertEqual("JOB_1072", jobs[0].requisition_id)
        self.assertIn("jobDetails/abc123", jobs[0].url)

    @patch("custom_source_parsers_v30.requests.get")
    def test_tonbo_maps_actively_hiring_heading(self, get: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"content": {"rendered": '''
          [vc_tta_section title=&#8221;Vision &amp; Deep Learning Engineer |
          Actively Hiring |&#8221; tab_id=&#8221;role-1&#8221;]
          <p>Build computer vision systems.</p>[/vc_tta_section]
        '''}}
        get.return_value = response
        jobs = parsers.parse_tonbo_html({
            "name": "Tonbo Imaging", "url": "https://tonbo.example/careers",
            "career_site_url": "https://tonbo.example/careers",
        })
        self.assertEqual("Vision & Deep Learning Engineer", jobs[0].title)
        self.assertEqual("Bengaluru, India", jobs[0].location)

    @patch("custom_source_parsers_v30.requests.get")
    def test_kaleideo_maps_wordpress_role_card(self, get: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"content": {"rendered": '''
          <a href="https://kaleideo.example/careers-at-kaleideo/image-processing-scientist/">
            <h2>Image Processing Scientist</h2>
            <p>Develop satellite image-processing pipelines.</p>
          </a>
        '''}}]
        get.return_value = response
        jobs = parsers.parse_kaleideo_wordpress({
            "name": "KaleidEO",
            "url": "https://kaleideo.example/wp-json/wp/v2/pages",
            "career_site_url": "https://kaleideo.example/careers-at-kaleideo/",
        })
        self.assertEqual("Image Processing Scientist", jobs[0].title)
        self.assertEqual("image-processing-scientist", jobs[0].requisition_id)
        self.assertEqual("Bengaluru, India", jobs[0].location)

    @patch("custom_source_parsers_v30.requests.post")
    def test_lululemon_maps_avature_detail(self, post: Mock) -> None:
        response = Mock(
            url="https://careers.lululemon.example/SearchCareer",
            text='''<div><a href="/en_US/careers/JobDetail/Data-Engineer/62394">
              Data Engineer</a><span>Bengaluru, India</span></div>''',
        )
        response.raise_for_status.return_value = None
        post.return_value = response
        jobs = parsers.parse_lululemon_avature({
            "name": "lululemon",
            "url": "https://careers.lululemon.example/SearchCareer",
            "search_terms": ["data"],
        })
        self.assertEqual("Data Engineer", jobs[0].title)
        self.assertEqual("62394", jobs[0].requisition_id)

    @patch("custom_source_parsers_v30.requests.get")
    def test_ameriprise_maps_server_rendered_card(self, get: Mock) -> None:
        response = Mock(
            url="https://careers.ameriprise.example/search-jobs?k=data&p=1",
            text='''<div class="card-job"><h2><a class="js-view-job"
              href="/search-jobs/r26_2784/senior-business-data-analyst/">
              Senior Business Data Analyst</a></h2>
              <div class="card-job-actions" data-id="r26_2784"></div>
              <ul class="job-meta"><li class="list-inline-item">Gurugram</li>
              <li class="list-inline-item">Data</li>
              <li class="list-inline-item">Ameriprise India</li></ul></div>''',
        )
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_ameriprise_html({
            "name": "Ameriprise Financial",
            "url": "https://careers.ameriprise.example/search-jobs",
            "search_terms": ["data"],
            "max_pages_per_term": 1,
        })
        self.assertEqual("Senior Business Data Analyst", jobs[0].title)
        self.assertEqual("Gurugram", jobs[0].location)
        self.assertEqual("r26_2784", jobs[0].requisition_id)


if __name__ == "__main__":
    unittest.main()
