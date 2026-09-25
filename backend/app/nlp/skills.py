"""Deterministic skill extraction + normalization.

Pipeline:
  1. Surface-form matching against the taxonomy (canonical names + aliases) with a single
     compiled alternation per case mode, longest form first, non-overlapping.
  2. Normalization: every surface form maps to exactly one canonical skill name
     ("sklearn" / "scikit learn" / "scikit-learn" -> "Scikit-learn").
  3. Ambiguous names ("R", "Go", "C", "Excel") are matched case-sensitively and are only trusted
     inside a Skills section.
  4. spaCy NER: entity spans overlapping a match add a small confidence boost; entities inside
     the Skills section that do not match the taxonomy are reported as `unrecognized_terms`
     (never silently turned into skills).
  5. Confidence is a transparent heuristic (NOT a probability): see `_confidence`.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from functools import lru_cache

from backend.app.knowledge import KnowledgeBase, get_kb
from backend.app.nlp.sections import Sections, detect_sections
from backend.app.nlp.spacy_loader import get_nlp

_LEFT = r"(?<![\w.+#-])"
_RIGHT = r"(?![\w+#&]|\.[A-Za-z0-9])"
NER_LABELS = {"ORG", "PRODUCT", "WORK_OF_ART", "LANGUAGE", "NORP", "GPE", "PERSON", "FAC"}


@dataclass
class SkillMatch:
    name: str
    category: str
    confidence: float
    mentions: int
    sections: list[str]
    matched_forms: list[str]
    ner_supported: bool = False


@dataclass
class ExtractionResult:
    skills: dict[str, SkillMatch] = field(default_factory=dict)
    unrecognized_terms: list[str] = field(default_factory=list)


class SkillExtractor:
    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb
        ci_forms: dict[str, str] = {}
        cs_forms: dict[str, str] = {}
        for s in kb.skills.values():
            (cs_forms if s.ambiguous else ci_forms)[s.name if s.ambiguous else s.name.lower()] = s.name
            for a in s.aliases:
                ci_forms[a.lower()] = s.name
            for a in s.case_sensitive_aliases:
                cs_forms[a] = s.name
        self._ci_lookup = ci_forms
        self._cs_lookup = cs_forms
        self._ci_re = self._compile(ci_forms, re.IGNORECASE)
        self._cs_re = self._compile(cs_forms, 0)
        self.ambiguous = {s.name for s in kb.skills.values() if s.ambiguous}

    @staticmethod
    def _compile(forms: dict[str, str], flags: int) -> re.Pattern[str]:
        ordered = sorted(forms, key=len, reverse=True)
        return re.compile(_LEFT + "(" + "|".join(re.escape(f) for f in ordered) + ")" + _RIGHT, flags)

    # ------------------------------------------------------------------ normalization
    def normalize(self, term: str) -> str | None:
        """Map any surface form to its canonical skill name (None if not in taxonomy)."""
        t = term.strip()
        if t in self._cs_lookup:
            return self._cs_lookup[t]
        return self._ci_lookup.get(t.lower())

    def normalize_many(self, terms: list[str]) -> list[str]:
        out: list[str] = []
        for t in terms:
            n = self.normalize(t)
            if n and n not in out:
                out.append(n)
        return out

    # ------------------------------------------------------------------ extraction
    def _spans(self, text: str) -> list[tuple[int, int, str, str]]:
        """All non-overlapping (start, end, surface, canonical) matches, longest-first on conflicts."""
        cands: list[tuple[int, int, str, str]] = []
        for m in self._ci_re.finditer(text):
            cands.append((m.start(), m.end(), m.group(1), self._ci_lookup[m.group(1).lower()]))
        for m in self._cs_re.finditer(text):
            cands.append((m.start(), m.end(), m.group(1), self._cs_lookup[m.group(1)]))
        cands.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
        taken: list[tuple[int, int]] = []
        kept: list[tuple[int, int, str, str]] = []
        for c in cands:
            if any(c[0] < e and s < c[1] for s, e in taken):
                continue
            taken.append((c[0], c[1]))
            kept.append(c)
        kept.sort()
        return kept

    def extract(self, text: str, sections: Sections | None = None, use_ner: bool = True) -> ExtractionResult:
        sections = sections or detect_sections(text)
        lines = text.split("\n")
        line_starts: list[int] = []
        pos = 0
        for ln in lines:
            line_starts.append(pos)
            pos += len(ln) + 1

        def section_at(offset: int) -> str:
            idx = bisect.bisect_right(line_starts, offset) - 1
            return sections.line_sections[idx] if 0 <= idx < len(sections.line_sections) else "header"

        has_skills_section = sections.has("skills")
        hits: dict[str, dict] = {}
        for start, end, surface, canonical in self._spans(_mask_non_claims(lines, sections)):
            sec = section_at(start)
            h = hits.setdefault(canonical, {"mentions": 0, "sections": [], "forms": [], "spans": []})
            h["mentions"] += 1
            if sec not in h["sections"]:
                h["sections"].append(sec)
            if surface not in h["forms"]:
                h["forms"].append(surface)
            h["spans"].append((start, end))

        ents: list[tuple[int, int, str, str]] = []
        doc_nlp = get_nlp() if use_ner else None
        if doc_nlp is not None:
            doc = doc_nlp(text[:100_000])
            ents = [(e.start_char, e.end_char, e.label_, e.text) for e in doc.ents if e.label_ in NER_LABELS]

        result = ExtractionResult()
        for canonical, h in hits.items():
            skill = self.kb.skills[canonical]
            ner_ok = any(s < e2 and s2 < e for s, e in h["spans"] for s2, e2, _, _ in ents)
            conf = _confidence(
                exact=any(f.lower() == canonical.lower() for f in h["forms"]),
                in_skills="skills" in h["sections"],
                in_usage=bool({"experience", "projects"} & set(h["sections"])),
                mentions=h["mentions"],
                ner=ner_ok,
                ambiguous=canonical in self.ambiguous and not any(f != canonical for f in h["forms"]),
                has_skills_section=has_skills_section,
            )
            if conf is None:
                continue
            result.skills[canonical] = SkillMatch(
                name=canonical, category=skill.category, confidence=conf, mentions=h["mentions"],
                sections=h["sections"], matched_forms=h["forms"], ner_supported=ner_ok,
            )

        # NER entities inside the skills section that the taxonomy does not know about
        if ents and has_skills_section:
            matched_spans = [sp for h in hits.values() for sp in h["spans"]]
            unknown: list[str] = []
            for s, e, label, etext in ents:
                if label not in {"ORG", "PRODUCT", "WORK_OF_ART", "LANGUAGE"} or section_at(s) != "skills":
                    continue
                if any(s < me and ms < e for ms, me in matched_spans):
                    continue
                term = etext.strip(" ,;:-")
                if 1 < len(term) <= 40 and term not in unknown and not self.normalize(term):
                    unknown.append(term)
            result.unrecognized_terms = unknown[:25]
        return result


_LABEL_PREFIX = re.compile(r"^(\s*-?\s*[A-Za-z][A-Za-z &/+.-]{0,40}?):(?=\s*\S)")


def _mask_non_claims(lines: list[str], sections: Sections) -> str:
    """Blank out text that names a skill without claiming it, keeping character offsets stable.

    * Education lines: a degree field ("M.S. in Statistics") is captured as education, not a skill.
    * Group labels in the Skills section ("Machine Learning: scikit-learn, XGBoost") are headings.
    """
    out: list[str] = []
    for i, line in enumerate(lines):
        sec = sections.line_sections[i] if i < len(sections.line_sections) else "header"
        if sec == "education":
            out.append(" " * len(line))
            continue
        if sec == "skills":
            m = _LABEL_PREFIX.match(line)
            if m and len(m.group(1).split()) <= 4:
                line = " " * m.end() + line[m.end():]
        out.append(line)
    return "\n".join(out)


def _confidence(*, exact: bool, in_skills: bool, in_usage: bool, mentions: int, ner: bool,
                ambiguous: bool, has_skills_section: bool) -> float | None:
    """Heuristic confidence in [0, 0.99]. Returns None when the match should be discarded.

    base 0.60 (alias) / 0.70 (canonical name)
    +0.15 listed in a Skills section
    +0.10 used in Experience/Projects (evidence of application)
    +0.05 per extra mention (max +0.10)
    +0.05 spaCy NER tagged the span as an entity
    Ambiguous names (R, Go, C, Excel) outside a Skills section are dropped when a Skills section
    exists, otherwise capped at 0.40.
    """
    if ambiguous and not in_skills:
        if has_skills_section:
            return None
        return 0.4
    conf = 0.70 if exact else 0.60
    if in_skills:
        conf += 0.15
    if in_usage:
        conf += 0.10
    conf += min(0.10, 0.05 * max(0, mentions - 1))
    if ner:
        conf += 0.05
    return round(min(conf, 0.99), 2)


@lru_cache
def get_extractor() -> SkillExtractor:
    return SkillExtractor(get_kb())


def extract_skills(text: str, sections: Sections | None = None, use_ner: bool = True) -> ExtractionResult:
    """Tool entrypoint: extract canonical skills (with confidence) from resume text."""
    return get_extractor().extract(text, sections, use_ner=use_ner)


def normalize_skills(terms: list[str]) -> list[str]:
    """Tool entrypoint: normalize free-form skill strings to canonical taxonomy names."""
    return get_extractor().normalize_many(terms)
