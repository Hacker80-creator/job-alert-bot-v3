from __future__ import annotations

import unittest
import json
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

    @patch("custom_source_parsers_v30.requests.Session")
    def test_peoplestrong_bootstraps_and_searches_public_portal(self, session_class: Mock) -> None:
        session = session_class.return_value
        session.get.return_value.raise_for_status.return_value = None
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": [{
            "requisitionId": 1830703,
            "jobCode": "HDE/JC/17482",
            "jobTitle": "Data Analyst",
            "jobDetailUrl": "https://hdfc.example/job/detail/HDE_JC_17482",
            "locationHierarchyComplete": "India>South>Karnataka>Bengaluru",
        }]}
        session.post.return_value = response

        jobs = parsers.parse_peoplestrong({
            "name": "HDFC ERGO",
            "url": "https://hdfc.example/api/cp/rest/altone/cp/jobs/v1?offset=0&limit=100",
            "bootstrap_url": "https://hdfc.example/api/cp/rest/altone/cp/urlinfo",
            "search_terms": ["data"],
        })

        self.assertEqual("Data Analyst", jobs[0].title)
        self.assertIn("Bengaluru", jobs[0].location)
        session.get.assert_called_once()
        self.assertEqual("data", session.post.call_args.kwargs["params"]["searchString"])

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

    @patch("custom_source_parsers_v30.requests.Session")
    def test_darwinbox_bootstraps_legacy_candidate_board(self, session_class: Mock) -> None:
        session = session_class.return_value
        session.get.return_value.raise_for_status.return_value = None
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": [{
            "id": "money-1",
            "designation_display_name": "Senior Data Analyst",
            "officelocation_show_arr": "Bengaluru",
            "internal_job_code": "MV-1",
        }]}
        session.post.return_value = response

        jobs = parsers.parse_darwinbox_v2({
            "name": "Moneyview",
            "url": "https://moneyview.darwinbox.in/ms/candidateapi/job/alljobs",
            "career_site_url": "https://moneyview.darwinbox.in/ms/candidate/careers",
            "company_id": "main",
            "bootstrap_required": True,
        })

        self.assertEqual("Senior Data Analyst", jobs[0].title)
        self.assertEqual("MV-1", jobs[0].requisition_id)
        session.get.assert_called_once()
        session.post.assert_called_once()

    @patch("custom_source_parsers_v30.requests.get")
    def test_icims_maps_server_rendered_job_card(self, get: Mock) -> None:
        first = Mock(text='''<ul class="iCIMS_JobsTable">
          <li class="iCIMS_JobCardItem"><div class="header left">
            <span class="sr-only">Location</span><span>IND-Bangalore</span></div>
            <div class="title"><a href="/jobs/3074/data-engineer/job?in_iframe=1">
              <h3>Data Engineer</h3></a></div>
            <div class="description">Build analytics pipelines.</div>
            <div class="iCIMS_JobHeaderTag"><dt>Category</dt><dd>Engineering</dd></div>
            <div class="iCIMS_JobHeaderTag"><dt>ID</dt><dd>2026-3074</dd></div>
          </li></ul>''', url="https://example.icims.com/jobs/search?pr=0")
        first.raise_for_status.return_value = None
        empty = Mock(text="<ul></ul>", url="https://example.icims.com/jobs/search?pr=1")
        empty.raise_for_status.return_value = None
        get.side_effect = [first, empty]

        jobs = parsers.parse_icims_html({
            "name": "Example",
            "url": "https://example.icims.com/jobs/search",
        })

        self.assertEqual("Data Engineer", jobs[0].title)
        self.assertEqual("IND-Bangalore", jobs[0].location)
        self.assertEqual("2026-3074", jobs[0].requisition_id)

    @patch("custom_source_parsers_v30.requests.get")
    def test_jobvite_maps_public_job_card(self, get: Mock) -> None:
        response = Mock(text='''<div class="jv-job-list"><a href="/simaai/job/o123">
          <div class="jv-job-list-name">MTS, Robotics Engineer (AI2443)</div>
          <div class="jv-job-list-location">Bengaluru, India</div>
        </a></div>''', url="https://jobs.jobvite.com/simaai/?nl=1")
        response.raise_for_status.return_value = None
        get.return_value = response

        jobs = parsers.parse_jobvite_html({
            "name": "SiMa.ai", "url": "https://jobs.jobvite.com/simaai/?nl=1",
        })

        self.assertEqual("MTS, Robotics Engineer (AI2443)", jobs[0].title)
        self.assertEqual("Bengaluru, India", jobs[0].location)
        self.assertEqual("AI2443", jobs[0].requisition_id)

    @patch("custom_source_parsers_v30.requests.get")
    def test_recruiterflow_maps_embedded_jobs_payload(self, get: Mock) -> None:
        payload = {"department": [["Engineering", [{
            "job_id": 662,
            "job_name": "Enterprise Security Engineer",
            "details": "Bengaluru",
            "apply_link": "coinswitch/jobs/662",
            "employment_type": "Full time",
        }]]]}
        response = Mock(
            text=f"<script>window.jobsList = {json.dumps(payload)};</script>",
            url="https://recruiterflow.com/coinswitch/jobs",
        )
        response.raise_for_status.return_value = None
        get.return_value = response

        jobs = parsers.parse_recruiterflow_html({
            "name": "CoinSwitch",
            "url": "https://recruiterflow.com/coinswitch/jobs",
        })

        self.assertEqual("Enterprise Security Engineer", jobs[0].title)
        self.assertEqual("Bengaluru", jobs[0].location)
        self.assertEqual("662", jobs[0].requisition_id)

    @patch("custom_source_parsers_v30.requests.get")
    def test_gnani_maps_first_party_job(self, get: Mock) -> None:
        response = Mock(
            url="https://careers.gnani.ai/api/jobs",
        )
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": {"jobs": [{
            "title": "Staff AI Engineer",
            "code": "Sta-Ben-2026-08-06-117",
            "department": "Engineering",
            "location": ["Bengaluru"],
            "minExperience": 7,
            "maxExperience": 12,
            "skills": ["Python", "Agentic AI"],
        }]}}
        get.return_value = response

        jobs = parsers.parse_gnani_api({
            "name": "Gnani.ai", "url": "https://careers.gnani.ai/api/jobs",
        })

        self.assertEqual("Staff AI Engineer", jobs[0].title)
        self.assertEqual("Bengaluru", jobs[0].location)
        self.assertEqual("Sta-Ben-2026-08-06-117", jobs[0].requisition_id)
        self.assertIn("/apply/Sta-Ben-2026-08-06-117", jobs[0].url)

    @patch("custom_source_parsers_v30.requests.Session")
    def test_hrone_maps_public_career_position(self, session_class: Mock) -> None:
        session = session_class.return_value
        listing = Mock(
            url=("https://career.hrone.cloud/career-portal?appId=public-key"
                 "&dc=addverb&rqt=request-token&cc=company-code")
        )
        listing.raise_for_status.return_value = None
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{
            "jobTitle": "Robotics Software Engineer",
            "positionId": 1152,
            "encryptedPositionId": "encrypted-position",
            "departmentCode": "department-code",
            "sourceType": "career-source",
            "preferredLocation": "Noida",
            "jobCode": "Addverb1135MPR",
            "seniorityName": "Mobile Robotics",
            "experienceFrom": 3,
            "experienceTo": 6,
        }]
        session.get.return_value = listing
        session.post.return_value = response

        jobs = parsers.parse_hrone_html({
            "name": "Addverb",
            "url": "https://app.hrone.cloud/api/external/referral/CareerPosition/Details",
            "career_site_url": "https://hr1.to/9c16d2",
        })

        self.assertEqual("Robotics Software Engineer", jobs[0].title)
        self.assertEqual("Noida", jobs[0].location)
        self.assertEqual("Addverb1135MPR", jobs[0].requisition_id)
        self.assertIn("pid=encrypted-position", jobs[0].url)

    @patch("custom_source_parsers_v30.requests.get")
    def test_evalueserve_maps_first_party_job_card(self, get: Mock) -> None:
        response = Mock(
            url="https://www.evalueserve.com/in-en/jobs/",
            text='''<div class="India">
              <div class="db-location-country"><h6>Bengaluru, India</h6></div>
              <div class="db-job-title"><h4>Senior Data Analyst</h4></div>
              <div class="db-busniess-unit"><h6>Analytics department</h6></div>
              <div class="db-experience-level"><h6>EXP: Mid-level</h6></div>
              <div class="db-job-link"><a href="https://lighthouse.darwinbox.com/ms/candidate/careers/a123">Learn More</a></div>
            </div>''',
        )
        response.raise_for_status.return_value = None
        get.return_value = response

        jobs = parsers.parse_evalueserve_html({
            "name": "Evalueserve",
            "url": "https://www.evalueserve.com/in-en/jobs/",
        })

        self.assertEqual("Senior Data Analyst", jobs[0].title)
        self.assertEqual("Bengaluru, India", jobs[0].location)
        self.assertEqual("a123", jobs[0].requisition_id)
        self.assertIn("Mid-level", jobs[0].description)

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

    @patch("custom_source_parsers_v30.requests.get")
    def test_wordpress_post_type_maps_stable_record(self, get: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{
            "id": 8737,
            "link": "https://career.example/job_opening/data-engineer/",
            "title": {"rendered": "Data Engineer"},
            "content": {"rendered": "<p>Build reliable pipelines.</p>"},
        }]
        get.return_value = response
        jobs = parsers.parse_wordpress_post_type({
            "name": "Molecular Connections",
            "url": "https://career.example/wp-json/wp/v2/job_opening",
        })
        self.assertEqual("Data Engineer", jobs[0].title)
        self.assertEqual("8737", jobs[0].requisition_id)
        self.assertEqual("Build reliable pipelines.", jobs[0].description)

    @patch("custom_source_parsers_v30.requests.get")
    def test_signalchip_maps_current_position_headings(self, get: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"content": {"rendered": '''
          <div class="sow-accordion-panel">
            <div class="sow-accordion-title">Communications Protocol Engineer</div>
            <div class="sow-accordion-panel-content">Build protocol stack software.</div>
          </div>
        '''}}]
        get.return_value = response
        jobs = parsers.parse_signalchip_wordpress({
            "name": "Signalchip",
            "url": "https://signalchip.example/wp-json/wp/v2/pages",
            "career_site_url": "https://signalchip.example/job-openings/",
        })
        self.assertEqual("Communications Protocol Engineer", jobs[0].title)
        self.assertEqual("communications-protocol-engineer", jobs[0].requisition_id)

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

    @patch("custom_source_parsers_v30.requests.get")
    def test_static_external_link_preserves_official_card_metadata(
        self, get: Mock
    ) -> None:
        response = Mock(
            url="https://example.com/careers/",
            text='''<div class="job-col">
              <p class="job-title">Machine Learning Intern</p>
              <div class="job-meta"><span>Bengaluru</span>
                <a href="https://www.linkedin.com/jobs/view/44123/">Apply Now</a>
              </div></div>''',
        )
        response.raise_for_status.return_value = None
        get.return_value = response
        jobs = parsers.parse_static_job_links({
            "name": "Example",
            "url": "https://example.com/careers/",
            "job_url_pattern": r"^https://www\.linkedin\.com/jobs/view/\d+/?$",
            "fetch_job_details": False,
            "location_pattern": r"\b(Bengaluru)\b",
            "source_label": "Official page: LinkedIn job",
        })
        self.assertEqual("Machine Learning Intern", jobs[0].title)
        self.assertEqual("Bengaluru", jobs[0].location)
        self.assertEqual("44123", jobs[0].requisition_id)
        self.assertEqual("Official page: LinkedIn job", jobs[0].source)
        get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
