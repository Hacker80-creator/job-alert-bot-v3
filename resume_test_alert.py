"""Send one clearly labeled Discord preview from a non-main workflow branch."""
from __future__ import annotations

import os

import job_monitor as bot
from resume_tailor import generate_tailored_resume


def main() -> int:
    if not os.getenv("GEMINI_API_KEY", "").strip():
        print("ERROR: GEMINI_API_KEY repository secret is missing")
        return 2
    if not bot.DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL repository secret is missing")
        return 2

    job = bot.Job(
        company="Resume Integration Test",
        title="[TEST] Product Analyst — tailored resume preview",
        location="Bengaluru, India",
        url="https://github.com/Hacker80-creator/job-alert-bot-v3",
        source="Branch-only integration test — not a live vacancy",
        description=(
            "Analyze product performance and business trends using SQL, Python, "
            "Exploratory Data Analysis, Statistical Analysis and Power BI. Build "
            "dashboards, clean data and communicate insights. Exposure to AWS "
            "and Tableau is preferred."
        ),
        wlb_score=4,
        score=100,
        reasons=[
            "branch-only resume integration test",
            "validates Gemini, grounded DOCX generation and Discord upload",
            "does not scan jobs or update deduplication state",
        ],
        requisition_id="RESUME-TEST-001",
    )
    result = generate_tailored_resume(job, require_ai=True)
    print(
        f"Test resume generated | model={result.model} | "
        f"warnings={len(result.warnings)}"
    )
    if not bot.discord_post(job, result):
        print("ERROR: Discord rejected the resume test alert")
        return 1
    print("Resume integration test sent to Discord")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
