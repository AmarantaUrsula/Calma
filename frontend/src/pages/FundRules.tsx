import { useEffect, useMemo, useState } from "react";
import { api, errText, money } from "../api";
import { STATE_NAMES } from "../states";

export type Rules = {
  states: string[]; income_max_fpl_pct: number | null; gest_min_weeks: number | null; gest_max_weeks: number | null;
  requires_travel: boolean; max_age: number | null; pledge_kind: "fixed" | "percent"; pledge_value: number;
  pledge_cap: number | null; state_basis: "residence" | "care" | "either"; support_type: "procedure" | "practical";
  rate_per_mile_cents: number | null; rate_per_night: number | null; rate_per_meal_day: number | null;
  rate_per_childcare_day: number | null; no_insurance_only: boolean; extra_questions: string[];
  income_waiver_categories: string[]; waiver_pledge_percent: number | null; waiver_pledge_cap: number | null;
  exclude_medicaid_covered: boolean;
};
export type RulesView = {
  rules: Rules; version: number; verified_by: string; last_verified_at: string; days_since_confirmed: number | null;
  confirm_every_days: number; needs_confirm: boolean; pending_ai_review: boolean;
  history: { version: number; status: string; verified_by: string; last_verified_at: string; source_url: string | null }[];
  // clinic-owned funds only
  fund_id?: number; fund_name?: string; monthly_limit?: number | null; used_this_month?: number;
};

// 2025 federal poverty guidelines (48 states + DC), same as the matching engine.
const fpl = (n: number) => 15650 + 5500 * (Math.max(1, n) - 1);
const CODES = Object.keys(STATE_NAMES).sort();

const LABELS: Record<keyof Rules, string> = {
  states: "States served", income_max_fpl_pct: "Income limit", gest_min_weeks: "Weeks: from",
  gest_max_weeks: "Weeks: up to", requires_travel: "Must travel", max_age: "Age limit",
  pledge_kind: "Pledge type", pledge_value: "Pledge amount", pledge_cap: "Pledge cap",
  state_basis: "Eligibility based on", support_type: "Type of help", rate_per_mile_cents: "Per mile",
  rate_per_night: "Per night", rate_per_meal_day: "Meals per day", rate_per_childcare_day: "Childcare per day",
  no_insurance_only: "Only patients without insurance coverage", extra_questions: "Extra questions",
  income_waiver_categories: "Income limit exceptions", waiver_pledge_percent: "Exception pledge (%)",
  waiver_pledge_cap: "Exception pledge cap", exclude_medicaid_covered: "Not when Medicaid covers abortion",
};

const QUESTION_LABELS: Record<string, string> = {
  age: "Age", travel_miles: "Travel miles", nights_away: "Nights away from home", meal_days: "Days needing meals",
  childcare_days: "Days needing dependent care", medicaid: "Has Medicaid", insurance: "Insurance that covers abortion",
  unhoused: "Currently unhoused", judicial_bypass: "Minor seeking a judicial bypass",
};

function describe(k: keyof Rules, v: unknown, r: Rules): string {
  if (k === "states") return (v as string[]).includes("*") ? "Any state" : (v as string[]).join(", ");
  if (v == null) return k === "pledge_cap" || k.startsWith("rate_") ? "—" : "No limit";
  if (k === "income_max_fpl_pct") return `${v}% of poverty line`;
  if (k === "requires_travel") return v ? "Yes" : "No";
  if (k === "max_age") return `${v} and under`;
  if (k === "pledge_kind") return v === "fixed" ? "Set dollar amount" : "Share of the cost";
  if (k === "pledge_value") return r.pledge_kind === "fixed" ? money(v as number) : `${v}%`;
  if (k === "pledge_cap") return money(v as number);
  if (k === "state_basis") return v === "care" ? "State where care happens" : v === "either" ? "Lives in or gets care in" : "State where patient lives";
  if (k === "support_type") return v === "practical" ? "Travel & practical support" : "Toward the procedure";
  if (k === "rate_per_mile_cents") return `$${((v as number) / 100).toFixed(2)}/mile`;
  if (k === "rate_per_night" || k === "rate_per_meal_day" || k === "rate_per_childcare_day") return money(v as number);
  if (k === "no_insurance_only" || k === "exclude_medicaid_covered") return v ? "Yes" : "No";
  if (k === "income_waiver_categories") return (v as string[]).length ? (v as string[]).map((c) => (c === "unhoused" ? "unhoused" : "judicial bypass")).join(", ") : "None";
  if (k === "waiver_pledge_percent") return `${v}%`;
  if (k === "waiver_pledge_cap") return money(v as number);
  if (k === "extra_questions") return (v as string[]).length ? (v as string[]).map((q) => QUESTION_LABELS[q] ?? q).join(", ") : "None";
  return `${v} weeks`;
}

export function ConfirmBanner({ view, onConfirmed, onEdit, base = "/api/fund/rules", who = "Clinics' patients are" }: {
  view: RulesView; onConfirmed: (v: RulesView) => void; onEdit: () => void; base?: string; who?: string;
}) {
  const [err, setErr] = useState("");
  if (!view.needs_confirm) return null;
  const confirm = () => api<RulesView>(`${base}/confirm`, { method: "POST" }).then(onConfirmed).catch((e) => setErr(errText(e)));
  return (
    <div className="nudge" role="status">
      <div>
        <strong>Are {view.fund_name ? `${view.fund_name}'s` : "your"} eligibility rules still right?</strong>{" "}
        <span className="muted">Last confirmed {view.days_since_confirmed ?? "?"} days ago. {who} matched using these rules.</span>
        {err && <span className="error small"> {err}</span>}
      </div>
      <div className="decide">
        <button className="btn small-btn" onClick={confirm}>Yes, still accurate</button>
        <button className="btn ghost small-btn" onClick={onEdit}>Update them</button>
      </div>
    </div>
  );
}

export default function FundRules({ view, onSaved, base = "/api/fund/rules" }: { view: RulesView; onSaved: (v: RulesView) => void; base?: string }) {
  const [r, setR] = useState<Rules>(view.rules);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setR(view.rules); }, [view.version]);
  const set = (p: Partial<Rules>) => { setR((x) => ({ ...x, ...p })); setOk(""); };
  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  const anyState = r.states.includes("*");

  const changes = useMemo(() => {
    const out: { k: keyof Rules; from: string; to: string }[] = [];
    (Object.keys(LABELS) as (keyof Rules)[]).forEach((k) => {
      if (k === "pledge_cap" && r.pledge_kind === "fixed" && view.rules.pledge_kind === "fixed" && r.support_type === "procedure" && view.rules.support_type === "procedure") return;
      if (k.startsWith("rate_") && r.support_type === "procedure" && view.rules.support_type === "procedure") return;
      const sortIf = (v: unknown) => (Array.isArray(v) ? [...v].sort() : v);
      const a = sortIf(view.rules[k]);
      const b = k === "pledge_cap" && r.pledge_kind === "fixed" && r.support_type === "procedure" ? null : sortIf(r[k]);
      if (JSON.stringify(a) !== JSON.stringify(b)) out.push({ k, from: describe(k, a, view.rules), to: describe(k, b, r) });
    });
    return out;
  }, [r, view]);

  const toggleState = (code: string) =>
    set({ states: r.states.includes(code) ? r.states.filter((s) => s !== code) : [...r.states.filter((s) => s !== "*"), code] });

  const save = async () => {
    setBusy(true); setErr(""); setOk("");
    try {
      const v = await api<RulesView>(base, { method: "PUT", body: r });
      onSaved(v);
      setOk(`Saved. Version ${v.version} is live now. New screenings use it right away.`);
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };

  return (
    <div className="rules-editor">
      {view.pending_ai_review && (
        <p className="warn">Calma noticed your website changed, and an admin is reviewing the suggested update. If you save your rules here, your version replaces that suggestion.</p>
      )}
      <div className="card">
        <h2>Which state decides eligibility?</h2>
        <div className="decide">
          <label className="check-inline"><input type="radio" name="sb" checked={r.state_basis === "residence"} onChange={() => set({ state_basis: "residence" })} /> Where the patient <strong>lives</strong></label>
          <label className="check-inline"><input type="radio" name="sb" checked={r.state_basis === "care"} onChange={() => set({ state_basis: "care" })} /> Where the abortion <strong>happens</strong> (the clinic's state)</label>
          <label className="check-inline"><input type="radio" name="sb" checked={r.state_basis === "either"} onChange={() => set({ state_basis: "either" })} /> <strong>Either one</strong>: lives there or gets care there</label>
        </div>
        <h2 className="sub">{r.state_basis === "care" ? "Clinics in which states?" : r.state_basis === "either" ? "Which states? (living there or getting care there both count)" : "Patients from which states?"}</h2>
        <label className="check-inline">
          <input type="checkbox" checked={anyState} onChange={(e) => set({ states: e.target.checked ? ["*"] : [] })} /> Any state
        </label>
        {!anyState && (
          <div className="state-grid" role="group" aria-label="States served">
            {CODES.map((c) => (
              <button key={c} type="button" className={`chip ${r.states.includes(c) ? "on" : ""}`} aria-pressed={r.states.includes(c)}
                title={STATE_NAMES[c]} onClick={() => toggleState(c)}>{c}</button>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h2>Income limit</h2>
        <label className="check-inline">
          <input type="checkbox" checked={r.income_max_fpl_pct == null} onChange={(e) => set({ income_max_fpl_pct: e.target.checked ? null : 200 })} /> No income limit
        </label>
        {r.income_max_fpl_pct != null && (
          <div className="inline-field">
            At or below <input className="input amt" type="number" min={1} value={r.income_max_fpl_pct} onChange={(e) => set({ income_max_fpl_pct: num(e.target.value) })} aria-label="Income limit percent" />
            % of the federal poverty level
            <div className="muted small">
              That's about {money(Math.round((fpl(1) * r.income_max_fpl_pct) / 100))}/year for 1 person,{" "}
              {money(Math.round((fpl(3) * r.income_max_fpl_pct) / 100))}/year for a household of 3.
            </div>
          </div>
        )}
      </div>

      <div className="card two-col">
        <div>
          <h2>Weeks of pregnancy you cover</h2>
          <div className="inline-field">
            From <input className="input amt" type="number" min={0} max={42} placeholder="any" value={r.gest_min_weeks ?? ""} onChange={(e) => set({ gest_min_weeks: num(e.target.value) })} aria-label="Minimum weeks" />
            up to <input className="input amt" type="number" min={0} max={42} placeholder="any" value={r.gest_max_weeks ?? ""} onChange={(e) => set({ gest_max_weeks: num(e.target.value) })} aria-label="Maximum weeks" /> weeks
          </div>
          <p className="muted small">Leave blank for no limit.</p>
        </div>
        <div>
          <h2>Other limits</h2>
          <label className="check-inline">
            <input type="checkbox" checked={r.requires_travel} onChange={(e) => set({ requires_travel: e.target.checked })} /> Only patients who must travel for care
          </label>
          <div className="inline-field">
            Age <input className="input amt" type="number" min={10} max={100} placeholder="any" value={r.max_age ?? ""} onChange={(e) => set({ max_age: num(e.target.value) })} aria-label="Age limit" /> and under
          </div>
          <label className="check-inline">
            <input type="checkbox" checked={r.no_insurance_only} onChange={(e) => set({ no_insurance_only: e.target.checked })} /> Only patients whose Medicaid or insurance does <strong>not</strong> cover abortion
          </label>
        </div>
      </div>

      <div className="card">
        <h2>What kind of help do you give?</h2>
        <div className="decide">
          <label className="check-inline"><input type="radio" name="st" checked={r.support_type === "procedure"} onChange={() => set({ support_type: "procedure", pledge_value: Math.max(1, r.pledge_value) })} /> Money toward the <strong>procedure</strong> (paid to the clinic)</label>
          <label className="check-inline"><input type="radio" name="st" checked={r.support_type === "practical"} onChange={() => set({ support_type: "practical", pledge_kind: "fixed" })} /> <strong>Travel & practical support</strong> only (gas, lodging, food, childcare)</label>
        </div>
        {r.support_type === "procedure" ? (
          <>
            <div className="decide">
              <label className="check-inline"><input type="radio" name="pk" checked={r.pledge_kind === "fixed"} onChange={() => set({ pledge_kind: "fixed", pledge_cap: null })} /> A set dollar amount</label>
              <label className="check-inline"><input type="radio" name="pk" checked={r.pledge_kind === "percent"} onChange={() => set({ pledge_kind: "percent", pledge_value: Math.min(r.pledge_value, 100) })} /> A share of the procedure cost</label>
            </div>
            {r.pledge_kind === "fixed" ? (
              <div className="inline-field">$ <input className="input amt" type="number" min={1} value={r.pledge_value} onChange={(e) => set({ pledge_value: Number(e.target.value) })} aria-label="Pledge dollars" /></div>
            ) : (
              <div className="inline-field">
                <input className="input amt" type="number" min={1} max={100} value={r.pledge_value} onChange={(e) => set({ pledge_value: Number(e.target.value) })} aria-label="Pledge percent" />% of the cost, up to $
                <input className="input amt" type="number" min={1} placeholder="no cap" value={r.pledge_cap ?? ""} onChange={(e) => set({ pledge_cap: num(e.target.value) })} aria-label="Pledge cap" />
              </div>
            )}
          </>
        ) : (
          <>
            <p className="muted small">Calma adds up what the patient tells us about their trip. Leave a rate blank if you don't cover it. Patients are only asked the questions your rates need.</p>
            <div className="rate-grid">
              <label>Per mile (round trip) $<input className="input amt" type="number" min={0} step={0.01} placeholder="—" value={r.rate_per_mile_cents == null ? "" : r.rate_per_mile_cents / 100} onChange={(e) => set({ rate_per_mile_cents: e.target.value === "" ? null : Math.round(Number(e.target.value) * 100) })} aria-label="Rate per mile" /></label>
              <label>Lodging per night $<input className="input amt" type="number" min={0} placeholder="—" value={r.rate_per_night ?? ""} onChange={(e) => set({ rate_per_night: num(e.target.value) })} aria-label="Rate per night" /></label>
              <label>Meals per day $<input className="input amt" type="number" min={0} placeholder="—" value={r.rate_per_meal_day ?? ""} onChange={(e) => set({ rate_per_meal_day: num(e.target.value) })} aria-label="Rate per meal day" /></label>
              <label>Dependent care per day $<input className="input amt" type="number" min={0} placeholder="—" value={r.rate_per_childcare_day ?? ""} onChange={(e) => set({ rate_per_childcare_day: num(e.target.value) })} aria-label="Rate per childcare day" /></label>
              <label>Flat amount (e.g. gas card) $<input className="input amt" type="number" min={0} value={r.pledge_value} onChange={(e) => set({ pledge_value: Number(e.target.value) })} aria-label="Flat amount" /></label>
              <label>Most you give per patient $<input className="input amt" type="number" min={1} placeholder="no cap" value={r.pledge_cap ?? ""} onChange={(e) => set({ pledge_cap: num(e.target.value) })} aria-label="Practical cap" /></label>
            </div>
          </>
        )}
        <p className="muted small">This is the amount Calma suggests. You still approve every pledge yourself and can change the amount each time.</p>
      </div>

      {r.support_type === "procedure" && (
        <div className="card">
          <h2>Exceptions</h2>
          <p className="muted small">Patients in these groups skip your income limit. Calma asks them the matching question automatically.</p>
          <div className="decide">
            {[["unhoused", "Currently unhoused"], ["judicial_bypass", "Minors seeking a judicial bypass"]].map(([id, label]) => (
              <label key={id} className="check-inline">
                <input type="checkbox" checked={r.income_waiver_categories.includes(id)}
                  onChange={(e) => set({ income_waiver_categories: e.target.checked ? [...r.income_waiver_categories, id] : r.income_waiver_categories.filter((x) => x !== id) })} /> {label}
              </label>
            ))}
          </div>
          {r.income_waiver_categories.length > 0 && (
            <div className="inline-field">
              For them, pledge <input className="input amt" type="number" min={1} max={100} placeholder="usual" value={r.waiver_pledge_percent ?? ""}
                onChange={(e) => set({ waiver_pledge_percent: num(e.target.value) })} aria-label="Exception pledge percent" />% of the cost, up to $
              <input className="input amt" type="number" min={1} placeholder="no cap" value={r.waiver_pledge_cap ?? ""}
                onChange={(e) => set({ waiver_pledge_cap: num(e.target.value) })} aria-label="Exception pledge cap" />
              <span className="muted small">Leave the percent blank to use your usual pledge.</span>
            </div>
          )}
          <label className="check-inline" style={{ marginTop: 10 }}>
            <input type="checkbox" checked={r.exclude_medicaid_covered} onChange={(e) => set({ exclude_medicaid_covered: e.target.checked })} />
            No pledge if the patient has Medicaid in a state where Medicaid covers abortion (Medicaid should pay)
          </label>
          {r.exclude_medicaid_covered && <MedicaidStates />}
        </div>
      )}

      <div className="card">
        <h2>Extra questions to ask patients</h2>
        <p className="muted small">Turn these on to see the answers on each patient's card, even if your rules don't use them. Patients can skip any of them. Questions your rules need are asked automatically.</p>
        <div className="q-grid">
          {Object.entries(QUESTION_LABELS).map(([q, label]) => (
            <label key={q} className="check-inline">
              <input type="checkbox" checked={r.extra_questions.includes(q)}
                onChange={(e) => set({ extra_questions: e.target.checked ? [...r.extra_questions, q] : r.extra_questions.filter((x) => x !== q) })} /> {label}
            </label>
          ))}
        </div>
      </div>

      <div className={`card save-card ${changes.length ? "sticky" : ""}`}>
        {changes.length === 0 ? (
          <p className="muted">No changes yet. Edit anything above to update your rules.</p>
        ) : (
          <>
            <h2>You're changing</h2>
            <ul className="change-list">
              {changes.map((c) => <li key={c.k}><strong>{LABELS[c.k]}:</strong> <span className="muted">{c.from}</span> → <span className="accent">{c.to}</span></li>)}
            </ul>
          </>
        )}
        <div className="decide">
          <button className="btn" disabled={busy || changes.length === 0 || (!anyState && r.states.length === 0)} onClick={save}>
            {busy ? "Saving…" : "Save and make live"}
          </button>
          {changes.length > 0 && <button className="btn ghost" onClick={() => setR(view.rules)}>Undo changes</button>}
        </div>
        {!anyState && r.states.length === 0 && <p className="error small">Pick at least one state, or "Any state".</p>}
        {err && <p className="error small" role="alert">{err}</p>}
        {ok && <p className="ok small" role="status">{ok}</p>}
      </div>

      <div className="card">
        <h2>Version history</h2>
        <table className="grid compact small">
          <thead><tr><th>Version</th><th>Status</th><th>Set or confirmed by</th><th>When (UTC)</th><th>Source</th></tr></thead>
          <tbody>
            {view.history.map((h) => (
              <tr key={h.version}>
                <td>v{h.version}</td><td>{h.status === "approved" ? "Live" : "Replaced"}</td><td>{h.verified_by}</td>
                <td className="mono">{h.last_verified_at?.replace("T", " ").slice(0, 16)}</td>
                <td className="muted">{h.source_url ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MedicaidStates() {
  const [d, setD] = useState<{ states: string[]; with_medical_necessity: string[]; as_of: string; source: string } | null>(null);
  useEffect(() => { api<typeof d>("/api/medicaid-coverage").then(setD).catch(() => {}); }, []);
  if (!d) return null;
  return (
    <p className="muted small">
      States whose Medicaid covers abortion ({d.states.length}): {d.states.join(", ")}.
      {" "}{d.with_medical_necessity.length} of them require a medical-necessity designation.
      {" "}Source: <a href={d.source} target="_blank" rel="noreferrer">Guttmacher Institute</a>, as of {d.as_of}.
    </p>
  );
}
