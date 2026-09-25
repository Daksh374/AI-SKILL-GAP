import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Api } from "../api/client.js";
import { Alert, Badge, Button, Card, NeedResume, PageHeader, ProgressBar, Spinner, pct } from "../components/ui.jsx";
import { useApp } from "../context/AppContext.jsx";

export default function Careers() {
  const { resume, resumeId, role, setRole, loading } = useApp();
  const [report, setReport] = useState(null);
  const [sortBy, setSortBy] = useState("probability");
  const navigate = useNavigate();

  useEffect(() => {
    Api.modelReport().then(setReport).catch(() => setReport(null));
  }, []);

  if (!resumeId && !loading) return (<><PageHeader title="Career Recommendations" /><NeedResume /></>);
  if (!resume) return <Spinner />;

  const c = resume.careers;
  const preds = [...c.predictions].sort((a, b) => sortBy === "probability" ? b.probability - a.probability : b.match.score - a.match.score);
  const selected = report?.models?.[report?.selected_model]?.test;

  return (
    <>
      <PageHeader title="Career Recommendations" description="Roles ranked by a supervised classifier, each paired with a deterministic skill-match score and a plain-language explanation.">
        <span className="text-sm text-slate-500">Sort by</span>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
          <option value="probability">Model probability</option>
          <option value="match">Match score</option>
        </select>
      </PageHeader>

      <Alert tone="sky" title={`Model: ${c.model_name}${c.model_test_macro_f1 != null ? ` · test macro-F1 ${c.model_test_macro_f1.toFixed(3)}` : ""}`}>
        {c.disclaimer}
        {selected && report && (
          <span className="mt-1 block text-xs">
            Trained on {report.n_samples} synthetic resumes ({report.split.train}/{report.split.validation}/{report.split.test} split) ·
            compared {Object.keys(report.models).join(", ")} · selected by {report.selection_metric} · test accuracy {pct(selected.accuracy, 1)}, top-3 {pct(selected.top3_accuracy, 1)}.
          </span>
        )}
      </Alert>

      <div className="mt-6 space-y-4">
        {preds.map((p) => (
          <Card key={p.role}>
            <div className="flex flex-col gap-4 lg:flex-row">
              <div className="lg:w-72 lg:shrink-0">
                <div className="flex items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-50 text-sm font-semibold text-brand-700">{p.rank}</span>
                  <h3 className="text-lg font-semibold text-slate-900">{p.role}</h3>
                </div>
                <div className="mt-1 text-xs text-slate-500">{p.category}</div>
                <div className="mt-4 space-y-3">
                  <ProgressBar value={p.probability} label="Model probability" />
                  <ProgressBar value={p.match.score} label="Skill-match score" tone="green" />
                  <ProgressBar value={p.match.required_coverage} label="Required-skill coverage" tone="sky" />
                </div>
                <div className="mt-4 flex gap-2">
                  <Button variant={role === p.role ? "secondary" : "primary"} onClick={() => setRole(p.role)} disabled={role === p.role}>
                    {role === p.role ? "Target role" : "Set as target"}
                  </Button>
                  <Button variant="ghost" onClick={() => { setRole(p.role); navigate("/skill-gap"); }}>Gap →</Button>
                </div>
              </div>

              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Why this role</div>
                <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-700">
                  {p.explanation.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <Chips title="Matched" tone="green" items={p.match.matched_required} />
                  <Chips title="Partial" tone="amber" items={p.match.partial_required} />
                  <Chips title="Missing" tone="red" items={p.match.missing_required} />
                </div>
                {p.top_features?.length > 0 && (
                  <div className="mt-4 text-xs text-slate-500">
                    Occlusion analysis — removing each skill lowers this role's probability by:{" "}
                    {p.top_features.map((f) => `${f.feature} (−${(f.probability_drop_if_removed * 100).toFixed(1)} pts)`).join(", ")}
                  </div>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}

function Chips({ title, tone, items }) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-slate-500">{title} ({items.length})</div>
      <div className="flex flex-wrap gap-1">
        {items.length ? items.map((s) => <Badge key={s} tone={tone}>{s}</Badge>) : <span className="text-xs text-slate-400">—</span>}
      </div>
    </div>
  );
}
