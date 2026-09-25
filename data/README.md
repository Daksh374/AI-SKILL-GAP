# Data directory — SYNTHETIC DATA

**Every dataset in this directory is synthetically generated.** These files exist **only** to
train and evaluate the career-ranking model, to evaluate the resume NLP pipeline, and to power
skill normalization and the skill-dependency graph.

**None of these files represent real labor-market data.** People, companies, universities,
e-mail addresses (`@example.com`) and phone numbers (`555-01xx`) are fictional. Role→skill
weights are editorial judgements, not measured statistics. The application never presents these
numbers as current market statistics — live market information comes only from Tavily search
results, shown with source URLs and retrieval dates.

## Files

### `skills_taxonomy.json` — 219 skills
| field | meaning |
|---|---|
| `skill_id` | stable id (`SK001`…) |
| `name` | canonical skill name — the normalization target (e.g. `Scikit-learn`) |
| `category` | one of 19 categories (Programming Languages, Machine Learning, Cloud, …) |
| `aliases` | case-insensitive surface forms that normalize to `name` (`sklearn`, `scikit learn`) |
| `case_sensitive_aliases` | surface forms matched only with exact case (`RAG`, `NER`, `BI`, `SOC`) |
| `importance` | 1 niche · 2 commonly used · 3 foundational (curated; used in gap priority) |
| `difficulty` | 1 foundational · 2 intermediate · 3 advanced (curated; used for study-time estimates) |
| `ambiguous` | name collides with plain English/single letters (`R`, `Go`, `C`, `Excel`) → matched case-sensitively and trusted only inside a Skills section |

### `skill_relationships.csv` — 493 edges
`relationship_id, source_skill_id, source_skill, target_skill_id, target_skill, relationship_type, strength`

* `prerequisite` — *source* should be learned before *target* (forms a DAG; drives roadmap ordering)
* `related` — undirected similarity (drives *partial* matches in the skill-gap engine)
* `specialization` — *source* is a specific tool/technique of the broader *target* (e.g. `PyTorch → Deep Learning`)

### `job_roles.csv` — 22 roles
`role_id, role_name, category, description, experience_level, required_skills, optional_skills, skill_weights, education_requirements`

`required_skills` / `optional_skills` are `;`-separated canonical skill names.
`skill_weights` is a JSON object `{skill: 1|2|3}` over the required skills (3 = core).

### `job_descriptions.csv` — 2,974 synthetic postings
`job_id, role_id, role_name, job_title, description, required_skills, preferred_skills, experience_years, education, industry, location, employment_type`

Used to (1) build per-role skill-demand profiles within the synthetic corpus and (2) build
role-prototype vectors that the classifier uses as features.

### `resume_dataset.csv` — 3,492 synthetic resumes
`resume_id, resume_text, target_role, education, experience_years, skills, projects, certifications`

`resume_text` is what the model sees (run through the same NLP pipeline as uploaded resumes).
`skills` (`;`-separated canonical names), `experience_years`, `education`, `projects` and
`certifications` are the generator's ground truth and are used to evaluate the NLP pipeline.
