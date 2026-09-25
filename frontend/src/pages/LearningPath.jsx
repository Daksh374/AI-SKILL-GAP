import { useEffect, useState } from "react";
import { Api, errorMessage } from "../api/client.js";
import { Alert, Badge, Button, Card, NeedResume, PageHeader, PriorityBadge, ProgressBar, Spinner, cx } from "../components/ui.jsx";
import { useApp } from "../context/AppContext.jsx";

const REASON_TONE = { missing: "red", partial: "amber", prerequisite: "slate" };

export default function LearningPath() {
  const { resumeId, role, loading, health } = useApp();
  const [roadmap, setRoadmap] = useState(null);
  const [hours, setHours] = useState(10);
  const [withResources, setWithResources] = useState(true);
  const [busy, setBusy] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!resumeId || !role) return;
    setFetching(true);
    setRoadmap(null);
    Api.getRoadmap(resumeId, role).then((r) => {
      setRoadmap(r);
      if (r) setHours(r.hours_per_week);
    }).catch((e) => setErr(errorMessage(e))).finally(() => setFetching(false));
  }, [resumeId, role]);

  async function generate() {
    setBusy(true);
    setErr(null);
    try {
      setRoadmap(await Api.createRoadmap(resumeId, { role, hours_per_week: Number(hours), include_resources: withResources }));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(stage) {
    try {
      setRoadmap(await Api.updateProgress(roadmap.id, stage.index, !stage.completed));
    } catch (e) {
      setErr(errorMessage(e));
    }
  }

  if (!resumeId && !loading) return (<><PageHeader title="Learning Path" /><NeedResume /></>);

  const doneHours = roadmap?.stages.filter((s) => s.completed).reduce((a, s) => a + s.estimated_hours, 0) || 0;

  return (
    <>
      <PageHeader title="Learning Path" description={`Week-by-week plan for ${role}, built from your actual skill gaps and the prerequisite graph.`} />

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-sm">
            <span className="mb-1 block text-slate-500">Study hours / week</span>
            <input type="number" min={2} max={60} value={hours} onChange={(e) => setHours(e.target.value)}
              className="w-28 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100" />
          </label>
          <label className="flex items-center gap-2 pb-2 text-sm text-slate-600">
            <input type="checkbox" checked={withResources} onChange={(e) => setWithResources(e.target.checked)} className="h-4 w-4 accent-brand-600" />
            Find YouTube & Coursera resources (Tavily)
          </label>
          <Button onClick={generate} disabled={busy || !role}>{busy ? "Building roadmap…" : roadmap ? "Regenerate roadmap" : "Generate roadmap"}</Button>
          {busy && withResources && <span className="pb-2 text-xs text-slate-500">Live resource search can take ~10–30 s.</span>}
        </div>
        {withResources && health && !health.tavily_configured && (
          <p className="mt-3 text-xs text-amber-700">TAVILY_API_KEY is not set — the roadmap will be generated without resources, and each stage will say so.</p>
        )}
      </Card>

      {err && <div className="mt-4"><Alert title="Roadmap error">{err}</Alert></div>}
      {fetching && <div className="mt-6"><Spinner /></div>}

      {roadmap && (
        <>
          <div className="mt-6 grid gap-4 sm:grid-cols-4">
            <Summary label="Total duration" value={`${roadmap.total_weeks} weeks`} />
            <Summary label="Study time" value={`${roadmap.total_hours} h`} />
            <Summary label="Stages" value={roadmap.stages.length} />
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <ProgressBar value={roadmap.total_hours ? doneHours / roadmap.total_hours : 0} label="Progress" tone="green" />
              <div className="mt-2 text-xs text-slate-500">{doneHours} of {roadmap.total_hours} hours</div>
            </div>
          </div>
          {roadmap.resources_status !== "ok" && roadmap.resources_status !== "not_requested" && (
            <div className="mt-4">
              <Alert tone="amber" title="Learning resources unavailable">
                {roadmap.resources_status === "not_configured" ? "Tavily is not configured on the server, so no resources were searched." : `Resource search status: ${roadmap.resources_status}. See notes on each stage.`}
              </Alert>
            </div>
          )}

          <ol className="relative mt-8 space-y-6 border-l-2 border-slate-200 pl-6 sm:ml-3">
            {roadmap.stages.map((st) => (
              <li key={st.index} className="relative">
                <button onClick={() => toggle(st)} title={st.completed ? "Mark as not done" : "Mark as done"}
                  className={cx("absolute -left-[35px] top-5 flex h-6 w-6 items-center justify-center rounded-full border-2 text-xs",
                    st.completed ? "border-emerald-500 bg-emerald-500 text-white" : "border-slate-300 bg-white text-transparent hover:border-brand-500")}>✓</button>
                <Card className={st.completed ? "opacity-70" : ""}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-wide text-brand-600">{st.label}</div>
                      <h3 className="mt-0.5 text-base font-semibold text-slate-900">{st.objective}</h3>
                    </div>
                    <Badge tone="slate">~{st.estimated_hours} h</Badge>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {st.skills.map((s) => (
                      <span key={s.name} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2 py-1 text-sm">
                        <span className="font-medium text-slate-800">{s.name}</span>
                        <Badge tone={REASON_TONE[s.reason]}>{s.reason}</Badge>
                        {s.priority && <PriorityBadge priority={s.priority} />}
                        <span className="text-xs text-slate-400">{s.estimated_hours}h</span>
                      </span>
                    ))}
                  </div>
                  {st.prerequisites.length > 0 && <div className="mt-2 text-xs text-slate-500">Builds on: {st.prerequisites.join(", ")}</div>}

                  <div className="mt-4 rounded-xl bg-slate-50 p-3">
                    <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Practice project</div>
                    <div className="mt-1 text-sm font-medium text-slate-800">{st.practice_project.title}</div>
                    <p className="text-sm text-slate-600">{st.practice_project.description}</p>
                    <ul className="mt-1 list-inside list-disc text-xs text-slate-500">{st.practice_project.deliverables.map((d) => <li key={d}>{d}</li>)}</ul>
                  </div>

                  {roadmap.resources_status !== "not_requested" && (
                    <div className="mt-4 grid gap-4 md:grid-cols-2">
                      <Resources title="YouTube (free to watch)" items={st.youtube} empty="No YouTube results for this stage." />
                      <Resources title="Coursera" items={st.coursera} empty="No Coursera results for this stage." />
                    </div>
                  )}
                  {st.resource_notes.length > 0 && <ul className="mt-3 space-y-0.5 text-xs text-slate-400">{st.resource_notes.map((n) => <li key={n}>{n}</li>)}</ul>}
                </Card>
              </li>
            ))}
          </ol>
          <p className="mt-6 text-xs text-slate-500">{roadmap.method}</p>
        </>
      )}
      {!roadmap && !fetching && !busy && <p className="mt-6 text-sm text-slate-500">No roadmap for {role} yet — choose your weekly hours and generate one.</p>}
    </>
  );
}

function Summary({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold text-slate-900">{value}</div>
    </div>
  );
}

function Resources({ title, items, empty }) {
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</div>
      {items.length === 0 ? <p className="text-xs text-slate-400">{empty}</p> : (
        <ul className="space-y-2">
          {items.map((r) => (
            <li key={r.url} className="text-sm">
              <a href={r.url} target="_blank" rel="noreferrer" className="font-medium text-brand-700 hover:underline">{r.title}</a>
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                <span>{r.skill}</span>
                {r.resource_type && <span>· {r.resource_type}</span>}
                {r.provider && <span>· {r.provider}</span>}
                {r.platform === "YouTube" && !r.channel && <span className="text-slate-400">· channel not in search metadata</span>}
                {r.free_mentioned && <Badge tone="green" title={`From the retrieved snippet: "${r.free_evidence}"`}>snippet mentions free access</Badge>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
