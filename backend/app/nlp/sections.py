"""Rule-based resume section detection."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SECTION_HEADINGS: dict[str, list[str]] = {
    "summary": ["summary", "professional summary", "profile", "professional profile", "objective", "career objective",
                "about me", "about", "career summary", "executive summary"],
    "skills": ["skills", "technical skills", "core skills", "key skills", "skills & tools", "skills and tools",
               "core competencies", "competencies", "technologies", "tech stack", "tools", "tools & technologies",
               "skill set", "skillset", "areas of expertise", "expertise", "soft skills"],
    "experience": ["experience", "work experience", "professional experience", "employment history", "work history",
                   "employment", "internships", "internship", "relevant experience", "career history"],
    "education": ["education", "academic background", "academics", "educational background", "qualifications",
                  "academic qualifications", "education & training"],
    "projects": ["projects", "selected projects", "academic projects", "personal projects", "key projects",
                 "project experience", "side projects", "notable projects"],
    "certifications": ["certifications", "licenses & certifications", "licenses and certifications", "certificates",
                       "courses & certifications", "certifications & training", "training", "courses", "certification"],
    "other": ["awards", "achievements", "honors", "publications", "languages", "interests", "hobbies",
              "volunteer", "volunteering", "references", "activities", "leadership & activities"],
}

_HEADING_LOOKUP = {h: sec for sec, heads in SECTION_HEADINGS.items() for h in heads}
_NORMALIZE = re.compile(r"[^a-z& ]+")


def _normalize_heading(line: str) -> str:
    return _NORMALIZE.sub("", line.lower().replace(" and ", " & ")).strip()


@dataclass
class Sections:
    """Maps section name -> list of content lines. `header` holds lines before the first heading."""

    lines: dict[str, list[str]] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    # (section, line_index_in_full_text) so other components can map spans to sections
    line_sections: list[str] = field(default_factory=list)

    def text(self, section: str) -> str:
        return "\n".join(self.lines.get(section, []))

    def has(self, section: str) -> bool:
        return bool(self.lines.get(section))


def classify_heading(line: str) -> tuple[str | None, str]:
    """Return (section, trailing_content) if the line is a heading, else (None, "")."""
    stripped = line.strip().strip("-:|").strip()
    if not stripped or len(stripped) > 60:
        return None, ""
    # "Skills: Python, SQL" — heading with inline content
    m = re.match(r"^([A-Za-z &/]+?)\s*:\s*(.+)$", stripped)
    if m:
        key = _normalize_heading(m.group(1))
        if key in _HEADING_LOOKUP and _HEADING_LOOKUP[key] in {"skills", "certifications", "summary"}:
            return _HEADING_LOOKUP[key], m.group(2)
        return None, ""
    if len(stripped.split()) > 5:
        return None, ""
    key = _normalize_heading(stripped)
    return (_HEADING_LOOKUP[key], "") if key in _HEADING_LOOKUP else (None, "")


def detect_sections(text: str) -> Sections:
    sections = Sections()
    current = "header"
    sections.lines[current] = []
    sections.order.append(current)
    for line in text.split("\n"):
        sec, trailing = classify_heading(line)
        # "Soft Skills: ..." inside a skills block stays in skills
        if sec is not None and not (sec == "skills" and current == "skills" and trailing):
            current = sec
            if current not in sections.lines:
                sections.lines[current] = []
                sections.order.append(current)
            sections.line_sections.append(current)
            if trailing:
                sections.lines[current].append(trailing)
            continue
        sections.line_sections.append(current)
        if line.strip():
            sections.lines[current].append(line)
    return sections
