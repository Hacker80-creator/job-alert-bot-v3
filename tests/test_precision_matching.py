from __future__ import annotations

import unittest

import job_match_precision as precision
import job_monitor as bot


SETTINGS = bot.load_config()["settings"]


def make_job(title: str, description: str, location: str = "Bengaluru, India") -> bot.Job:
    return bot.Job(
        company="Test Company",
        title=title,
        location=location,
        url="https://example.com/job",
        source="Official careers: test",
        description=description,
        wlb_score=4,
    )


class PrecisionMatchingTests(unittest.TestCase):
    def assert_rejected(self, title: str, description: str, location: str = "Bengaluru") -> None:
        score, _ = precision.precision_score_job(make_job(title, description, location), SETTINGS)
        self.assertEqual(0, score)

    def test_keeps_ai_orchestration_engineer(self) -> None:
        job = make_job(
            "Engineer - AI Orchestration (Windows)",
            "Early-career work on machine learning runtimes and generative AI using Python and SQL.",
        )
        score, _ = precision.precision_score_job(job, SETTINGS)
        self.assertGreaterEqual(score, 70)

    def test_keeps_generic_title_with_strong_data_engineering_stack(self) -> None:
        job = make_job(
            "Custom Software Engineer",
            "Build data engineering pipelines with Python, SQL, Spark and Airflow. Minimum 3 years.",
        )
        score, reasons = precision.precision_score_job(job, SETTINGS)
        self.assertGreaterEqual(score, 70)
        self.assertTrue(any("strict profile-overlap" in reason for reason in reasons))

    def test_rejects_support_and_customer_roles(self) -> None:
        body = "Machine learning and AI platform support using Python and SQL for associates."
        self.assert_rejected("Technical Support Engineer 2", body, "Remote - India")
        self.assert_rejected("Customer Engineer", body, "Remote - India")

    def test_rejects_full_stack_ai_role(self) -> None:
        self.assert_rejected(
            "Full Stack Developer (AI Agents)",
            "Build LLM applications with Python, React and Databricks.",
        )

    def test_rejects_generic_cplusplus_engineer_with_ai_mention(self) -> None:
        self.assert_rejected(
            "Engineer",
            "Linux C++ drivers for machine learning inference; some Python tooling.",
        )

    def test_rejects_role_described_as_senior(self) -> None:
        self.assert_rejected(
            "Associate Engineer",
            "We are seeking a Senior Engineer for machine learning DevOps using Python and SQL.",
        )

    def test_rejects_title_explicitly_based_in_mumbai(self) -> None:
        self.assert_rejected(
            "Customer Engineer, India (Based in Mumbai)",
            "Generative AI, LLM and Python work.",
            "Remote India",
        )


if __name__ == "__main__":
    unittest.main()
