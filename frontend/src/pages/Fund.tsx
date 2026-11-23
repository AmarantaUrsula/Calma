import { useEffect, useState } from "react";
import { api, errText, money } from "../api";
import FundRules, { ConfirmBanner, RulesView } from "./FundRules";
import { FundPartnerships } from "./Partnerships";
import { answerRows, Badge, DecisionControls, StaffShell } from "./Staff";

type Item = {
  id: number; case_ref: string; fund_name: string; fund_kind: string; suggested_amount: number;
  approved_amount: number | null; status: string; reasons: string[]; clinic_name: string;
  appointment_date: string; case_status: string; state: string; household_size: number; income_fpl_pct: number;
  category: "procedure" | "practical"; answers: Record<string, unknown>;
};
type Summary = {
  fund: { name: string; description: string };
  partner_clinics: { id: number; name: string; city: string; state: string; phone: string }[];
  monthly_budget: number | null; approved_this_month: number;
  criteria: { states: string[]; income_max_fpl_pct: number | null; gest_min_weeks: number | null;
    gest_max_weeks: number | null; requires_travel: boolean; max_age: number | null;
    pledge_kind: string; pledge_value: number; pledge_cap: number | null; state_basis: string;
    support_type: string; no_insurance_only: boolean } | null;
};

export default function Fund() {
  const [s, setS] = useState<Summary | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [tab, setTab] = useState<"pending" | "approved" | "history" | "rules" | "partners">("pending");
  const [rulesView, setRulesView] = useState<RulesView | null>(null);
  const [err, setErr] = useState("");
  const load = async () => {
    try {
      const [a, b, r] = await Promise.all([api<Summary>("/api/fund/summary"), api<Item[]>("/api/fund/pledges"), api<RulesView>("/api/fund/rules")]);
      setS(a); setItems(b); setRulesView(r);
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);
  if (!s) return <StaffShell title="Fund portal"><p className="muted">{err || "Loading…"}</p></StaffShell>;

  const pending = items.filter((i) => i.status === "pending");
  const approved = items.filter((i) => i.status === "approved");
  const history = items.filter((i) => i.status === "paid" || i.status === "declined");
  const owedNow = approved.filter((i) => i.category === "procedure" && i.case_status !== "screened");
  const c = s.criteria;
  const markPaid = async (id: number) => {
    try { await api(`/api/fund/pledges/${id}/mark-paid`, { method: "POST" }); load(); }
    catch (e) { setErr(errText(e)); }
  };

  return (
    <StaffShell title={s.fund.name} subtitle={`Fund portal · ${s.fund.description}`}>
      <div className="stat-row">
        <div className="stat">
          <div className="muted small">Approved this month</div>
          <div className="stat-num">{money(s.approved_this_month)} {s.monthly_budget != null && <span className="muted small">of {money(s.monthly_budget)} budget</span>}</div>
          {s.monthly_budget != null && <div className="meter"><div style={{ width: `${Math.min(100, (s.approved_this_month / s.monthly_budget) * 100)}%` }} /></div>}
          <div className="muted small">You check the budget yourself before approving. Calma doesn't approve anything automatically.</div>
        </div>
        <div className="stat"><div className="muted small">Eligible patients waiting</div><div className="stat-num">{pending.length}</div></div>
        <div className="stat"><div className="muted small">You owe clinics (visit done)</div><div className="stat-num">{money(owedNow.reduce((n, i) => n + (i.approved_amount ?? 0), 0))}</div></div>
        <div className="stat"><div className="muted small">Partner clinics</div><div className="small">{s.partner_clinics.map((p) => `${p.name} (${p.state})`).join(", ")}</div></div>
      </div>
      {rulesView && <ConfirmBanner view={rulesView} onConfirmed={setRulesView} onEdit={() => setTab("rules")} />}
      {c && (
        <p className="muted small criteria-line">
          Your rules: {c.states.includes("*") ? "any state" : c.states.join(", ")}
          {c.income_max_fpl_pct != null && ` · income ≤ ${c.income_max_fpl_pct}% of poverty line`}
          {(c.gest_min_weeks != null || c.gest_max_weeks != null) && ` · ${c.gest_min_weeks ?? 0}–${c.gest_max_weeks ?? "any"} weeks`}
          {c.requires_travel && " · must travel"}
          {c.max_age != null && ` · age ≤ ${c.max_age}`}
          {c.state_basis === "care" && " · based on state of care"}
          {c.state_basis === "either" && " · lives in or gets care in"}
          {c.no_insurance_only && " · no insurance coverage"}
          {c.support_type === "practical" ? ` · travel/practical help up to ${money(c.pledge_cap)}` : <>{" · pledge: "}{c.pledge_kind === "fixed" ? money(c.pledge_value) : `${c.pledge_value}% up to ${money(c.pledge_cap)}`}</>}
          {rulesView && <> · v{rulesView.version}, confirmed {rulesView.days_since_confirmed === 0 ? "today" : `${rulesView.days_since_confirmed} days ago`} · <button className="link small" onClick={() => setTab("rules")}>edit</button></>}
        </p>
      )}
      {err && <p className="error">{err}</p>}

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "pending"} onClick={() => setTab("pending")}>Needs decision ({pending.length})</button>
        <button role="tab" aria-selected={tab === "approved"} onClick={() => setTab("approved")}>Approved / owed ({approved.length})</button>
        <button role="tab" aria-selected={tab === "history"} onClick={() => setTab("history")}>History ({history.length})</button>
        <button role="tab" aria-selected={tab === "partners"} onClick={() => setTab("partners")}>Partner clinics</button>
        <button role="tab" aria-selected={tab === "rules"} onClick={() => setTab("rules")}>My eligibility rules{rulesView?.needs_confirm ? " •" : ""}</button>
      </div>

      {tab === "partners" && <FundPartnerships onChange={load} />}

      {tab === "rules" && rulesView && (
        <FundRules view={rulesView} onSaved={(v) => { setRulesView(v); load(); }} />
      )}

      {tab === "pending" && (
        <div className="cards">
          {pending.map((i) => (
            <div key={i.id} className="card pledge-card">
              <div className="pledge-head">
                <strong className="mono">{i.case_ref}</strong>
                <span className="muted small">{i.clinic_name} · visit {i.appointment_date}</span>
                <span className="right">suggested {money(i.suggested_amount)}</span>
              </div>
              <div className="small muted">
                {i.category === "practical" && <span className="badge screened">Travel/practical help</span>}{" "}
                Household of {i.household_size} · income {i.income_fpl_pct}% of poverty line
              </div>
              <div className="answer-chips small">
                {answerRows(i.answers).filter(([k]) => k !== "Household").map(([k, v]) => <span key={k} className="ans"><span className="muted">{k}:</span> {v}</span>)}
              </div>
              <ul className="reasons">{i.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              <DecisionControls p={i} path={`/api/fund/pledges/${i.id}/decide`} onDone={load} />
            </div>
          ))}
          {!pending.length && <p className="muted">No patients waiting. New eligible patients from your partner clinics show up here.</p>}
        </div>
      )}

      {tab === "approved" && (
        <table className="grid">
          <thead><tr><th>Case</th><th>Clinic</th><th>Visit</th><th className="num">Amount</th><th>Status</th><th /></tr></thead>
          <tbody>
            {approved.map((i) => (
              <tr key={i.id}>
                <td className="mono">{i.case_ref}</td><td>{i.clinic_name}</td><td>{i.appointment_date}</td>
                <td className="num">{money(i.approved_amount)}</td>
                <td>{i.category === "practical" ? <span className="badge owed">Give to patient</span> : i.case_status === "screened" ? <span className="badge approved">Visit upcoming</span> : <span className="badge owed">Owed to clinic</span>}</td>
                <td>{(i.category === "practical" || i.case_status !== "screened") && <button className="btn small-btn" onClick={() => markPaid(i.id)}>{i.category === "practical" ? "Mark provided" : "Mark paid"}</button>}</td>
              </tr>
            ))}
            {!approved.length && <tr><td colSpan={6} className="muted">Nothing approved yet.</td></tr>}
          </tbody>
        </table>
      )}

      {tab === "history" && (
        <table className="grid">
          <thead><tr><th>Case</th><th>Clinic</th><th>Visit</th><th className="num">Amount</th><th>Status</th></tr></thead>
          <tbody>
            {history.map((i) => (
              <tr key={i.id}>
                <td className="mono">{i.case_ref}</td><td>{i.clinic_name}</td><td>{i.appointment_date}</td>
                <td className="num">{money(i.approved_amount)}</td><td><Badge status={i.status} /></td>
              </tr>
            ))}
            {!history.length && <tr><td colSpan={5} className="muted">No history yet.</td></tr>}
          </tbody>
        </table>
      )}
    </StaffShell>
  );
}
