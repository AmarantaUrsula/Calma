import { useEffect, useState } from "react";
import { api, errText, money } from "../api";
import FundRules, { ConfirmBanner, RulesView } from "./FundRules";
import { ClinicPartnerships, Partnership } from "./Partnerships";
import Reports from "./Reports";
import { answerRows, Badge, DecisionControls, DueBadge, StaffShell } from "./Staff";

type Pledge = {
  id: number; case_ref: string; fund_name: string; fund_kind: string; suggested_amount: number;
  approved_amount: number | null; status: string; reasons: string[]; category: "procedure" | "practical";
  decide_by: string | null; overdue: boolean;
};
type Case = {
  id: number; case_ref: string; appointment_date: string; procedure_cost: number; status: string;
  language: string; contact_method: string; patient_path: string | null; pledges: Pledge[];
  approved_total: number; patient_owes: number; practical_approved: number;
  screening?: Record<string, unknown> & { monthly_income: number; income_fpl_pct: number };
  contact?: { first_name: string | null; last_name: string | null; phone: string | null; email: string | null; notify_pref: string | null } | null;
  not_matched?: { fund_name: string; reasons: string[] }[];
};
type Summary = {
  clinic: { name: string; city: string; state: string; phone: string };
  own_funds: { id: number; name: string; monthly_limit: number; used_this_month: number; left_this_month: number }[];
  partner_funds: { id: number; name: string; description: string }[];
};
type Owed = Pledge & { appointment_date: string; case_status: string };

export default function Clinic() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [owed, setOwed] = useState<Owed[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [tab, setTab] = useState<"cases" | "reimb" | "rules" | "questions" | "partners" | "reports">("cases");
  const [partners, setPartners] = useState<Partnership[]>([]);
  const [fundRules, setFundRules] = useState<RulesView[]>([]);
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const [s, c, o] = await Promise.all([
        api<Summary>("/api/clinic/summary"), api<Case[]>("/api/clinic/cases"), api<Owed[]>("/api/clinic/reimbursements"),
      ]);
      setSummary(s); setCases(c); setOwed(o);
      setFundRules(await Promise.all(s.own_funds.map((f) => api<RulesView>(`/api/clinic/funds/${f.id}/rules`))));
      setPartners(await api<Partnership[]>("/api/clinic/partnerships"));
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);

  if (!summary) return <StaffShell title="Clinic portal"><p className="muted">{err || "Loading…"}</p></StaffShell>;
  const needs = cases.reduce((n, c) => n + c.pledges.filter((p) => p.fund_kind === "clinic" && p.status === "pending").length, 0);

  return (
    <StaffShell title={summary.clinic.name} subtitle={`Clinic portal · ${summary.clinic.city}, ${summary.clinic.state} · ${summary.clinic.phone}`}>
      <div className="stat-row">
        {summary.own_funds.map((f) => (
          <div key={f.id} className="stat">
            <div className="muted small">{f.name} · this month</div>
            <div className="stat-num">{money(f.left_this_month)} <span className="muted small">left of {money(f.monthly_limit)}</span></div>
            <div className="meter"><div style={{ width: `${Math.min(100, (f.used_this_month / f.monthly_limit) * 100)}%` }} /></div>
          </div>
        ))}
        <div className="stat"><div className="muted small">Your fund's pledges needing a decision</div><div className="stat-num">{needs}</div></div>
        <div className="stat"><div className="muted small">Partner funds</div><div className="small">{summary.partner_funds.map((f) => f.name).join(", ")}</div></div>
      </div>

      {fundRules.map((v) => (
        <ConfirmBanner key={v.fund_id} view={v} base={`/api/clinic/funds/${v.fund_id}/rules`} who="Your patients are"
          onConfirmed={() => load()} onEdit={() => setTab("rules")} />
      ))}

      {partners.some((p) => p.status === "pending") && (
        <div className="nudge" role="status">
          <div><strong>{partners.filter((p) => p.status === "pending").map((p) => p.fund_name).join(", ")}</strong> asked to partner with your clinic.</div>
          <button className="btn small-btn" onClick={() => setTab("partners")}>Review</button>
        </div>
      )}

      <NewAppointment onCreated={load} />

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "cases"} onClick={() => setTab("cases")}>Cases ({cases.length})</button>
        <button role="tab" aria-selected={tab === "reimb"} onClick={() => setTab("reimb")}>Reimbursement</button>
        <button role="tab" aria-selected={tab === "reports"} onClick={() => setTab("reports")}>Reports</button>
        <button role="tab" aria-selected={tab === "partners"} onClick={() => setTab("partners")}>Partner funds{partners.some((p) => p.status === "pending") ? " •" : ""}</button>
        <button role="tab" aria-selected={tab === "questions"} onClick={() => setTab("questions")}>Intake questions</button>
        <button role="tab" aria-selected={tab === "rules"} onClick={() => setTab("rules")}>Our fund's rules{fundRules.some((v) => v.needs_confirm) ? " •" : ""}</button>
      </div>

      {tab === "questions" && <IntakeQuestions />}

      {tab === "reports" && <Reports />}

      {tab === "partners" && <ClinicPartnerships rows={partners} onChange={load} />}

      {tab === "rules" && fundRules.map((v) => (
        <div key={v.fund_id}>
          <h2 className="section-title">{v.fund_name}</h2>
          <MonthlyLimit view={v} onSaved={load} />
          <FundRules view={v} base={`/api/clinic/funds/${v.fund_id}/rules`} onSaved={() => load()} />
        </div>
      ))}

      {tab === "cases" && (
        <div className="split">
          <table className="grid">
            <thead><tr><th>Case</th><th>Visit</th><th>Status</th><th className="num">Cost</th><th className="num">Help approved</th><th className="num">Patient pays</th><th>Pledges</th></tr></thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id} className={selected === c.id ? "sel" : ""} onClick={() => setSelected(c.id)} tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && setSelected(c.id)}>
                  <td className="mono">{c.case_ref}</td>
                  <td>{c.appointment_date}</td>
                  <td><Badge status={c.status} /></td>
                  <td className="num">{money(c.procedure_cost)}</td>
                  <td className="num">{money(c.approved_total)}</td>
                  <td className="num">{c.status === "link_sent" ? "—" : money(c.patient_owes)}</td>
                  <td>{c.pledges.map((p) => <span key={p.id} className={`dot ${p.status}`} title={`${p.fund_name}: ${p.status}`} />)}</td>
                </tr>
              ))}
              {!cases.length && <tr><td colSpan={7} className="muted">No cases yet. Book an appointment above.</td></tr>}
            </tbody>
          </table>
          {selected && <CaseDetail id={selected} onChange={load} key={selected + JSON.stringify(cases.find((c) => c.id === selected)?.pledges.map((p) => p.status))} />}
        </div>
      )}

      {tab === "reimb" && (
        <div className="card">
          <h2>Pledges from partner funds</h2>
          <p className="muted small">"Owed" means the fund approved it and the visit is done or coming up. The fund marks it paid when it sends the money.</p>
          <table className="grid">
            <thead><tr><th>Case</th><th>Fund</th><th>Visit</th><th className="num">Amount</th><th>Status</th></tr></thead>
            <tbody>
              {owed.map((o) => (
                <tr key={o.id}>
                  <td className="mono">{o.case_ref}</td><td>{o.fund_name}</td><td>{o.appointment_date}</td>
                  <td className="num">{money(o.approved_amount)}</td>
                  <td>{o.status === "paid" ? <Badge status="paid" /> : o.case_status === "screened" ? <span className="badge approved">Approved · visit upcoming</span> : <span className="badge owed">Owed</span>}</td>
                </tr>
              ))}
              {!owed.length && <tr><td colSpan={5} className="muted">Nothing yet.</td></tr>}
            </tbody>
            {owed.length > 0 && (
              <tfoot><tr><td colSpan={3}>Total still owed (visit done)</td>
                <td className="num">{money(owed.filter((o) => o.status === "approved" && o.case_status !== "screened").reduce((n, o) => n + (o.approved_amount ?? 0), 0))}</td><td /></tr></tfoot>
            )}
          </table>
        </div>
      )}
    </StaffShell>
  );
}

function NewAppointment({ onCreated }: { onCreated: () => void }) {
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  const [date, setDate] = useState(tomorrow);
  const [cost, setCost] = useState(900);
  const [method, setMethod] = useState<"text" | "email">("text");
  const [lang, setLang] = useState<"en" | "es">("en");
  const [link, setLink] = useState<{ ref: string; path: string } | null>(null);
  const [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr("");
    try {
      const r = await api<{ case_ref: string; patient_path: string }>("/api/clinic/cases", {
        body: { appointment_date: date, procedure_cost: cost, contact_method: method, language: lang },
      });
      setLink({ ref: r.case_ref, path: r.patient_path });
      onCreated();
    } catch (e) { setErr(errText(e)); }
  };
  return (
    <form className="card new-appt" onSubmit={submit}>
      <h2>New appointment → send screening link</h2>
      <div className="form-row">
        <label>Visit date<input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></label>
        <label>Procedure cost ($)<input className="input" type="number" min={1} value={cost} onChange={(e) => setCost(Number(e.target.value))} required /></label>
        <label>Send by<select className="input" value={method} onChange={(e) => setMethod(e.target.value as "text" | "email")}><option value="text">Text</option><option value="email">Email</option></select></label>
        <label>Language<select className="input" value={lang} onChange={(e) => setLang(e.target.value as "en" | "es")}><option value="en">English</option><option value="es">Español</option></select></label>
        <button className="btn" type="submit">Create link</button>
      </div>
      {err && <p className="error small">{err}</p>}
      {link && (
        <div className="sent">
          <span className="muted small">Demo: a real version would {method} this to the patient. The message would say only "Answer a few questions before your visit" plus the link, with no mention of abortion.</span>
          <div><strong>{link.ref}</strong> · <a href={link.path} target="_blank" rel="noreferrer">Open patient link ↗</a></div>
        </div>
      )}
    </form>
  );
}

function CaseDetail({ id, onChange }: { id: number; onChange: () => void }) {
  const [c, setC] = useState<Case | null>(null);
  const [err, setErr] = useState("");
  const load = () => api<Case>(`/api/clinic/cases/${id}`).then(setC).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, [id]);
  if (!c) return <div className="card detail"><p className="muted">{err || "Loading…"}</p></div>;
  const refresh = () => { load(); onChange(); };
  const done = async () => {
    try { await api(`/api/clinic/cases/${id}/appointment-done`, { method: "POST" }); refresh(); }
    catch (e) { setErr(errText(e)); }
  };
  const s = c.screening;
  return (
    <div className="card detail">
      <h2>{c.case_ref} · visit {c.appointment_date}</h2>
      {c.status === "link_sent" && (
        <p className="muted">Waiting for the patient to fill out the form. <a href={c.patient_path!} target="_blank" rel="noreferrer">Open patient link ↗</a></p>
      )}
      {s && (
        <table className="kv small"><tbody>
          {answerRows(s).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}
          <tr><td>Income</td><td>{money(s.monthly_income)}/mo · {s.income_fpl_pct}% of poverty line</td></tr>
          <tr><td>Language</td><td>{c.language === "es" ? "Español" : "English"}</td></tr>
        </tbody></table>
      )}
      {c.contact && (
        <div className="contact-box small">
          <strong>Contact (clinic only)</strong>{" "}
          {[c.contact.first_name, c.contact.last_name].filter(Boolean).join(" ") || "—"}
          {c.contact.phone && <> · {c.contact.phone}</>}{c.contact.email && <> · {c.contact.email}</>}
          {c.contact.notify_pref && <> · prefers {c.contact.notify_pref}</>}
          <div className="muted">Never shared with funds. Deleted when the case closes.</div>
        </div>
      )}
      {c.pledges.length > 0 && <h3>Matched funds</h3>}
      {c.pledges.map((p) => (
        <div key={p.id} className="pledge-card">
          <div className="pledge-head">
            <strong>{p.fund_name}</strong>
            <span className="muted small">{p.fund_kind === "clinic" ? "your fund" : "partner fund"}{p.category === "practical" && " · travel/practical help (paid to patient, not the bill)"}</span>
            <span className="right">{money(p.approved_amount ?? p.suggested_amount)} <Badge status={p.status} /></span>
            {p.status === "pending" && <span className="due-row"><DueBadge decideBy={p.decide_by} overdue={p.overdue} /></span>}
          </div>
          <ul className="reasons">{p.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          {p.fund_kind === "clinic" && p.status === "pending" && (
            <DecisionControls p={p} path={`/api/clinic/pledges/${p.id}/decide`} onDone={refresh} />
          )}
          {p.fund_kind !== "clinic" && p.status === "pending" && <p className="muted small">Waiting for {p.fund_name} to decide.</p>}
        </div>
      ))}
      {c.not_matched && c.not_matched.length > 0 && (
        <details>
          <summary className="small">Funds that didn't match ({c.not_matched.length})</summary>
          <ul className="reasons">{c.not_matched.map((n) => <li key={n.fund_name}><strong>{n.fund_name}:</strong> {n.reasons.join("; ")}</li>)}</ul>
        </details>
      )}
      {s && (
        <div className="totals-mini">
          Cost {money(c.procedure_cost)} − approved {money(c.approved_total)} = <strong>patient pays {money(c.patient_owes)}</strong>
          {c.practical_approved > 0 && <> · plus {money(c.practical_approved)} travel/practical help approved</>}
        </div>
      )}
      {c.status === "screened" && <button className="btn ghost" onClick={done}>Mark visit done</button>}
      {err && <p className="error small">{err}</p>}
    </div>
  );
}

function MonthlyLimit({ view, onSaved }: { view: RulesView; onSaved: () => void }) {
  const [val, setVal] = useState(view.monthly_limit ?? 0);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  useEffect(() => { setVal(view.monthly_limit ?? 0); }, [view.monthly_limit]);
  const save = async () => {
    setErr(""); setOk("");
    try {
      await api(`/api/clinic/funds/${view.fund_id}/monthly-limit`, { method: "PUT", body: { monthly_limit: val } });
      setOk("Saved."); onSaved();
    } catch (e) { setErr(errText(e)); }
  };
  return (
    <div className="card">
      <h2>Monthly limit (block grant)</h2>
      <div className="inline-field">
        Your fund can pledge up to $
        <input className="input amt" type="number" min={0} value={val} onChange={(e) => { setVal(Number(e.target.value)); setOk(""); }} aria-label="Monthly limit" />
        each month.
        <button className="btn small-btn" disabled={val === view.monthly_limit} onClick={save}>Save limit</button>
        {ok && <span className="ok small">{ok}</span>}
        <div className="muted small">Used so far this month: {money(view.used_this_month)}. Calma won't let staff approve past this limit.</div>
      </div>
      {err && <p className="error small" role="alert">{err}</p>}
    </div>
  );
}

type QCatalog = { id: string; group: string; label: string; fund_askable: boolean }[];

function IntakeQuestions() {
  const [d, setD] = useState<{ asked: string[]; why: Record<string, string[]>; clinic_extras: string[]; catalog: QCatalog } | null>(null);
  const [err, setErr] = useState("");
  const load = () => api<typeof d>("/api/clinic/questions").then(setD).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  if (!d) return <p className="muted">{err || "Loading…"}</p>;
  const toggle = async (q: string, on: boolean) => {
    const extras = on ? [...d.clinic_extras, q] : d.clinic_extras.filter((x) => x !== q);
    try { setD(await api<typeof d>("/api/clinic/questions", { method: "PUT", body: { extra_questions: extras } })); }
    catch (e) { setErr(errText(e)); }
  };
  const fromFunds = (q: string) => (d.why[q] ?? []).filter((w) => !w.endsWith("(clinic)"));
  return (
    <div className="card">
      <h2>What your patients are asked</h2>
      <p className="muted small">
        Patients see the core questions, plus any question a matching fund needs or asked for, plus any you turn on below.
        Every extra question can be skipped by the patient. State of care isn't asked: it's your clinic's state.
        Right now your patients see <strong>{d.asked.length}</strong> of {d.catalog.length} questions.
      </p>
      {err && <p className="error small">{err}</p>}
      <table className="grid">
        <thead><tr><th>Question</th><th>Asked?</th><th>Why</th><th>Ask our patients</th></tr></thead>
        <tbody>
          {d.catalog.map((q) => {
            const asked = d.asked.includes(q.id);
            const mine = d.clinic_extras.includes(q.id);
            return (
              <tr key={q.id}>
                <td>{q.label}{q.id === "contact" && <div className="muted small">Only your clinic sees these. Funds never do.</div>}</td>
                <td>{asked ? <span className="badge approved">Asked</span> : <span className="badge declined">Not asked</span>}</td>
                <td className="small muted">{q.group === "core" ? "Always asked" : fromFunds(q.id).join("; ") || (mine ? "" : "—")}</td>
                <td>{q.group === "core" ? <span className="muted small">Always</span> : (
                  <label className="check-inline"><input type="checkbox" checked={mine} onChange={(e) => toggle(q.id, e.target.checked)} aria-label={`Ask: ${q.label}`} /> {mine ? "On" : "Off"}</label>
                )}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
