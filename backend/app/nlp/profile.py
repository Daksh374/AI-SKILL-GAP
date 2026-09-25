"""Structured candidate-profile extraction from cleaned resume text (rule-based + spaCy NER)."""
from __future__ import annotations

import re
from datetime import date

from backend.app.nlp.sections import Sections, classify_heading, detect_sections
from backend.app.nlp.skills import ExtractionResult, SkillMatch, extract_skills
from backend.app.nlp.spacy_loader import get_nlp
from backend.app.schemas import (
    CandidateProfile,
    EducationEntry,
    ExperienceEntry,
    ExtractedSkill,
    ProjectEntry,
)

# ------------------------------------------------------------------ regexes
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){1,3}\d{3,4}")
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = rf"(?:{_MONTH}\s*'?\d{{2,4}}|\d{{1,2}}/\d{{4}}|\d{{4}}-\d{{2}}|\d{{4}})"
_END = rf"(?:{_DATE}|present|current|now|till date|to date|ongoing)"
RANGE_RE = re.compile(rf"(?P<start>{_DATE})\s*(?:-|to|until)\s*(?P<end>{_END})", re.IGNORECASE)
STATED_YEARS_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+|industry\s+|work\s+|hands-on\s+)?experience", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19[6-9]\d|20[0-4]\d)\b")

DEGREE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PhD", re.compile(r"\bPh\.?\s?D\.?|\bDoctor of Philosophy\b|\bDoctorate\b", re.IGNORECASE)),
    ("Master", re.compile(r"\bM\.S\.?(?=[\s,]|$)|\bM\.Sc\.?|\bMSc\b|\bMaster(?:'s|s)?\b|\bM\.Tech\b|\bMTech\b|\bMBA\b|\bM\.B\.A\.?|\bM\.E\.|\bM\.Eng\b|\bMCA\b|\bM\.A\.(?=[\s,]|$)")),
    ("Bachelor", re.compile(r"\bB\.S\.?(?=[\s,]|$)|\bB\.Sc\.?|\bBSc\b|\bBachelor(?:'s|s)?\b|\bB\.Tech\b|\bBTech\b|\bB\.E\.|\bB\.Eng\b|\bBCA\b|\bB\.A\.(?=[\s,]|$)|\bBBA\b|\bUndergraduate\b")),
    ("Associate", re.compile(r"\bAssociate(?:'s)? Degree\b|\bDiploma\b|\bA\.A\.S\.?", re.IGNORECASE)),
]
LEVEL_ORDER = {"Unknown": 0, "Associate": 1, "Bachelor": 2, "Master": 3, "PhD": 4}
FIELD_RE = re.compile(r"\b(?:in|of)\s+([A-Z][A-Za-z&/,' -]+?)(?=\s*(?:,|\(|\||;|$|\bfrom\b|\bat\b|\d))")
INSTITUTION_RE = re.compile(
    r"([A-Z][\w.&'-]*(?:\s+[A-Z][\w.&'-]*)*\s+(?:University|College|Institute|School|Academy|Polytechnic)(?:\s+of\s+[A-Z][\w&'-]*(?:\s+[A-Z][\w&'-]*)*)?"
    r"|(?:University|Institute|College)\s+of\s+[A-Z][\w&'-]*(?:\s+[A-Z][\w&'-]*)*)"
)
CERT_PATTERNS = re.compile(
    r"(AWS Certified[^,;|\n]*|Microsoft Certified:?[^,;|\n]*|Google (?:Professional|Associate|Cloud)[^,;|\n]*"
    r"|Certified [A-Z][^,;|\n]*|CompTIA [A-Za-z+]+|\bCISSP\b|\bOSCP\b|\bPMP\b|[A-Z][\w.&-]*(?: [A-Z][\w.&-]*)* Professional Certificate"
    r"|TensorFlow Developer Certificate|HashiCorp Certified[^,;|\n]*)"
)
BULLET_PREFIX = re.compile(r"^-\s+")


def _month_index(token: str, is_end: bool, today: date) -> int | None:
    t = token.strip().lower().rstrip(".")
    if t in {"present", "current", "now", "till date", "to date", "ongoing"}:
        return today.year * 12 + today.month
    m = re.match(rf"({_MONTH})\s*'?(\d{{2,4}})", t, re.IGNORECASE)
    if m:
        month = MONTHS.get(m.group(1)[:3].lower())
        year = int(m.group(2))
        year = year + 2000 if year < 100 else year
        return year * 12 + month if month else None
    m = re.match(r"(\d{1,2})/(\d{4})", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(2)) * 12 + int(m.group(1))
    m = re.match(r"(\d{4})-(\d{2})", t)
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)) * 12 + int(m.group(2))
    m = re.match(r"(\d{4})$", t)
    if m:
        return int(m.group(1)) * 12 + 1
    return None


def _fmt_month(idx: int) -> str:
    y, m = divmod(idx - 1, 12)
    return f"{y:04d}-{m + 1:02d}"


def parse_experience(sections: Sections, text: str, today: date) -> tuple[list[ExperienceEntry], float, str]:
    """Return (entries, total_years, source). Overlapping date ranges are merged before summing."""
    source_text = sections.text("experience") if sections.has("experience") else "\n".join(
        ln for sec in sections.order if sec not in {"education", "certifications"} for ln in sections.lines.get(sec, [])
    )
    entries: list[ExperienceEntry] = []
    intervals: list[tuple[int, int]] = []
    for line in source_text.split("\n"):
        m = RANGE_RE.search(line)
        if not m:
            continue
        start = _month_index(m.group("start"), False, today)
        end = _month_index(m.group("end"), True, today)
        if start is None or end is None or end < start or start > today.year * 12 + today.month:
            continue
        is_present = m.group("end").strip().lower() in {"present", "current", "now", "till date", "to date", "ongoing"}
        rest = (line[: m.start()] + " " + line[m.end():]).strip(" |,-()")
        parts = [p.strip() for p in re.split(r"\s*\|\s*|\s+at\s+|\s*,\s*|\s+-\s+", rest) if p.strip()]
        entries.append(ExperienceEntry(
            title=parts[0] if parts else None,
            company=parts[1] if len(parts) > 1 else None,
            start=_fmt_month(start),
            end="Present" if is_present else _fmt_month(end),
            duration_months=end - start,
            raw=line.strip(),
        ))
        intervals.append((start, end))

    if intervals:
        intervals.sort()
        merged: list[list[int]] = [list(intervals[0])]
        for s, e in intervals[1:]:
            if s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        total_months = sum(e - s for s, e in merged)
        return entries, round(total_months / 12, 1), "date_ranges"

    stated = [float(x) for x in STATED_YEARS_RE.findall(text)]
    if stated:
        return entries, max(stated), "stated_years"
    return entries, 0.0, "none"


def parse_education(sections: Sections, text: str) -> list[EducationEntry]:
    lines = sections.lines.get("education") or [ln for ln in text.split("\n") if any(p.search(ln) for _, p in DEGREE_PATTERNS)]
    entries: list[EducationEntry] = []
    for line in lines:
        line = BULLET_PREFIX.sub("", line).strip()
        level, degree = "Unknown", None
        for lvl, pat in DEGREE_PATTERNS:
            m = pat.search(line)
            if m:
                level, degree = lvl, m.group(0).strip()
                break
        inst = INSTITUTION_RE.search(line)
        year_matches = YEAR_RE.findall(line)
        fields = FIELD_RE.findall(line)
        field_of_study = None
        for f in reversed(fields):  # "Master of Science in Statistics" -> prefer the last "in X"
            f = f.strip(" ,-")
            if f and f not in {"Science", "Arts", "Engineering", "Technology", "Philosophy"} and (not inst or f not in inst.group(0)):
                field_of_study = f
                break
        if level == "Unknown" and not inst:
            # continuation line (e.g. GPA, coursework) - attach to previous entry
            if entries and not entries[-1].year and year_matches:
                entries[-1].year = int(year_matches[-1])
            continue
        entries.append(EducationEntry(
            degree=degree, level=level, field_of_study=field_of_study,
            institution=inst.group(0).strip() if inst else None,
            year=int(year_matches[-1]) if year_matches else None, raw=line,
        ))
    return entries


def parse_projects(sections: Sections, extraction_lookup) -> list[ProjectEntry]:
    projects: list[ProjectEntry] = []
    for line in sections.lines.get("projects", []):
        is_bullet = bool(BULLET_PREFIX.match(line))
        content = BULLET_PREFIX.sub("", line).strip()
        if not is_bullet and ":" in content and len(content.split(":", 1)[0].split()) <= 8:
            title, desc = content.split(":", 1)
            projects.append(ProjectEntry(title=title.strip(), description=desc.strip()))
        elif not is_bullet or not projects:
            projects.append(ProjectEntry(title=content[:120], description=""))
        else:
            projects[-1].description = (projects[-1].description + " " + content).strip()
    for p in projects:
        p.skills = extraction_lookup(f"{p.title}\n{p.description}")
    return projects


def parse_certifications(sections: Sections, text: str) -> list[str]:
    certs: list[str] = []
    for line in sections.lines.get("certifications", []):
        c = BULLET_PREFIX.sub("", line).strip(" -•,;")
        if c and len(c) <= 150:
            certs.append(c)
    for m in CERT_PATTERNS.finditer(text):
        c = m.group(0).strip(" -•,;.")
        if not any(c.lower() in x.lower() or x.lower() in c.lower() for x in certs):
            certs.append(c)
    return list(dict.fromkeys(certs))


_NAME_TOKEN = re.compile(r"^[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'.-]*$")


def parse_name(sections: Sections, text: str, use_ner: bool) -> str | None:
    for line in sections.lines.get("header", [])[:5]:
        cand = line.split("|")[0].strip()
        tokens = cand.split()
        if 2 <= len(tokens) <= 4 and all(_NAME_TOKEN.match(t) for t in tokens) and not EMAIL_RE.search(cand) \
                and classify_heading(cand)[0] is None:
            return cand
    nlp = get_nlp() if use_ner else None
    if nlp is not None:
        for ent in nlp(text[:400]).ents:
            if ent.label_ == "PERSON" and 2 <= len(ent.text.split()) <= 4:
                return ent.text.strip()
    return None


def _to_schema(m: SkillMatch) -> ExtractedSkill:
    return ExtractedSkill(
        name=m.name, category=m.category, confidence=m.confidence, mentions=m.mentions,
        sections=m.sections, matched_forms=m.matched_forms, ner_supported=m.ner_supported,
    )


def build_profile(text: str, use_ner: bool = True, today: date | None = None) -> CandidateProfile:
    """Tool entrypoint: cleaned resume text -> structured CandidateProfile."""
    today = today or date.today()
    sections = detect_sections(text)
    extraction: ExtractionResult = extract_skills(text, sections, use_ner=use_ner)

    skills = sorted(extraction.skills.values(), key=lambda s: (-s.confidence, s.name))
    technical = [_to_schema(s) for s in skills if s.category != "Soft Skills"]
    soft = [_to_schema(s) for s in skills if s.category == "Soft Skills"]

    def skills_in(snippet: str) -> list[str]:
        return [n for n in extract_skills(snippet, use_ner=False).skills if n in extraction.skills]

    experience, years, exp_source = parse_experience(sections, text, today)
    education = parse_education(sections, text)
    highest = max((e.level for e in education), key=lambda lv: LEVEL_ORDER[lv], default="Unknown")

    email = EMAIL_RE.search(text)
    phone = None
    for m in PHONE_RE.finditer(sections.text("header") or text[:500]):
        digits = re.sub(r"\D", "", m.group(0))
        if 7 <= len(digits) <= 15 and not YEAR_RE.fullmatch(m.group(0).strip()):
            phone = m.group(0).strip()
            break

    warnings: list[str] = []
    if not sections.has("skills"):
        warnings.append("No Skills section detected; skills were extracted from the full text.")
    if exp_source == "none":
        warnings.append("No employment date ranges or stated years of experience found.")
    if use_ner and get_nlp() is None:
        warnings.append("spaCy model not installed; NER-based signals were skipped.")

    summary = sections.text("summary") or None
    return CandidateProfile(
        name=parse_name(sections, text, use_ner),
        email=email.group(0) if email else None,
        phone=phone,
        summary=summary[:1000] if summary else None,
        technical_skills=technical,
        soft_skills=soft,
        unrecognized_terms=extraction.unrecognized_terms,
        education=education,
        highest_education_level=highest,
        experience=experience,
        total_experience_years=years,
        experience_source=exp_source,
        projects=parse_projects(sections, skills_in),
        certifications=parse_certifications(sections, text),
        sections_detected=[s for s in sections.order if s != "header" and sections.has(s)],
        word_count=len(text.split()),
        warnings=warnings,
    )
