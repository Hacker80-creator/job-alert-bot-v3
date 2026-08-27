"""Strict title vocabulary shared by QA routing and ML-channel exclusion."""
from __future__ import annotations

import re


QA_ROLE_PHRASES = (
    "qa engineer",
    "quality assurance engineer",
    "qa analyst",
    "quality analyst",
    "software test engineer",
    "software tester",
    "test engineer",
    "testing engineer",
    "manual tester",
    "manual test engineer",
    "functional tester",
    "functional test engineer",
    "automation test engineer",
    "automation tester",
    "qa automation engineer",
    "test automation engineer",
    "sdet",
    "software engineer in test",
    "software development engineer in test",
    "api tester",
    "api test engineer",
    "performance test engineer",
    "mobile test engineer",
    "validation engineer",
    "quality engineer",
    "associate qa engineer",
    "junior qa engineer",
    "qa trainee",
    "trainee test engineer",
    "graduate qa engineer",
    "graduate engineer trainee testing",
    "qa intern",
    "quality assurance intern",
    "software testing intern",
    "test engineer intern",
)

QA_SEARCH_TERMS = (
    "quality assurance",
    "QA engineer",
    "test engineer",
    "software tester",
    "test automation",
    "SDET",
)

QA_SKILL_TERMS = (
    "selenium",
    "playwright",
    "cypress",
    "appium",
    "rest assured",
    "postman",
    "jmeter",
    "jira",
    "api testing",
    "manual testing",
    "functional testing",
    "automation testing",
    "performance testing",
    "mobile testing",
    "regression testing",
    "smoke testing",
    "test cases",
    "test automation",
    "quality assurance",
)

SENIOR_QA_TITLE = re.compile(
    r"\b(?:senior|sr|staff|principal|lead|manager|director|architect|head|"
    r"vice president|vp|avp|svp)\b",
    re.IGNORECASE,
)


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def is_qa_title(title: str) -> bool:
    padded = f" {normalize_title(title)} "
    return any(f" {phrase} " in padded for phrase in QA_ROLE_PHRASES)


def is_senior_qa_title(title: str) -> bool:
    return bool(SENIOR_QA_TITLE.search(normalize_title(title)))
