import { useEffect, useMemo, useState } from "react";
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, RadialBar, RadialBarChart, ResponsiveContainer, Tooltip } from "recharts";
import { Api, errorMessage } from "../api/client.js";
import { Alert, Badge, Card, NeedResume, PageHeader, PriorityBadge, Spinner, cx, pct } from "../components/ui.jsx";
import { useApp } from "../context/AppContext.jsx";

export default function SkillGap() {
  const { resumeId, role, loading } = useApp();
  const [gap, setGap] = useState(null);
  const [err, setErr] = useState(null);
  const [filter, setFilter] = useState("All");

  useEffect(() => {
    if (!resumeId || !role) return;
    setGap(null);
    setErr(null);
    Api.skillGap(resumeId, role).then(setGap).catch((e) => setErr(errorMessage(e)));
  }, [resumeId, role]);

  const radar = useMemo(() => {
    if (!gap) return [];
    const cats = {};
    for (const s of [...gap.matched, ...gap.partial, ...gap.missing]) {
      if (s.requirement !== "required") continue;
      cats[s.category] ||= { category: s.category, required: 0, current: 0 };
      cats[s.category].required += s.role_weight;
      cats[s.category].current += s.role_weight * s.credit;
    }
    return Object.values(cats).map((c) => ({ category: c.category, Required: 100, Current: Math.round((100 * c.current) / c.required) }));
  }, [gap]);

  if (!resumeId && !loading) return (<><PageHeader title="Skill Gap Analysis" /><NeedResume /></>);
  if (err) return <Alert title="Could not compute skill gap">{err}</Alert>;
  if (!gap) return <Spinner />;

  const gaps = [...gap.missing, ...gap.partial].sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0));
  const shown = filter === "All" ? gaps : gaps.filter((g) => g.priority === filter);
  const s = gap.summary;

  return (
    <>
      <PageHeader title="Skill Gap Analysis" description={`Required vs. current skills for ${gap.role}. Computed deterministically from the role's requirement weights and the skill graph — no LLM involved.`} />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Readiness" subtitle="Weighted required-skill coverage">
          <div className="relative h-52">
            <ResponsiveContainer>
              <RadialBarChart innerRadius="72%" outerRadius="100%" startAngle={90} endAngle={-270}
                data={[{ name: "readiness", value: Math.round(gap.readiness_score * 100), fill: "#4f46e5" }]}>
                <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
                <RadialBar background dataKey="value" cornerRadius={10} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div className="text-3xl font-semibold text-slate-900">{pct(gap.readiness_score)}</div>
              <div className="text-xs text-slate-500">{gap.role}</div>
            </div>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2 text-center text-sm">
            <div><div className="font-semibold text-emerald-600">{s.required_matched}</div><div className="text-xs text-slate-500">matched</div></div>
            <div><div className="font-semibold text-amber-600">{s.required_partial}</div><div className="text-xs text-slate-500">partial</div></div>
            <div><div className="font-semibold text-rose-600">{s.required_missing}</div><div className="text-xs text-slate-500">missing</div></div>
          </div>
          <div className="mt-2 text-center text-xs text-slate-500">of {s.required_total} required · {s.optional_matched}/{s.optional_total} optional matched</div>
        </Card>

        <Card className="lg:col-span-2" title="Required vs. current, by category" subtitle="100 = every required skill in the category fully covered">
          <div className="h-72">
            {radar.length >= 3 ? (
              <ResponsiveContainer>
                <RadarChart data={radar} outerRadius="62%" margin={{ left: 30, right: 30 }}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="category" tick={{ fontSize: 11 }} />
                  <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                  <Radar name="Required" dataKey="Required" stroke="#94a3b8" fill="#94a3b8" fillOpacity={0.15} />
                  <Radar name="Current" dataKey="Current" stroke="#4f46e5" fill="#4f46e5" fillOpacity={0.35} />
                  <Tooltip />
                </RadarChart>
              </ResponsiveContainer>
            ) : (
              <ul className="space-y-2 pt-6 text-sm">{radar.map((r) => <li key={r.category}>{r.category}: {r.Current}% covered</li>)}</ul>
            )}
          </div>
        </Card>
      </div>

      <Card className="mt-6" title="Skills to acquire" subtitle="Priority = 0.35·role weight + 0.25·synthetic-JD demand + 0.20·taxonomy importance + 0.20·foundation (prerequisite depth & skills it unblocks)"
        action={
          <div className="flex gap-1">
            {["All", "High", "Medium", "Low"].map((f) => (
              <button key={f} onClick={() => setFilter(f)} className={cx("rounded-md px-2.5 py-1 text-xs font-medium",
                filter === f ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}>{f}</button>
            ))}
          </div>
        }>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500">
              <tr className="border-b border-slate-200">
                <th className="py-2 pr-3">Skill</th><th className="py-2 pr-3">Status</th><th className="py-2 pr-3">Priority</th>
                <th className="py-2 pr-3">Score</th><th className="py-2 pr-3">Requirement</th><th className="py-2">Why</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {shown.map((g) => (
                <tr key={g.name} className="align-top">
                  <td className="py-2.5 pr-3"><div className="font-medium text-slate-800">{g.name}</div><div className="text-xs text-slate-400">{g.category}</div></td>
                  <td className="py-2.5 pr-3"><Badge tone={g.status === "missing" ? "red" : "amber"}>{g.status}</Badge></td>
                  <td className="py-2.5 pr-3"><PriorityBadge priority={g.priority} /></td>
                  <td className="py-2.5 pr-3 tabular-nums">{g.priority_score?.toFixed(2)}</td>
                  <td className="py-2.5 pr-3 text-xs text-slate-600">{g.requirement} · weight {g.role_weight}</td>
                  <td className="py-2.5 text-xs text-slate-600">
                    {g.status === "partial" && <div className="mb-1">Partial credit {pct(g.credit)} via <b>{g.evidence.join(", ")}</b></div>}
                    <div className="text-slate-500">
                      role {g.priority_factors.role_weight} · JD demand {g.priority_factors.jd_demand} · importance {g.priority_factors.importance} ·
                      foundation {g.priority_factors.foundation}{g.priority_factors.unblocks > 0 ? ` (unblocks ${g.priority_factors.unblocks})` : ""}
                    </div>
                  </td>
                </tr>
              ))}
              {shown.length === 0 && <tr><td colSpan={6} className="py-4 text-center text-slate-500">No skills in this bucket.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="mt-6" title={`Current skills that meet requirements (${gap.matched.length})`}>
        <div className="flex flex-wrap gap-1.5">
          {gap.matched.map((m) => <Badge key={m.name} tone="green" title={m.requirement}>{m.name}{m.requirement === "optional" ? " (optional)" : ""}</Badge>)}
          {gap.matched.length === 0 && <span className="text-sm text-slate-500">None yet.</span>}
        </div>
        <p className="mt-4 text-xs text-slate-500">{gap.method} JD demand is measured on the synthetic job-description corpus, not live market data.</p>
      </Card>
    </>
  );
}
