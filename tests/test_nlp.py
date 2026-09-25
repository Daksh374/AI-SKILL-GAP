from datetime import date

import pytest

from backend.app.nlp.parser import ResumeParseError, clean_text, parse_resume
from backend.app.nlp.profile import build_profile
from backend.app.nlp.sections import detect_sections
from backend.app.nlp.skills import extract_skills, normalize_skills

TODAY = date(2026, 6, 30)


@pytest.mark.parametrize("variant", ["sklearn", "scikit learn", "scikit-learn", "Scikit-Learn", "SKLEARN"])
def test_normalization_variants_map_to_canonical(variant):
    assert normalize_skills([variant]) == ["Scikit-learn"]


def test_normalize_many_dedupes_and_drops_unknown():
    assert normalize_skills(["k8s", "Kubernetes", "postgres", "not-a-skill"]) == ["Kubernetes", "PostgreSQL"]


def test_longest_match_wins():
    skills = extract_skills("SKILLS\nText classification and model monitoring\n", use_ner=False).skills
    assert "Text Classification" in skills and "Classification" not in skills
    assert "Model Monitoring" in skills and "Monitoring" not in skills


def test_special_character_skills():
    skills = extract_skills("SKILLS\nC++, C#, Node.js, CI/CD, A/B testing\n", use_ner=False).skills
    assert {"C++", "C#", "Node.js", "CI/CD", "A/B Testing"} <= set(skills)
    assert "C" not in skills


def test_ambiguous_skill_only_trusted_in_skills_section():
    text = "SUMMARY\nI can Go anywhere and R&D is fun.\n\nSKILLS\nPython, SQL\n"
    skills = extract_skills(text, use_ner=False).skills
    assert "Go" not in skills and "R" not in skills
    text2 = "SKILLS\nPython, R, Go\n"
    assert {"R", "Go"} <= set(extract_skills(text2, use_ner=False).skills)


def test_skill_group_labels_and_degree_fields_are_not_claims():
    text = "SKILLS\nMachine Learning: sklearn, XGBoost\n\nEDUCATION\nM.S. in Statistics, Riverside State University, 2020\n"
    skills = extract_skills(text, use_ner=False).skills
    assert "Machine Learning" not in skills and "Statistics" not in skills
    assert {"Scikit-learn", "XGBoost"} <= set(skills)


def test_confidence_rewards_skills_section_and_usage():
    text = "SKILLS\nDocker\n\nEXPERIENCE\nEngineer | X | Jan 2020 - Jan 2021\n- Shipped services with Docker.\n\nPROJECTS\nUsed kubernetes once.\n"
    skills = extract_skills(text, use_ner=False).skills
    assert skills["Docker"].confidence > skills["Kubernetes"].confidence
    assert "skills" in skills["Docker"].sections and "experience" in skills["Docker"].sections


def test_section_detection(resume_text):
    s = detect_sections(clean_text(resume_text))
    for sec in ["summary", "skills", "experience", "projects", "education", "certifications"]:
        assert s.has(sec), sec
    assert any("Soft Skills" in ln for ln in s.lines["skills"])


def test_profile_extraction(resume_text):
    p = build_profile(clean_text(resume_text), use_ner=False, today=TODAY)
    assert p.name == "Jordan Rivera"
    assert p.email == "jordan.rivera@example.com"
    assert p.highest_education_level == "Bachelor"
    assert p.education[0].field_of_study == "Statistics"
    assert p.education[0].institution == "Lakeshore University"
    assert p.education[0].year == 2021
    # Mar 2022-Dec 2024 (33 months) + Jun-Dec 2021 (6 months) = 39 months
    assert p.total_experience_years == 3.2
    assert p.experience_source == "date_ranges"
    assert p.experience[0].title == "Data Analyst" and p.experience[0].company == "Northwind Retail"
    names = set(p.all_skill_names)
    assert {"Python", "Pandas", "NumPy", "Scikit-learn", "SQL", "PostgreSQL", "Tableau", "Excel", "R", "Git",
            "A/B Testing", "Communication", "Problem Solving", "PyTorch"} <= names
    assert {s.name for s in p.soft_skills} >= {"Communication", "Problem Solving"}
    assert p.projects[0].title == "Movie Recommender" and "PyTorch" in p.projects[0].skills
    assert p.certifications == ["Google Data Analytics Professional Certificate"]


def test_overlapping_date_ranges_are_merged():
    text = "EXPERIENCE\nA | X | Jan 2020 - Dec 2021\nB | Y | Jan 2021 - Dec 2021\nSKILLS\nPython\n"
    p = build_profile(text, use_ner=False, today=TODAY)
    assert p.total_experience_years == 1.9  # 23 months, not 34


def test_present_uses_reference_date():
    p = build_profile("EXPERIENCE\nDev | X | 01/2025 - Present\nSKILLS\nPython\n", use_ner=False, today=TODAY)
    assert p.total_experience_years == 1.4  # Jan 2025 -> Jun 2026 = 17 months


def test_stated_years_fallback():
    p = build_profile("SUMMARY\nEngineer with 7+ years of experience.\nSKILLS\nPython\n", use_ner=False, today=TODAY)
    assert p.total_experience_years == 7 and p.experience_source == "stated_years"


def test_parse_docx(resume_docx):
    doc = parse_resume("resume.docx", resume_docx)
    assert doc.file_type == "docx" and "Jordan Rivera" in doc.text


def test_parse_pdf(resume_pdf):
    doc = parse_resume("resume.pdf", resume_pdf)
    assert doc.file_type == "pdf" and "TECHNICAL SKILLS" in doc.text
    p = build_profile(doc.text, use_ner=False, today=TODAY)
    assert {"Python", "SQL", "Tableau"} <= set(p.all_skill_names)


@pytest.mark.parametrize("name,data,msg", [
    ("resume.txt", b"hello", "Unsupported file type"),
    ("resume.pdf", b"", "empty"),
    ("resume.pdf", b"not a pdf", "Could not read PDF"),
    ("resume.docx", b"not a docx", "Could not read DOCX"),
])
def test_parse_errors(name, data, msg):
    with pytest.raises(ResumeParseError, match=msg):
        parse_resume(name, data)


def test_clean_text_normalizes_bullets_and_hyphenation():
    out = clean_text("• Built  data-\npipelines\n\n\n\n▪ Item")
    assert out == "- Built datapipelines\n\n- Item"
