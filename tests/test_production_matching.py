from __future__ import annotations

import unittest

import job_match_production as production
import job_monitor as bot


SETTINGS = bot.load_config()["settings"]


class ProductionMatchingTests(unittest.TestCase):
    def test_parenthesized_ten_year_requirement_is_rejected(self) -> None:
        job = bot.Job(
            company="Accenture",
            title="Natural Language Processing (NLP)-AI Platform Engineer",
            location="Bengaluru",
            url="https://www.accenture.com/example",
            source="Official careers: Accenture",
            description="Minimum 10+ year(s) of experience is required. Deep learning and NLP.",
            wlb_score=4,
        )
        score, reasons = production.production_score_job(job, SETTINGS)
        self.assertEqual(0, score)
        self.assertTrue(any("experience minimum too high" in reason for reason in reasons))

    def test_three_year_minimum_remains_eligible(self) -> None:
        job = bot.Job(
            company="Accenture",
            title="Custom Software Engineer",
            location="Bengaluru",
            url="https://www.accenture.com/example",
            source="Official careers: Accenture",
            description=(
                "Minimum 3 year(s) of experience. Build data engineering pipelines with "
                "Python, SQL, Spark, Airflow and machine learning teams."
            ),
            wlb_score=4,
        )
        score, _ = production.production_score_job(job, SETTINGS)
        self.assertGreaterEqual(score, 70)


if __name__ == "__main__":
    unittest.main()
