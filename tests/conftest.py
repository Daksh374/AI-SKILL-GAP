"""Test configuration: isolated SQLite DB, no Tavily key, and resume fixtures built at runtime."""
from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="career_engine_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["TAVILY_API_KEY"] = ""
os.environ["SECRET_KEY"] = "test-secret"

from backend.app.db.database import init_db  # noqa: E402

init_db()

SAMPLE_RESUME = """Jordan Rivera
jordan.rivera@example.com | +1 415 555 0199 | San Francisco, CA

SUMMARY
Data analyst with 3 years of experience turning messy data into decisions.

TECHNICAL SKILLS
Python (pandas, numpy, sklearn), SQL, PostgreSQL, Tableau, Excel, R, git, statistics, A/B testing
Soft Skills: communication, problem-solving

EXPERIENCE
Data Analyst | Northwind Retail | Mar 2022 - Dec 2024
- Built weekly dashboards in Tableau and automated SQL reports for finance stakeholders.
- Ran hypothesis testing for pricing experiments and trained a churn model with scikit-learn.
Analytics Intern | Blue Co | Jun 2021 - Dec 2021
- Cleaned survey data with pandas.

PROJECTS
Movie Recommender: collaborative filtering with Python and PyTorch.

EDUCATION
B.S. in Statistics, Lakeshore University, 2021

CERTIFICATIONS
- Google Data Analytics Professional Certificate
"""


@pytest.fixture
def resume_text() -> str:
    return SAMPLE_RESUME


@pytest.fixture
def resume_docx() -> bytes:
    import docx

    d = docx.Document()
    for line in SAMPLE_RESUME.split("\n"):
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


@pytest.fixture
def resume_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 560, 800), SAMPLE_RESUME, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data
