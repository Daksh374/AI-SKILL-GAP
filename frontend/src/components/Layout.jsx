import { useState } from "react";
import { NavLink } from "react-router-dom";
import { useApp } from "../context/AppContext.jsx";
import { Badge, RoleSelect, cx } from "./ui.jsx";

const NAV = [
  { to: "/", label: "Dashboard", icon: "M3 12l9-9 9 9M5 10v10h14V10" },
  { to: "/resume", label: "Resume Analysis", icon: "M7 3h7l5 5v13H7zM14 3v5h5M9 13h6M9 17h6" },
  { to: "/careers", label: "Career Recommendations", icon: "M4 19h16M6 16V9m6 7V5m6 11v-4" },
  { to: "/skill-gap", label: "Skill Gap Analysis", icon: "M12 3v18M3 12h18M5.6 5.6l12.8 12.8" },
  { to: "/market", label: "Market Intelligence", icon: "M3 17l6-6 4 4 8-8M15 7h6v6" },
  { to: "/learning-path", label: "Learning Path", icon: "M4 6h16M4 12h10M4 18h6M18 14l3 3-3 3" },
];

function Icon({ d }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

export default function Layout({ children }) {
  const { roles, role, setRole, resume, health } = useApp();
  const [open, setOpen] = useState(false);

  const nav = (
    <nav className="flex flex-col gap-1">
      {NAV.map((n) => (
        <NavLink key={n.to} to={n.to} end={n.to === "/"} onClick={() => setOpen(false)}
          className={({ isActive }) => cx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
            isActive ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900")}>
          <Icon d={n.icon} />
          {n.label}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[250px_1fr]">
      <aside className="hidden border-r border-slate-200 bg-white px-4 py-6 lg:block">
        <div className="mb-8 px-2">
          <div className="text-sm font-semibold uppercase tracking-wider text-brand-600">Career Engine</div>
          <div className="text-xs text-slate-500">Skill-gap & career intelligence</div>
        </div>
        {nav}
        {health && (
          <div className="mt-8 space-y-1.5 rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
            <div className="font-semibold text-slate-700">System status</div>
            <Status ok={health.model_trained} label="ML model" />
            <Status ok={health.spacy_model_loaded} label="spaCy NER" />
            <Status ok={health.tavily_configured} label="Tavily (live web)" />
          </div>
        )}
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur sm:px-8">
          <button className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setOpen(!open)} aria-label="Menu">
            <Icon d="M4 6h16M4 12h16M4 18h16" />
          </button>
          <div className="min-w-0 flex-1 truncate text-sm text-slate-500">
            {resume ? (
              <>Analysing <span className="font-medium text-slate-800">{resume.profile?.name || resume.resume.filename}</span></>
            ) : "No resume selected"}
          </div>
          {roles.length > 0 && (
            <label className="flex items-center gap-2 text-sm text-slate-500">
              <span className="hidden sm:inline">Target role</span>
              <RoleSelect value={role} onChange={setRole} roles={roles} />
            </label>
          )}
        </header>
        {open && <div className="border-b border-slate-200 bg-white p-3 lg:hidden">{nav}</div>}
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-8">{children}</main>
      </div>
    </div>
  );
}

function Status({ ok, label }) {
  return (
    <div className="flex items-center justify-between">
      <span>{label}</span>
      <Badge tone={ok ? "green" : "amber"}>{ok ? "ready" : "off"}</Badge>
    </div>
  );
}
