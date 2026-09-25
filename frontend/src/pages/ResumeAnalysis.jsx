import { useRef, useState } from "react";
import { errorMessage } from "../api/client.js";
import { Alert, Badge, Button, Card, PageHeader, ProgressBar, Spinner, cx, fmtDate } from "../components/ui.jsx";
import { useApp } from "../context/AppContext.jsx";

export default function ResumeAnalysis() {
  const { resume, resumes, resumeId, uploadResume, loadResume, deleteResume, loading } = useApp();
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [err, setErr] = useState(null);
  const [drag, setDrag] = useState(false);
  const input = useRef(null);

  async function handle(file) {
    if (!file) return;
    if (!/\.(pdf|docx)$/i.test(file.name)) return setErr("Please upload a .pdf or .docx file.");
    setErr(null);
    setBusy(true);
    setProgress(0);
    try {
      await uploadResume(file, setProgress);
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const p = resume?.profile;
  return (
    <>
      <PageHeader title="Resume Analysis" description="Upload → text extraction → section detection → skill extraction & normalization (taxonomy + aliases + spaCy NER) → structured profile." />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); handle(e.dataTransfer.files[0]); }}
            className={cx("flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition",
              drag ? "border-brand-500 bg-brand-50" : "border-slate-300 bg-slate-50")}>
            <div className="text-base font-medium text-slate-800">Drop your resume here</div>
            <div className="text-sm text-slate-500">PDF or DOCX · max 5 MB · text-based (not scanned)</div>
            <input ref={input} type="file" accept=".pdf,.docx" className="hidden" onChange={(e) => handle(e.target.files[0])} />
            <Button onClick={() => input.current?.click()} disabled={busy}>{busy ? "Analysing…" : "Choose file"}</Button>
            {busy && <div className="w-64"><ProgressBar value={progress} label={progress < 1 ? "Uploading" : "Extracting & ranking"} /></div>}
          </div>
          {err && <div className="mt-4"><Alert title="Upload failed">{err}</Alert></div>}
        </Card>

        <Card title="Your uploads" subtitle="Stored for this browser session">
          {resumes.length === 0 ? <p className="text-sm text-slate-500">Nothing uploaded yet.</p> : (
            <ul className="space-y-2">
              {resumes.map((r) => (
                <li key={r.id} className={cx("flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm",
                  r.id === resumeId ? "border-brand-200 bg-brand-50" : "border-slate-200")}>
                  <button className="min-w-0 flex-1 text-left" onClick={() => loadResume(r.id)}>
                    <div className="truncate font-medium text-slate-800">{r.name || r.filename}</div>
                    <div className="truncate text-xs text-slate-500">{fmtDate(r.created_at)} · {r.skill_count} skills · {r.top_role}</div>
                  </button>
                  <button className="text-xs text-slate-400 hover:text-rose-600" onClick={() => deleteResume(r.id)} title="Delete">✕</button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {loading && <div className="mt-6"><Spinner /></div>}
      {p && <Profile p={p} filename={resume.resume.filename} />}
    </>
  );
}

function Profile({ p, filename }) {
  const byCat = p.technical_skills.reduce((acc, s) => ({ ...acc, [s.category]: [...(acc[s.category] || []), s] }), {});
  return (
    <div className="mt-6 space-y-6">
      {p.warnings?.length > 0 && <Alert tone="amber" title="Extraction notes">{p.warnings.join(" ")}</Alert>}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title={p.name || "Candidate"} subtitle={filename}>
          <dl className="space-y-2 text-sm">
            <Row k="Email" v={p.email} />
            <Row k="Phone" v={p.phone} />
            <Row k="Experience" v={`${p.total_experience_years} years (${p.experience_source.replace("_", " ")})`} />
            <Row k="Highest degree" v={p.highest_education_level} />
            <Row k="Words" v={p.word_count} />
          </dl>
          <div className="mt-4 flex flex-wrap gap-1.5">
            {p.sections_detected.map((s) => <Badge key={s} tone="slate">{s}</Badge>)}
          </div>
          {p.summary && <p className="mt-4 text-sm text-slate-600">{p.summary}</p>}
        </Card>

        <Card className="lg:col-span-2" title={`Technical skills (${p.technical_skills.length})`}
          subtitle="Confidence is a transparent heuristic: Skills-section listing, usage in experience/projects, repeat mentions and NER support.">
          <div className="grid gap-5 sm:grid-cols-2">
            {Object.entries(byCat).map(([cat, skills]) => (
              <div key={cat}>
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{cat}</div>
                <ul className="space-y-2">
                  {skills.map((s) => <SkillRow key={s.name} s={s} />)}
                </ul>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title={`Soft skills (${p.soft_skills.length})`}>
          <ul className="space-y-2">{p.soft_skills.map((s) => <SkillRow key={s.name} s={s} />)}</ul>
          {p.soft_skills.length === 0 && <p className="text-sm text-slate-500">None detected.</p>}
          {p.unrecognized_terms?.length > 0 && (
            <div className="mt-5">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Not in taxonomy (NER)</div>
              <p className="mb-2 text-xs text-slate-500">Entities spaCy found in your Skills section that the taxonomy doesn't know — not counted as skills.</p>
              <div className="flex flex-wrap gap-1.5">{p.unrecognized_terms.map((t) => <Badge key={t}>{t}</Badge>)}</div>
            </div>
          )}
        </Card>

        <Card title="Education">
          {p.education.length === 0 ? <p className="text-sm text-slate-500">No education entries detected.</p> : (
            <ul className="space-y-3 text-sm">
              {p.education.map((e, i) => (
                <li key={i}>
                  <div className="font-medium text-slate-800">{e.degree || e.level}{e.field_of_study ? ` · ${e.field_of_study}` : ""}</div>
                  <div className="text-slate-500">{[e.institution, e.year].filter(Boolean).join(" · ") || e.raw}</div>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-5 text-xs font-semibold uppercase tracking-wide text-slate-500">Certifications</div>
          {p.certifications.length ? (
            <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-700">{p.certifications.map((c) => <li key={c}>{c}</li>)}</ul>
          ) : <p className="mt-2 text-sm text-slate-500">None detected.</p>}
        </Card>

        <Card title="Experience">
          {p.experience.length === 0 ? <p className="text-sm text-slate-500">No dated roles detected.</p> : (
            <ol className="relative space-y-4 border-l border-slate-200 pl-4">
              {p.experience.map((e, i) => (
                <li key={i} className="text-sm">
                  <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-white bg-brand-500" />
                  <div className="font-medium text-slate-800">{e.title || "Role"}</div>
                  <div className="text-slate-500">{e.company}</div>
                  <div className="text-xs text-slate-400">{e.start} → {e.end} · {e.duration_months} months</div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>

      {p.projects.length > 0 && (
        <Card title="Projects">
          <div className="grid gap-4 md:grid-cols-2">
            {p.projects.map((pr, i) => (
              <div key={i} className="rounded-xl border border-slate-200 p-4">
                <div className="font-medium text-slate-800">{pr.title}</div>
                {pr.description && <p className="mt-1 text-sm text-slate-600">{pr.description}</p>}
                <div className="mt-2 flex flex-wrap gap-1.5">{pr.skills.map((s) => <Badge key={s} tone="brand">{s}</Badge>)}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-slate-500">{k}</dt>
      <dd className="truncate text-right font-medium text-slate-800">{v ?? "—"}</dd>
    </div>
  );
}

function SkillRow({ s }) {
  const tone = s.confidence >= 0.85 ? "green" : s.confidence >= 0.65 ? "brand" : "amber";
  const aliasNote = s.matched_forms.filter((f) => f.toLowerCase() !== s.name.toLowerCase());
  return (
    <li title={`Found as: ${s.matched_forms.join(", ")} · sections: ${s.sections.join(", ")} · mentions: ${s.mentions}${s.ner_supported ? " · NER-supported" : ""}`}>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-slate-700">{s.name}{aliasNote.length > 0 && <span className="ml-1 text-xs font-normal text-slate-400">← {aliasNote.slice(0, 2).join(", ")}</span>}</span>
        <span className="text-xs text-slate-500">{Math.round(s.confidence * 100)}%</span>
      </div>
      <ProgressBar value={s.confidence} tone={tone} className="mt-1" />
    </li>
  );
}
