import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Api, errorMessage } from "../api/client.js";
import { Alert, Badge, Card, NeedResume, PageHeader, PriorityBadge, ProgressBar, Spinner, Stat, pct } from "../components/ui.jsx";
import { useApp } from "../context/AppContext.jsx";

export default function Dashboard() {
  const { resumeId, resume, role, loading } = useApp();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!resumeId || !role) return;
    setData(null);
    Api.dashboard(resumeId, role).then(setData).catch((e) => setErr(errorMessage(e)));
  }, [resumeId, role]);

  if (!resumeId && !loading) return (<><PageHeader title="Dashboard" /><NeedResume /></>);
  if (err) return <Alert title="Could not load dashboard">{err}</Alert>;
  if (!data || !resume) return <Spinner />;

  const roleChart = data.top_roles.map((r) => ({ role: r.role, "Model probability": +(r.probability * 100).toFixed(1), "Match score": +(r.match_score * 100).toFixed(1) }));
  const catChart = Object.entries(data.skills_by_category).map(([category, count]) => ({ category, count }));
  const g = data.gap_summary;

  return (
    <>
      <PageHeader title="Dashboard" description={`Career readiness overview for ${data.role}. Change the target role in the header.`} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label={`Readiness · ${data.role}`} value={pct(data.readiness_score)} tone="brand" hint="Weighted coverage of required skills" />
        <Stat label="Extracted skills" value={data.skill_count} hint={`${data.technical_skill_count} technical · ${data.soft_skill_count} soft`} />
        <Stat label="Experience" value={`${data.experience_years} yrs`} hint="From employment date ranges" />
        <Stat label="Education" value={data.education_level} hint="Highest degree detected" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3" title="Top career matches" subtitle="ML probability (synthetic-trained model) vs. transparent skill-match score"
          action={<Link to="/careers" className="text-sm font-medium text-brand-600 hover:underline">Details →</Link>}>
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={roleChart} layout="vertical" margin={{ left: 40, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 12 }} />
                <YAxis type="category" dataKey="role" width={150} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v) => `${v}%`} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Model probability" fill="#4f46e5" radius={[0, 4, 4, 0]} />
                <Bar dataKey="Match score" fill="#10b981" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="lg:col-span-2" title="Skill-gap summary" subtitle={data.role}
          action={<Link to="/skill-gap" className="text-sm font-medium text-brand-600 hover:underline">Analyse →</Link>}>
          <div className="mb-4 grid grid-cols-3 gap-2 text-center">
            <Mini label="Matched" value={`${g.required_matched}/${g.required_total}`} color="text-emerald-600" />
            <Mini label="Partial" value={g.required_partial} color="text-amber-600" />
            <Mini label="Missing" value={g.required_missing} color="text-rose-600" />
          </div>
          <div className="mb-3 flex gap-2">
            <Badge tone="red">{g.high_priority} high</Badge>
            <Badge tone="amber">{g.medium_priority} medium</Badge>
            <Badge tone="sky">{g.low_priority} low priority</Badge>
          </div>
          <ul className="divide-y divide-slate-100">
            {data.top_gaps.map((t) => (
              <li key={t.name} className="flex items-center justify-between py-2 text-sm">
                <span>{t.name} <span className="text-xs text-slate-400">({t.status})</span></span>
                <PriorityBadge priority={t.priority} />
              </li>
            ))}
            {data.top_gaps.length === 0 && <li className="py-2 text-sm text-slate-500">No required-skill gaps for this role.</li>}
          </ul>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Skills by category" subtitle="Technical skills extracted from your resume">
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={catChart} margin={{ bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="category" angle={-35} textAnchor="end" interval={0} tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Learning progress" subtitle={`Roadmap for ${data.role}`}
          action={<Link to="/learning-path" className="text-sm font-medium text-brand-600 hover:underline">Open →</Link>}>
          {data.progress ? (
            <div className="space-y-4">
              <ProgressBar value={data.progress.percent / 100} label="Study hours completed" tone="green" />
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Mini label="Stages done" value={`${data.progress.stages_completed}/${data.progress.stages_total}`} />
                <Mini label="Hours done" value={`${data.progress.hours_completed}/${data.progress.hours_total} h`} />
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">No roadmap yet for this role. <Link to="/learning-path" className="font-medium text-brand-600 hover:underline">Generate one</Link> to track progress.</p>
          )}
        </Card>
      </div>
    </>
  );
}

function Mini({ label, value, color = "text-slate-900" }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <div className={`text-xl font-semibold ${color}`}>{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}
