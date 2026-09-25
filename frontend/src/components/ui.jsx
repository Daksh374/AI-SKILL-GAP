import { Link } from "react-router-dom";

export const cx = (...c) => c.filter(Boolean).join(" ");
export const pct = (v, digits = 0) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`);

export function Card({ title, subtitle, action, children, className = "" }) {
  return (
    <section className={cx("rounded-2xl border border-slate-200 bg-white p-5 shadow-sm", className)}>
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-base font-semibold text-slate-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
          </div>
          {action && <div className="shrink-0 whitespace-nowrap">{action}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

const TONES = {
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  brand: "bg-brand-50 text-brand-700 ring-brand-100",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-rose-50 text-rose-700 ring-rose-200",
  sky: "bg-sky-50 text-sky-700 ring-sky-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
};

export function Badge({ tone = "slate", children, title, className = "" }) {
  return (
    <span title={title} className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset", TONES[tone], className)}>
      {children}
    </span>
  );
}

export function PriorityBadge({ priority }) {
  const tone = priority === "High" ? "red" : priority === "Medium" ? "amber" : priority === "Low" ? "sky" : "slate";
  return <Badge tone={tone}>{priority || "—"}</Badge>;
}

export function ProgressBar({ value, tone = "brand", label, className = "" }) {
  const color = { brand: "bg-brand-600", green: "bg-emerald-500", amber: "bg-amber-500", red: "bg-rose-500", sky: "bg-sky-500" }[tone];
  const v = Math.max(0, Math.min(1, value || 0));
  return (
    <div className={className}>
      {label && (
        <div className="mb-1 flex justify-between text-xs text-slate-500">
          <span>{label}</span>
          <span className="font-medium text-slate-700">{pct(v)}</span>
        </div>
      )}
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
        <div className={cx("h-full rounded-full transition-all", color)} style={{ width: `${v * 100}%` }} />
      </div>
    </div>
  );
}

export function Stat({ label, value, hint, tone = "slate" }) {
  const color = { slate: "text-slate-900", brand: "text-brand-700", green: "text-emerald-700", amber: "text-amber-700" }[tone];
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold", color)}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600" />
      {label}
    </div>
  );
}

export function Alert({ tone = "red", title, children }) {
  const styles = {
    red: "border-rose-200 bg-rose-50 text-rose-800",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    sky: "border-sky-200 bg-sky-50 text-sky-900",
    slate: "border-slate-200 bg-slate-50 text-slate-700",
  }[tone];
  return (
    <div className={cx("rounded-xl border px-4 py-3 text-sm", styles)}>
      {title && <div className="mb-0.5 font-semibold">{title}</div>}
      {children}
    </div>
  );
}

export function Button({ children, variant = "primary", className = "", ...props }) {
  const styles = {
    primary: "bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-500/60",
    secondary: "bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:opacity-60",
    ghost: "text-slate-600 hover:bg-slate-100",
  }[variant];
  return (
    <button className={cx("inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed", styles, className)} {...props}>
      {children}
    </button>
  );
}

export function NeedResume() {
  return (
    <Card>
      <div className="flex flex-col items-center gap-3 py-10 text-center">
        <div className="text-lg font-semibold text-slate-900">No resume analysed yet</div>
        <p className="max-w-md text-sm text-slate-500">Upload a PDF or DOCX resume to extract your skills, rank suitable roles and build a learning path.</p>
        <Link to="/resume" className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">Upload a resume</Link>
      </div>
    </Card>
  );
}

export function RoleSelect({ value, onChange, roles, className = "" }) {
  const groups = roles.reduce((acc, r) => ({ ...acc, [r.category]: [...(acc[r.category] || []), r] }), {});
  return (
    <select value={value || ""} onChange={(e) => onChange(e.target.value)}
      className={cx("rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100", className)}>
      {Object.entries(groups).map(([cat, rs]) => (
        <optgroup key={cat} label={cat}>
          {rs.map((r) => <option key={r.role} value={r.role}>{r.role}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

export function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function PageHeader({ title, description, children }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-slate-500">{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}
