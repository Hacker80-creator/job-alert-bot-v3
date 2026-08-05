from __future__ import annotations

import unittest

import job_match_expanded as expanded
import job_monitor as bot


SETTINGS = bot.load_config()["settings"]


def make_job(title: str, description: str) -> bot.Job:
    return bot.Job(
        company="Qualcomm",
        title=title,
        location="Bangalore, India",
        url="https://careers.qualcomm.com/example",
        source="Official careers: test",
        description=description,
        department="Engineering",
        wlb_score=4,
    )


class ExpandedMatchingTests(unittest.TestCase):
    def test_early_career_generic_ai_engineer_is_included(self) -> None:
        job = make_job(
            "Engineer - AI Orchestration (Windows)",
            "Ideal for an early-career engineer working on machine learning runtimes, "
            "generative AI workloads, Python tooling, and AI orchestration.",
        )
        score, reasons = expanded.expanded_score_job(job, SETTINGS)
        self.assertGreaterEqual(score, 70)
        self.assertTrue(any("adjacent engineer" in reason for reason in reasons))

    def test_unrelated_generic_engineer_is_rejected(self) -> None:
        job = make_job("Engineer", "Maintain electrical equipment and factory safety systems.")
        score, _ = expanded.expanded_score_job(job, SETTINGS)
        self.assertEqual(0, score)

    def test_senior_generic_engineer_is_rejected(self) -> None:
        job = make_job(
            "Senior Engineer - AI Platform",
            "Build machine learning and generative AI systems using Python and SQL.",
        )
        score, reasons = expanded.expanded_score_job(job, SETTINGS)
        self.assertEqual(0, score)
        self.assertTrue(any("blocked title" in reason for reason in reasons))

    def test_existing_precise_title_keeps_original_scoring(self) -> None:
        job = make_job("Data Analyst", "Use Python, SQL, Tableau and statistics.")
        self.assertEqual(
            bot.score_job(job, SETTINGS),
            expanded.expanded_score_job(job, SETTINGS),
        )


if __name__ == "__main__":
    unittest.main()
