import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Api, errorMessage } from "../api/client.js";
import { Alert, Badge, Button, Card, PageHeader, Spinner, fmtDate } from "../components/ui.jsx";
import { useApp } from "../context/AppContext.jsx";

export default function Market() {
  const { role, resumeId, health } = useApp();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(async (refresh = false) => {
    if (!role) return;
    setBusy(true);
    setErr(null);
    try {
      setData(await Api.market(role, resumeId, refresh));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [role, resumeId]);

  useEffect(() => { setData(null); load(false); }, [load]);

  const chart = (data?.skill_mentions || []).slice(0, 15).map((m) => ({ skill: m.skill, sources: m.source_count, has: m.candidate_has }));

  return (
    <>
      <PageHeader title="Market Intelligence" description={`Live web results for ${role || "your target role"}, retrieved server-side through Tavily. Synthetic training data is never shown here.`}>
        <Button variant="secondary" onClick={() => load(true)} disabled={busy || !role}>{busy ? "Searching…" : "Refresh live data"}</Button>
      </PageHeader>

      {err && <Alert title="Market search failed">{err}</Alert>}
      {busy && !data && <Spinner label="Querying Tavily…" />}

      {data?.status === "not_configured" && (
        <Alert tone="amber" title="Live web data is not configured">
          {data.message} Add <code className="rounded bg-amber-100 px-1">TAVILY_API_KEY</code> to the backend <code className="rounded bg-amber-100 px-1">.env</code> and restart the server. Nothing is shown in the meantime rather than inventing market data.
        </Alert>
      )}
      {data && ["empty", "error"].includes(data.status) && <Alert tone={data.status === "error" ? "red" : "amber"} title="No market insights available">{data.message}</Alert>}
      {data?.status === "partial" && <div className="mb-4"><Alert tone="amber">{data.message}</Alert></div>}

      {data && data.observed_sources.length > 0 && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <Badge tone="green">Observed from retrieved sources</Badge>
            {data.observed_sources.length} unique sources · retrieved {fmtDate(data.retrieved_at)}
            {data.queries.some((q) => q.cached) && <Badge>served from 24h cache</Badge>}
          </div>

          <div className="grid gap-6 lg:grid-cols-5">
            <Card className="lg:col-span-2" title="Skills mentioned across sources"
              subtitle="Count of retrieved sources whose title/snippet mentions each skill (taxonomy matching). Indigo = you have it, rose = gap.">
              {chart.length ? (
                <div className="h-96">
                  <ResponsiveContainer>
                    <BarChart data={chart} layout="vertical" margin={{ left: 24 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
                      <YAxis type="category" dataKey="skill" width={130} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(v) => [`${v} source(s)`, "Mentioned in"]} />
                      <Bar dataKey="sources" radius={[0, 4, 4, 0]}>
                        {chart.map((c) => <Cell key={c.skill} fill={c.has ? "#4f46e5" : "#f43f5e"} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : <p className="text-sm text-slate-500">No taxonomy skills were mentioned in the retrieved snippets.</p>}
              <p className="mt-2 text-xs text-slate-500">This is a count within this small set of search results, not a labor-market statistic.</p>
            </Card>

            <Card className="lg:col-span-3" title="Retrieved sources" subtitle="Factual excerpts exactly as returned by the search">
              <ul className="max-h-[28rem] space-y-4 overflow-y-auto pr-1">
                {data.observed_sources.map((s) => (
                  <li key={s.url} className="rounded-xl border border-slate-200 p-3">
                    <a href={s.url} target="_blank" rel="noreferrer" className="font-medium text-brand-700 hover:underline">{s.title}</a>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {s.domain}{s.published_date ? ` · published ${fmtDate(s.published_date)}` : ""} · retrieved {fmtDate(s.retrieved_at)}
                    </div>
                    <p className="mt-2 line-clamp-4 text-sm text-slate-600">{s.snippet || <i>No snippet provided.</i>}</p>
                    <div className="mt-1 text-[11px] text-slate-400">query: “{s.query}”</div>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <Card title="AI-generated interpretation" subtitle="LLM-written summaries produced by Tavily from the pages above. They can be wrong — verify against the sources."
            action={<Badge tone="violet">AI-generated</Badge>}>
            {data.ai_interpretation.length === 0 ? <p className="text-sm text-slate-500">No AI summary was returned.</p> : (
              <div className="space-y-4">
                {data.ai_interpretation.map((a, i) => (
                  <div key={i} className="rounded-xl border border-violet-200 bg-violet-50/50 p-4">
                    <div className="text-xs font-medium text-violet-700">Question: {a.query}</div>
                    <p className="mt-2 text-sm text-slate-700">{a.text}</p>
                    <div className="mt-2 text-xs text-slate-500">{a.generated_by} · based on {a.based_on_urls.length} source(s) · {fmtDate(a.retrieved_at)}</div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Search log">
            <ul className="space-y-1 text-sm">
              {data.queries.map((q) => (
                <li key={q.query} className="flex flex-wrap items-center gap-2">
                  <Badge tone={q.status === "ok" ? "green" : q.status === "empty" ? "amber" : "red"}>{q.status}</Badge>
                  <span className="text-slate-700">{q.query}</span>
                  <span className="text-xs text-slate-400">{q.results.length} results{q.cached ? " · cached" : ""}{q.message ? ` · ${q.message}` : ""}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
      {health && !health.tavily_configured && !data && !busy && (
        <Alert tone="amber" title="Live web data is not configured">Set TAVILY_API_KEY on the backend to enable this page.</Alert>
      )}
    </>
  );
}
