# AI Skill-Gap & Career Intelligence Engine

Upload a resume (PDF/DOCX). The app then:
1. **extracts your skills with NLP**,
2. **ranks suitable career roles with a trained ML model**,
3. **computes your skill gap** for a target role using deterministic rules,
4. **pulls live market trends and learning resources** through Tavily, and
5. **builds a prerequisite-aware, week-by-week learning roadmap**.

This is deliberately a plain **ML + NLP application**. It uses no agents, LangGraph or RAG/vector DB.
Every number shown comes from one of three places: the trained model, deterministic rule-based code,
or a live API call.

---

## Architecture

```
          ┌──────────── React (Vite, Tailwind, Recharts) ────────────┐
          │ Dashboard · Resume · Careers · Skill Gap · Market · Path │
          └───────────────────────────┬───────────────────────────────┘
                                      │ /api (proxied; no keys in browser)
┌─────────────────────────────── FastAPI ────────────────────────────────────┐
│ routers/ resumes · roadmap · market · meta                                  │
│                                                                             │
│ parse_resume ─► clean_text ─► detect_sections ─► extract_skills ─► profile  │
│   (PyMuPDF /     (unicode,     (heading rules)    (taxonomy+aliases  (edu,  │
│    python-docx)   bullets)                         +spaCy NER,       exp,   │
│                                                    normalize_skills) certs) │
│                                     │                                       │
│             FeatureBuilder ─► predict_career (LR / RF / XGB, best by F1)    │
│                                     │   + role_match (deterministic)        │
│             calculate_skill_gap (rules over skill_relationships + weights)  │
│             build_learning_path (prerequisite DAG → staged timeline)        │
│             tavily_search ─► market intelligence / find_youtube_resources / │
│                              find_coursera_resources                        │
│ SQLAlchemy + SQLite: resumes, profiles, predictions, roadmaps+progress,     │
│                      market reports, Tavily response cache                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

```
backend/app/
  config.py         settings (.env)
  knowledge.py      loads data/*.csv|json into a KnowledgeBase (skills, roles, graph, JD demand)
  schemas.py        Pydantic models
  nlp/              parser.py · sections.py · skills.py · profile.py · spacy_loader.py
  ml/               features.py · train.py · predictor.py
  services/         matching.py · skill_gap.py · roadmap.py · tavily_client.py · resources.py · market.py
  routers/          resumes.py · roadmap.py · market.py · meta.py
  db/database.py    ORM models + session
frontend/           React app (6 pages)
data/               synthetic CSV/JSON datasets (see data/README.md)
models/             career_model.joblib, evaluation_report.{md,json}, confusion_matrix.csv
tests/              pytest suite (NLP, skill gap, roadmap, Tavily client, API)
```

## Datasets (`data/`, all synthetic)

| File | Rows | Schema |
|---|---|---|
| `skills_taxonomy.json` | 219 skills | skill_id, name, category, aliases, case_sensitive_aliases, importance, difficulty, ambiguous |
| `skill_relationships.csv` | 493 edges | relationship_id, source/target skill (id+name), relationship_type (`prerequisite` / `related` / `specialization`), strength |
| `job_roles.csv` | 22 roles | role_id, role_name, category, description, experience_level, required_skills, optional_skills, skill_weights, education_requirements |
| `job_descriptions.csv` | 2,974 | job_id, role_id, role_name, job_title, description, required_skills, preferred_skills, experience_years, education, industry, location, employment_type |
| `resume_dataset.csv` | 3,492 | resume_id, resume_text, target_role, education, experience_years, skills, projects, certifications |

**These are synthetic and are not labor-market data.** See [data/README.md](data/README.md). Learning
resources and market data are always fetched live.

---

## Setup

Prerequisites: Python 3.12 (3.11+ works), Node 20+. On macOS, XGBoost needs the OpenMP runtime:
`brew install libomp`.

```bash
cp .env.example .env        # leave TAVILY_API_KEY empty for now; set SECRET_KEY
```

### 1. Backend environment
```bash
python3.12 -m venv .venv
```
```bash
.venv/bin/pip install -r backend/requirements.txt
```
```bash
.venv/bin/python -m spacy download en_core_web_sm
```

### 2. Datasets
The datasets ship pre-generated as CSV/JSON files in `data/`. Nothing needs to be generated.

### 3. Train the ML model (reads `data/resume_dataset.csv` + `data/job_descriptions.csv`)
```bash
.venv/bin/python -m backend.app.ml.train
```
This prints the model comparison and writes `models/career_model.joblib`, `models/evaluation_report.md`,
`models/evaluation_report.json` and `models/confusion_matrix.csv`.

### 4. Start the FastAPI backend (API docs at http://localhost:8000/docs)
```bash
.venv/bin/uvicorn backend.app.main:app --reload --port 8000
```

### 5. Start the React frontend (http://localhost:5173)
```bash
cd frontend && npm install && npm run dev
```
The Vite dev server proxies `/api` to `http://localhost:8000`. If the backend runs on a different port, set
`VITE_BACKEND_URL=http://localhost:<port>`.

### 6. Run the full stack with Docker (frontend http://localhost:8080, API http://localhost:8000)
```bash
docker compose up --build
```
The backend image installs dependencies, downloads the spaCy model and trains the career model from the
CSVs during the build.

### Tests
```bash
.venv/bin/python -m pytest
```

### Adding Tavily later
Put your key in `.env` (`TAVILY_API_KEY=tvly-...`) and restart the backend. Until then, Market Intelligence
and learning resources report **"not configured"** instead of showing any made-up content.

---

## API (FastAPI; interactive docs at `/docs`)

All resume-scoped endpoints need an `X-Session-ID` header. The frontend generates an anonymous UUID for it,
and the server HMAC-hashes the ID with `SECRET_KEY` before storing it.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | model / spaCy / Tavily status |
| GET | `/api/roles` | roles with requirement weights |
| GET | `/api/skills?q=` | taxonomy search |
| GET | `/api/model/report` | training + evaluation report |
| POST | `/api/resumes` | upload PDF/DOCX → profile + ranked careers |
| GET | `/api/resumes` · `/api/resumes/{id}` · DELETE `/api/resumes/{id}` | session resumes |
| GET | `/api/resumes/{id}/careers` | ranked roles (probability + match score + explanation) |
| GET | `/api/resumes/{id}/skill-gap?role=` | deterministic gap with priorities |
| GET | `/api/resumes/{id}/dashboard?role=` | aggregated dashboard data |
| POST | `/api/resumes/{id}/roadmap` | build roadmap `{role, hours_per_week, include_resources}` |
| GET | `/api/resumes/{id}/roadmap?role=` | latest roadmap |
| PATCH | `/api/roadmaps/{id}/progress` | `{stage_index, completed}` |
| POST | `/api/market` | live market intelligence `{role, resume_id?, refresh?}` |
| GET | `/api/resources?skill=` | YouTube + Coursera resources for one skill |

---

## How it works

### NLP pipeline (`backend/app/nlp`)
1. **Parsing:** PyMuPDF (PDF, sorted text blocks) and python-docx (paragraphs and table cells, since
   two-column templates use tables). Scanned or empty PDFs are rejected with a clear message.
2. **Cleaning:** NFKC unicode normalization, bullet glyphs converted to `- `, hyphenated line breaks
   rejoined, whitespace collapsed. Line structure is kept because section detection relies on it.
3. **Section detection:** heading rules (≤5 words, a known heading vocabulary, inline `Skills: …` form).
4. **Skill extraction and normalization:** one compiled regex alternation per case mode over all taxonomy
   surface forms, tried longest first. Overlapping matches are resolved in favour of the longer span, so
   "text classification" does not also count "classification". Each surface form maps to one canonical
   name (`sklearn` → `Scikit-learn`).
   * Ambiguous names (`R`, `Go`, `C`, `Excel`) are case-sensitive and are only trusted inside a Skills section.
   * Degree fields ("M.S. in Statistics") and group labels ("Machine Learning: …") are masked out. They
     name a skill without claiming it.
   * **spaCy NER** adds a confidence boost when an entity overlaps a match. Entities in the Skills section
     that aren't in the taxonomy are reported as `unrecognized_terms` and are never silently turned into skills.
   * **Confidence** is a transparent heuristic, not a probability: base 0.6 (alias) or 0.7 (canonical),
     +0.15 if listed in Skills, +0.10 if used in Experience/Projects, +0.05 per extra mention (max +0.10),
     and +0.05 for NER support.
5. **Profile:** name (header heuristics, falling back to spaCy PERSON), contact, education (degree level,
   field, institution, year), experience (date ranges with overlaps merged; "Present" means today;
   falls back to "N years of experience"), projects, certifications.

Evaluated on the synthetic resumes: skill precision 0.999, recall 1.0, experience MAE 0.0 years. **These
numbers are optimistic**, because the generator uses the same taxonomy vocabulary. Real resumes will score lower.

### ML career ranking (`backend/app/ml`)
* **Features (281):** skill multi-hot (219), per-category skill counts (19), cosine similarity to each
  role's **prototype vector built from `job_descriptions.csv`** (22), experience, education level,
  field-of-study group, certification keyword groups, and counts of certifications, projects and skills.
  Training runs every `resume_text` through **the same NLP pipeline** used at inference, so training and
  serving share one code path.
* **Models:** Logistic Regression (scaled), Random Forest and XGBoost, each with a small hyperparameter grid.
  Data is split **70/15/15 stratified**, the grid is chosen on validation macro-F1, and all three are
  reported on the held-out test set (accuracy, macro precision/recall/F1, top-3 accuracy, confusion matrix).
  The best family by validation macro-F1 is saved with joblib.
* **Current result:** Logistic Regression was selected, with test macro-F1 0.987 and top-3 accuracy 1.0.
  See [models/evaluation_report.md](models/evaluation_report.md).
* **Caveat:** the model learns the *patterns of the synthetic generator*, and the synthetic classes separate
  cleanly. Scores that high, and very confident probabilities, demonstrate the ML workflow. They are not
  evidence about real hiring outcomes. The UI says this next to every probability.
* **Explainability:** each ranked role also gets a **deterministic match score**
  (0.8 × weighted required coverage + 0.2 × optional coverage, with partial credit via the skill graph),
  a plain-language explanation, and a **model-agnostic occlusion attribution**. Occlusion removes each of
  your skills in turn and measures how much that role's probability drops.

### Skill-gap engine (`services/skill_gap.py`, fully deterministic)
* **Credit per role skill:** exact = 1.0, implied by a specialization (you know PyTorch, so Deep
  Learning) = 0.75, strongly related = 0.5, sibling tool (Power BI vs Tableau) = 0.4, weakly related = 0.35.
  This yields matched, partial and missing skills with evidence.
* **Priority** = 0.35·role weight + 0.25·synthetic-JD demand + 0.20·taxonomy importance
  + 0.20·foundation (inverse prerequisite depth plus how many other gaps it unblocks). Partial skills are
  discounted. High ≥ 0.60, Medium ≥ 0.40, otherwise Low. Every factor is returned and shown in the UI.
* **Readiness** = weighted required-skill credit.

### Market intelligence and resources (Tavily only, `services/`)
* `tavily_search` runs **server-side only**. It retries with exponential backoff on timeouts, network
  errors, 429 and 5xx (honouring `Retry-After`), does not retry auth errors, and limits concurrency with a
  semaphore. Responses are cached for 24h in SQLite to save rate limit. Sources are de-duplicated by
  normalized URL, and each one keeps its URL, snippet, published date and retrieval timestamp.
* **Market page:** three queries (in-demand skills, job-market news, emerging tools). The UI separates:
  * **Observed from retrieved sources:** source cards, plus a deterministic count of taxonomy skills
    mentioned across the retrieved snippets, colour-coded by whether you have each skill.
  * **AI-generated interpretation:** Tavily's LLM answer text, labelled as such, with the URLs it was based on.
* **Resources:** `site:youtube.com <skill> tutorial` and `site:coursera.org <skill> course`, each restricted
  with `include_domains`. Only real video/playlist URLs and course, specialization, certificate or guided-project
  URLs are kept (up to 3 per skill). YouTube channel, duration and thumbnail are **not guessed**, because Tavily
  metadata doesn't reliably include them. A Coursera item is marked *"snippet mentions free access"* only when
  the retrieved text says so ("free trial" doesn't count), and the matching text is shown as evidence.
* Empty results, failures and missing configuration are shown as such. Nothing is fabricated.

### Learning roadmap (`services/roadmap.py`)
Targets are all required gap skills plus High/Medium optional ones. Missing prerequisites are added
transitively from the prerequisite DAG. The plan is a **layered topological sort**: a stage only contains
skills whose prerequisites were covered in earlier stages. The most urgent skills go first, and a
prerequisite inherits the urgency of whatever it unlocks. Stages are packed into about two weeks of your
chosen weekly hours. Hours come from taxonomy difficulty (10/20/35 h, halved for partial skills). Each stage
has an objective, skills, prerequisites, estimated hours, a template-based practice project, and live
YouTube/Coursera resources. Progress is stored per stage.

---

## Interview notes

**ML methodology.** "I framed career ranking as multi-class classification over 22 roles. Features come
from the NLP output: skill presence, category counts, experience, education and certifications. I also added
prototype-similarity features built from a separate job-description corpus, which acts like a nearest-centroid
prior. I compared Logistic Regression, Random Forest and XGBoost on a stratified train/validation/test split,
tuned each on validation macro-F1 (macro, so every role counts equally), and reported all three on a held-out
test set with a confusion matrix. The data is synthetic, so the model learns the generator's patterns. That's
why every probability sits next to a transparent match score and an occlusion-based explanation, rather than
being presented as a hiring prediction."

**NLP pipeline.** "It's deterministic and fast, with no LLM. After parsing and cleaning, heading rules split
the resume into sections. Skill extraction is a single longest-first regex over about 1,000 taxonomy surface
forms, normalized to canonical names. Context rules handle ambiguity: 'R' or 'Go' only count inside a Skills
section, and degree fields and group labels are masked. spaCy NER supports confidence and flags unknown
technologies without inventing skills. Confidence is an explainable heuristic, and I evaluated extraction
against the dataset's ground truth, knowing the synthetic score is optimistic."

**Tavily integration.** "All web access goes through one server-side client with retries, backoff, a
rate-limit-aware semaphore, a SQLite response cache and URL de-duplication, so the key never reaches the
browser. I kept provenance on everything: URL, snippet and retrieval time. The UI puts sourced facts and
Tavily's AI summary in visibly separate panels. Domain-restricted queries replace the YouTube Data API, and
I only show fields that Tavily actually returns. When search fails or returns nothing, the app says so."
