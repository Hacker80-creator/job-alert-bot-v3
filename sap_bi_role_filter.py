"""Strict role vocabulary for the independent SAP/BI alert channel."""
from __future__ import annotations

import re


SAP_BI_ROLE_PHRASES = (
    "sap ui5 developer",
    "sapui5 developer",
    "sap fiori developer",
    "sap ui5 fiori developer",
    "sap ui5 fiori consultant",
    "junior sap ui5 developer",
    "junior sap fiori developer",
    "associate sap developer",
    "sap btp developer",
    "junior sap btp developer",
    "sap btp extension developer",
    "sap cap developer",
    "sap odata developer",
    "sap frontend developer",
    "sap technical consultant",
    "junior sap technical consultant",
    "sap application developer",
    "sap application support",
    "sap ui5 support",
    "sap fiori support",
    "sap ui5 fiori support",
    "sap abap ui5 developer",
    "sap abap fiori developer",
    "power bi developer",
    "junior power bi developer",
    "associate power bi developer",
    "power bi analyst",
    "power bi consultant",
    "power bi report developer",
    "power bi dashboard developer",
    "business intelligence developer",
    "junior bi developer",
    "associate bi developer",
    "bi analyst",
    "business intelligence analyst",
    "bi reporting analyst",
    "data analyst",
    "junior data analyst",
    "associate data analyst",
    "reporting analyst",
    "data reporting analyst",
    "mis analyst",
    "mis executive",
    "sql developer",
    "junior sql developer",
    "sql analyst",
    "sql reporting analyst",
    "database reporting analyst",
    "dashboard developer",
    "data visualization developer",
    "data visualization analyst",
    "business data analyst",
    "junior business analyst",
    "associate business analyst",
    "application support analyst",
    "technical support analyst",
    "application support engineer",
    "production support analyst",
    "junior python developer",
    "python data analyst",
    "junior data engineer",
    "associate data engineer",
)

SAP_BI_SEARCH_TERMS = (
    "SAP UI5",
    "SAP Fiori",
    "SAP BTP",
    "Power BI",
    "business intelligence",
    "data analyst",
    "SQL developer",
    "application support",
)

SAP_BI_SKILL_TERMS = (
    "sap ui5",
    "sapui5",
    "sap fiori",
    "sap btp",
    "sap cap",
    "odata",
    "abap",
    "javascript",
    "typescript",
    "power bi",
    "dax",
    "power query",
    "business intelligence",
    "sql",
    "excel",
    "reporting",
    "dashboard",
    "data visualization",
    "etl",
    "python",
    "application support",
    "production support",
    "incident management",
)

SENIOR_SAP_BI_TITLE = re.compile(
    r"\b(?:senior|sr|staff|principal|lead|manager|director|architect|head|"
    r"vice president|vp|avp|svp)\b",
    re.IGNORECASE,
)


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def matched_sap_bi_role(title: str) -> str:
    """Return the most-specific approved role phrase found in a title."""
    padded = f" {normalize_title(title)} "
    return next(
        (
            phrase
            for phrase in sorted(SAP_BI_ROLE_PHRASES, key=len, reverse=True)
            if f" {phrase} " in padded
        ),
        "",
    )


def is_sap_bi_title(title: str) -> bool:
    return bool(matched_sap_bi_role(title))


def is_senior_sap_bi_title(title: str) -> bool:
    return bool(SENIOR_SAP_BI_TITLE.search(normalize_title(title)))
