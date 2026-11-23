import { useEffect, useMemo, useRef, useState } from "react";
import { api, errText, getToken, money } from "../api";

// Reports for every staff role. Numbers always come from Calma's report engine (no AI).
// The "Describe a report" box asks the Report Builder agent to choose the settings only.

type Opt = { id: string; label: string };
type Options = { dimensions: Opt[]; measures: Opt[]; date_bases: Opt[]; scope_name: string; today: string };
type Group = { keys: string[]; amount: number; patients: number; pledges: number; small: boolean };
type Result = { groups: Group[]; total_amount: number; total_patients: number; total_pledges: number; group_by: string[]; labels: string[] };
type Params = { measure: string; date_basis: string; start: string; end: string; group_by: string[] };
type View = "table" | "bar" | "pie";
type Value = "amount" | "patients";

// Categorical palette, validated for color-vision deficiency and contrast (see styles.css).
const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)", "var(--series-6)"];
const OTHER = "var(--series-other)";
const MAX_SERIES = 6;

function iso(d: Date) { return d.toISOString().slice(0, 10); }
function presets(todayIso: string): Record<string, [string, string]> {
  const t = new Date(todayIso + "T12:00:00");
  const y = t.getFullYear(), m = t.getMonth();
  const q = Math.floor(m / 3) * 3;
  const back = (months: number) => { const d = new Date(t); d.setMonth(d.getMonth() - months); return iso(d); };
  return {
    "This month": [iso(new Date(y, m, 1)), todayIso],
    "Last month": [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))],
    "This quarter": [iso(new Date(y, q, 1)), todayIso],
    "Last 3 months": [back(3), todayIso],
    "Last 6 months": [back(6), todayIso],
    "This year": [iso(new Date(y, 0, 1)), todayIso],
    "Last 12 months": [back(12), todayIso],
  };
}
const fmt = (v: number, value: Value) => (value === "amount" ? money(v) : `${v} patient${v === 1 ? "" : "s"}`);

export default function Reports() {
  const [opts, setOpts] = useState<Options | null>(null);
  const [p, setP] = useState<Params | null>(null);
  const [preset, setPreset] = useState("Last 6 months");
  const [view, setView] = useState<View>("bar");
  const [value, setValue] = useState<Value>("amount");
  const [res, setRes] = useState<Result | null>(null);
  const [err, setErr] = useState("");
  const [ask, setAsk] = useState("");
  const [asking, setAsking] = useState(false);
  const [askNote, setAskNote] = useState<{ title: string; notes: string[] } | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    api<Options>("/api/reports/options").then((o) => {
      setOpts(o);
      const [start, end] = presets(o.today)["Last 6 months"];
      setP({ measure: "disbursed", date_basis: "paid", start, end, group_by: [o.dimensions.find((d) => d.id === "month") ? "month" : o.dimensions[0].id] });
    }).catch((e) => setErr(errText(e)));
  }, []);

  useEffect(() => {
    if (!p) return;
    const id = setTimeout(() => {
      api<Result>("/api/reports/run", { body: p }).then((r) => { setRes(r); setErr(""); }).catch((e) => setErr(errText(e)));
    }, 150);
    return () => clearTimeout(id);
  }, [p]);

  if (!opts || !p) return <p className="muted">{err || "Loading reports…"}</p>;
  const set = (x: Partial<Params>) => { setP({ ...p, ...x }); setAskNote(null); };
  const setDim = (i: number, id: string) => {
    const by = [...p.group_by];
    if (id === "") by.splice(i); else by[i] = id;
    const clean = by.filter((d, j) => d && by.indexOf(d) === j).slice(0, 3);
    set({ group_by: clean });
    if (clean.length !== 1 && view === "pie") setView(clean.length === 0 || clean.length > 2 ? "table" : "bar");
    if (clean.length > 2 && view === "bar") setView("table");
  };
  const choosePreset = (name: string) => {
    setPreset(name);
    if (name !== "Custom") { const [start, end] = presets(opts.today)[name]; set({ start, end }); }
  };

  const runAsk = async (e: React.FormEvent) => {
    e.preventDefault(); if (!ask.trim()) return;
    setAsking(true); setErr("");
    try {
      const r = await api<{ spec: Params & { view: View; chart_value: Value; title: string }; notes: string[]; result: Result }>("/api/reports/ask", { body: { request: ask } });
      setP({ measure: r.spec.measure, date_basis: r.spec.date_basis, start: r.spec.start, end: r.spec.end, group_by: r.spec.group_by });
      setPreset("Custom"); setView(r.spec.view); setValue(r.spec.chart_value); setRes(r.result);
      setAskNote({ title: r.spec.title, notes: r.notes });
    } catch (e) { setErr(errText(e)); } finally { setAsking(false); }
  };

  const download = async () => {
    setDownloading(true); setErr("");
    try {
      const r = await fetch("/api/reports/export", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify(p) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail ?? "Download failed.");
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = /filename="([^"]+)"/.exec(r.headers.get("content-disposition") ?? "")?.[1] ?? "calma-report.xlsx";
      a.click(); URL.revokeObjectURL(a.href);
    } catch (e) { setErr(errText(e)); } finally { setDownloading(false); }
  };

  const dimLabel = (id: string) => opts.dimensions.find((d) => d.id === id)?.label ?? id;
  const measureLabel = opts.measures.find((m) => m.id === p.measure)?.label ?? "";
  const n = p.group_by.length;
  const canBar = n >= 1 && n <= 2, canPie = n === 1;

  return (
    <div className="reports">
      <form className="card ask-card" onSubmit={runAsk}>
        <h2>Describe the report you want</h2>
        <div className="ask-row">
          <input className="input" value={ask} onChange={(e) => setAsk(e.target.value)} maxLength={500}
            placeholder='e.g. "bar chart of money paid out by month and type of help this year"' aria-label="Describe the report you want" />
          <button className="btn" disabled={asking || ask.trim().length < 3}>{asking ? "Building…" : "Build report"}</button>
        </div>
        <p className="muted small">The AI only picks the settings below. It never sees patient information, and all numbers are calculated by Calma. You can change any setting afterward.</p>
        {askNote && (
          <div className="ask-result small">
            <strong>{askNote.title}</strong>
            {askNote.notes.map((x) => <div key={x} className="muted">{x}</div>)}
          </div>
        )}
      </form>

      <div className="card controls-card">
        <div className="controls">
          <label>Period
            <select className="input" value={preset} onChange={(e) => choosePreset(e.target.value)}>
              {[...Object.keys(presets(opts.today)), "Custom"].map((k) => <option key={k}>{k}</option>)}
            </select>
          </label>
          <label>From<input className="input" type="date" value={p.start} max={p.end} onChange={(e) => { setPreset("Custom"); set({ start: e.target.value }); }} /></label>
          <label>To<input className="input" type="date" value={p.end} min={p.start} onChange={(e) => { setPreset("Custom"); set({ end: e.target.value }); }} /></label>
          <label>Measure
            <select className="input" value={p.measure} onChange={(e) => set({ measure: e.target.value, date_basis: e.target.value === "pledged" ? "approved" : "paid" })}>
              {opts.measures.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </label>
          <label>Dates are
            <select className="input" value={p.date_basis} onChange={(e) => set({ date_basis: e.target.value })}>
              {opts.date_bases.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
            </select>
          </label>
        </div>
        <div className="controls">
          {[0, 1, 2].map((i) => (
            <label key={i}>{i === 0 ? "Group by" : i === 1 ? "Then by" : "And by"}
              <select className="input" value={p.group_by[i] ?? ""} disabled={i > n} onChange={(e) => setDim(i, e.target.value)}>
                <option value="">{i === 0 ? "No grouping (total only)" : "—"}</option>
                {opts.dimensions.filter((d) => d.id === p.group_by[i] || !p.group_by.includes(d.id)).map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
              </select>
            </label>
          ))}
          <div className="view-toggle" role="group" aria-label="Show as">
            <span className="small muted">Show as</span>
            <div className="lang-toggle">
              <button type="button" aria-pressed={view === "table"} onClick={() => setView("table")}>Table</button>
              <button type="button" aria-pressed={view === "bar"} disabled={!canBar} title={canBar ? "" : "Bar charts use 1 or 2 criteria"} onClick={() => setView("bar")}>Bar</button>
              <button type="button" aria-pressed={view === "pie"} disabled={!canPie} title={canPie ? "" : "Pie charts use exactly 1 criterion"} onClick={() => setView("pie")}>Pie</button>
            </div>
          </div>
          {view !== "table" && (
            <div className="view-toggle" role="group" aria-label="Chart shows">
              <span className="small muted">Chart shows</span>
              <div className="lang-toggle">
                <button type="button" aria-pressed={value === "amount"} onClick={() => setValue("amount")}>Dollars</button>
                <button type="button" aria-pressed={value === "patients"} onClick={() => setValue("patients")}>Patients</button>
              </div>
            </div>
          )}
          <button type="button" className="btn ghost right" disabled={downloading} onClick={download}>{downloading ? "Preparing…" : "Download Excel"}</button>
        </div>
      </div>

      {err && <p className="error" role="alert">{err}</p>}

      {res && (
        <>
          <div className="stat-row">
            <div className="stat"><div className="muted small">{measureLabel}</div><div className="stat-num">{money(res.total_amount)}</div></div>
            <div className="stat"><div className="muted small">Patients helped</div><div className="stat-num">{res.total_patients}</div></div>
            <div className="stat"><div className="muted small">Pledges</div><div className="stat-num">{res.total_pledges}</div></div>
            <div className="stat"><div className="muted small">Organization</div><div className="small">{opts.scope_name}<br /><span className="muted">{p.start} to {p.end}</span></div></div>
          </div>
          <div className="card">
            <h2>{measureLabel}{n ? ` by ${res.labels.map((l) => l.toLowerCase()).join(", then ")}` : ""}</h2>
            {res.groups.length === 0 ? <p className="muted">Nothing in this period. Try a longer period or a different measure.</p>
              : view === "bar" && canBar ? (n === 1 ? <Bars groups={res.groups} value={value} /> : <StackedBars groups={res.groups} value={value} label2={dimLabel(p.group_by[1])} />)
              : view === "pie" && canPie ? <Pie groups={res.groups} value={value} />
              : <Table res={res} />}
            {view !== "table" && res.groups.length > 0 && (
              <details className="table-toggle"><summary className="small">Show as a table</summary><Table res={res} /></details>
            )}
            {res.groups.some((g) => g.small) && <p className="muted small">* Fewer than 5 patients. Small groups can point to a specific person, so take care when sharing.</p>}
          </div>
        </>
      )}
    </div>
  );
}

function Table({ res }: { res: Result }) {
  return (
    <table className="grid report-table">
      <thead><tr>{res.labels.map((l) => <th key={l}>{l}</th>)}<th className="num">Amount</th><th className="num">Patients</th><th className="num">Pledges</th></tr></thead>
      <tbody>
        {res.groups.map((g, i) => (
          <tr key={i}>{g.keys.map((k, j) => <td key={j}>{k}</td>)}<td className="num">{money(g.amount)}</td><td className="num">{g.patients}{g.small ? " *" : ""}</td><td className="num">{g.pledges}</td></tr>
        ))}
      </tbody>
      <tfoot><tr><td colSpan={Math.max(1, res.labels.length)}>Total</td><td className="num">{money(res.total_amount)}</td><td className="num">{res.total_patients}</td><td className="num">{res.total_pledges}</td></tr></tfoot>
    </table>
  );
}

// ---------- charts (plain SVG/HTML) ----------

function useTip() {
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const show = (e: React.MouseEvent, text: string) => {
    const r = ref.current?.getBoundingClientRect();
    if (r) setTip({ x: e.clientX - r.left + 12, y: e.clientY - r.top + 12, text });
  };
  const node = tip && <div className="chart-tip" style={{ left: tip.x, top: tip.y }}>{tip.text}</div>;
  return { ref, show, hide: () => setTip(null), node };
}

/** One criterion: horizontal bars, one color (a single series needs no legend). */
function Bars({ groups, value }: { groups: Group[]; value: Value }) {
  const t = useTip();
  const max = Math.max(...groups.map((g) => g[value]), 1);
  return (
    <div className="hbars" ref={t.ref} onMouseLeave={t.hide}>
      {groups.map((g, i) => (
        <div key={i} className="hbar-row" onMouseMove={(e) => t.show(e, `${g.keys[0]}: ${money(g.amount)} · ${g.patients} patients · ${g.pledges} pledges`)}>
          <span className="hbar-label">{g.keys[0]}{g.small ? " *" : ""}</span>
          <span className="hbar-track"><span className="hbar" style={{ width: `${(g[value] / max) * 100}%`, background: SERIES[0] }} /></span>
          <span className="hbar-value">{fmt(g[value], value)}</span>
        </div>
      ))}
      {t.node}
    </div>
  );
}

/** Two criteria: one bar per first criterion, stacked by the second (top 6 + Other). */
function StackedBars({ groups, value, label2 }: { groups: Group[]; value: Value; label2: string }) {
  const t = useTip();
  const { rows, series, max } = useMemo(() => {
    const totals = new Map<string, number>();
    groups.forEach((g) => totals.set(g.keys[1], (totals.get(g.keys[1]) ?? 0) + g[value]));
    const ordered = [...totals.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k);
    const top = ordered.length > MAX_SERIES ? ordered.slice(0, MAX_SERIES - 1) : ordered;
    const series = ordered.length > MAX_SERIES ? [...top, "Other"] : top;
    const rowsMap = new Map<string, Map<string, number>>();
    groups.forEach((g) => {
      const s = top.includes(g.keys[1]) ? g.keys[1] : "Other";
      const m = rowsMap.get(g.keys[0]) ?? new Map<string, number>();
      m.set(s, (m.get(s) ?? 0) + g[value]);
      rowsMap.set(g.keys[0], m);
    });
    const rows = [...rowsMap.entries()].map(([k, m]) => ({ k, parts: series.map((s) => m.get(s) ?? 0) }));
    const isTime = /^\d{4}-(\d{2}|W\d{2})$/.test(rows[0]?.k ?? "");
    if (isTime) rows.sort((a, b) => a.k.localeCompare(b.k)); else rows.sort((a, b) => b.parts.reduce((x, y) => x + y) - a.parts.reduce((x, y) => x + y));
    return { rows, series, max: Math.max(...rows.map((r) => r.parts.reduce((x, y) => x + y, 0)), 1) };
  }, [groups, value]);
  const color = (i: number) => (series[i] === "Other" ? OTHER : SERIES[i]);
  return (
    <div ref={t.ref} onMouseLeave={t.hide} className="stacked">
      <div className="legend" aria-label={label2}>
        <span className="muted small">{label2}:</span>
        {series.map((s, i) => <span key={s} className="legend-item small"><span className="swatch" style={{ background: color(i) }} />{s}</span>)}
      </div>
      <div className="hbars">
        {rows.map((r) => {
          const total = r.parts.reduce((x, y) => x + y, 0);
          return (
            <div key={r.k} className="hbar-row">
              <span className="hbar-label">{r.k}</span>
              <span className="hbar-track">
                <span className="hbar-stack" style={{ width: `${(total / max) * 100}%` }}>
                  {r.parts.map((v, i) => v > 0 && (
                    <span key={i} className="seg" style={{ flexGrow: v, background: color(i) }}
                      onMouseMove={(e) => t.show(e, `${r.k} · ${series[i]}: ${fmt(v, value)}`)} />
                  ))}
                </span>
              </span>
              <span className="hbar-value">{fmt(total, value)}</span>
            </div>
          );
        })}
      </div>
      {t.node}
    </div>
  );
}

/** One criterion: pie with up to 6 slices (the rest fold into Other), legend with shares. */
function Pie({ groups, value }: { groups: Group[]; value: Value }) {
  const t = useTip();
  const sorted = [...groups].sort((a, b) => b[value] - a[value]);
  const slices = sorted.length > MAX_SERIES
    ? [...sorted.slice(0, MAX_SERIES - 1).map((g) => ({ k: g.keys[0], v: g[value] })), { k: "Other", v: sorted.slice(MAX_SERIES - 1).reduce((x, g) => x + g[value], 0) }]
    : sorted.map((g) => ({ k: g.keys[0], v: g[value] }));
  const total = slices.reduce((x, s) => x + s.v, 0) || 1;
  let a0 = -Math.PI / 2;
  const R = 110, C = 120;
  const arcs = slices.map((s, i) => {
    const a1 = a0 + (s.v / total) * Math.PI * 2;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (a: number) => `${C + R * Math.cos(a)} ${C + R * Math.sin(a)}`;
    const d = slices.length === 1 ? `M ${C} ${C - R} A ${R} ${R} 0 1 1 ${C - 0.01} ${C - R} Z` : `M ${C} ${C} L ${p(a0)} A ${R} ${R} 0 ${large} 1 ${p(a1)} Z`;
    a0 = a1;
    return { d, s, color: s.k === "Other" ? OTHER : SERIES[i] };
  });
  return (
    <div className="pie-wrap" ref={t.ref} onMouseLeave={t.hide}>
      <svg viewBox="0 0 240 240" width="240" height="240" role="img" aria-label="Pie chart">
        {arcs.map((a) => (
          <path key={a.s.k} d={a.d} fill={a.color} stroke="var(--panel)" strokeWidth={2}
            onMouseMove={(e) => t.show(e, `${a.s.k}: ${fmt(a.s.v, value)} (${Math.round((a.s.v / total) * 100)}%)`)} />
        ))}
      </svg>
      <ul className="pie-legend">
        {arcs.map((a) => (
          <li key={a.s.k} className="small"><span className="swatch" style={{ background: a.color }} /><span>{a.s.k}</span>
            <span className="muted">{fmt(a.s.v, value)} · {Math.round((a.s.v / total) * 100)}%</span></li>
        ))}
      </ul>
      {sorted.length > MAX_SERIES && <p className="muted small">Smaller groups are combined into "Other". A bar chart shows every group.</p>}
      {t.node}
    </div>
  );
}
