from __future__ import annotations

import unittest

import job_match_resume as resume
import job_monitor as bot


SETTINGS = bot.load_config()["settings"]


def make_job(title: str, description: str, location: str = "Bengaluru, India") -> bot.Job:
    return bot.Job(
        company="Resume Match Test",
        title=title,
        location=location,
        url="https://example.test/job",
        source="Official careers: test",
        description=description,
        department="Engineering",
        wlb_score=4,
    )


class ResumeMatchingTests(unittest.TestCase):
    def assert_match(self, title: str, description: str, location: str = "Bengaluru") -> None:
        score, reasons = resume.resume_score_job(
            make_job(title, description, location), SETTINGS
        )
        self.assertGreaterEqual(score, 70, reasons)

    def assert_rejected(self, title: str, description: str, location: str = "Bengaluru") -> None:
        score, _ = resume.resume_score_job(
            make_job(title, description, location), SETTINGS
        )
        self.assertEqual(0, score)

    def test_accepts_early_career_devops_engineer(self) -> None:
        self.assert_match(
            "DevOps Engineer",
            "Build CI/CD and deployment pipelines using Jenkins, Docker, Linux, "
            "Python, Ansible and Git for containerized services.",
        )

    def test_accepts_plain_engineer_only_with_strong_resume_overlap(self) -> None:
        self.assert_match(
            "Engineer",
            "Early career role with 1+ year experience. Own CI/CD, deployment "
            "automation and containerization using Jenkins, Groovy, Docker, "
            "Linux, Python, Ansible and Git.",
        )

    def test_accepts_compute_operations_role_matching_current_experience(self) -> None:
        self.assert_match(
            "Engineering Compute Operations Engineer",
            "Operate engineering compute infrastructure and Linux systems. "
            "Use GitHub and Power BI to track compute and storage utilization.",
        )

    def test_accepts_data_engineer_with_profile_stack(self) -> None:
        self.assert_match(
            "Data Engineer",
            "Build data pipelines and ETL workflows with Python, SQL, Spark and Airflow.",
        )

    def test_rejects_qualcomm_embedded_cpp_engineer(self) -> None:
        self.assert_rejected(
            "Engineer",
            "Linux C++ drivers for machine learning inference on embedded RTOS. "
            "Some Python and Git tooling.",
        )

    def test_rejects_senior_platform_role(self) -> None:
        self.assert_rejected(
            "Senior DevOps Engineer",
            "Jenkins, Docker, Linux, Python, Ansible and CI/CD.",
        )

    def test_rejects_adjacent_role_requiring_three_plus_years(self) -> None:
        self.assert_rejected(
            "DevOps Engineer II",
            "Bring 3+ years of experience in DevOps. Work with Jenkins, Docker, "
            "Linux, Python, Ansible and CI/CD cloud infrastructure.",
        )

    def test_rejects_support_role_even_with_matching_tools(self) -> None:
        self.assert_rejected(
            "Technical Support Engineer",
            "Support Jenkins, Docker, Linux, Python and CI/CD systems.",
        )

    def test_rejects_foreign_remote_role(self) -> None:
        self.assert_rejected(
            "Platform Engineer",
            "Jenkins, Docker, Linux, Python, Ansible and CI/CD.",
            "Remote, United States",
        )

    def test_platform_salary_estimate_is_role_specific(self) -> None:
        estimate = bot.expected_salary(make_job("DevOps Engineer", ""))
        self.assertIn("7", estimate)
        self.assertIn("16", estimate)


if __name__ == "__main__":
    unittest.main()
