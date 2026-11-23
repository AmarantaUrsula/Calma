import { useEffect, useState } from "react";
import { api, errText, money } from "../api";
import { StaffShell } from "./Staff";

type FundRow = {
  id: number; name: string; kind: string; monthly_limit: number | null; description: string; version: number | null;
  reference_only: boolean;
  states: string[]; income_max_fpl_pct: number | null; gest_min_weeks: number | null; gest_max_weeks: number | null;
  requires_travel: number; max_age: number | null; pledge_kind: string; pledge_value: number; pledge_cap: number | null;
  last_verified_at: string; verified_by: string; state_basis: string; support_type: string; no_insurance_only: boolean;
};
type AuditRow = { id: number; at: string; actor: string; action: string; case_id: number | null; detail: string | null };
type Rules = {
  states: string[]; income_max_fpl_pct: number | null; gest_min_weeks: number | null; gest_max_weeks: number | null;
  requires_travel: boolean; max_age: number | null; pledge_kind: "fixed" | "percent"; pledge_value: number;
  pledge_cap: number | null; state_basis: "residence" | "care"; support_type: "procedure" | "practical";
  no_insurance_only: boolean;
};
type Evidence = { status: "changed" | "same" | "not_stated" | "needs_manual"; quote: string | null; quote_verified: boolean };
type Proposal = {
  id: number; fund_id: number; fund_name: string; version: number; source_url: string | null; proposed_by: string;
  current: Rules; proposed: Rules;
  evidence: Record<string, Evidence> & { _summary?: { text: string }; _other?: { items: string[] } };
};

const FIELDS: { key: keyof Rules; label: string; kind: "states" | "int" | "bool" | "pledgeKind" | "basis" | "stype" }[] = [
  { key: "state_basis", label: "Eligibility based on", kind: "basis" },
  { key: "states", label: "States", kind: "states" },
  { key: "income_max_fpl_pct", label: "Income limit (% of poverty line)", kind: "int" },
  { key: "gest_min_weeks", label: "Weeks pregnant: minimum", kind: "int" },
  { key: "gest_max_weeks", label: "Weeks pregnant: maximum", kind: "int" },
  { key: "requires_travel", label: "Only patients who must travel", kind: "bool" },
  { key: "max_age", label: "Age limit (and under)", kind: "int" },
  { key: "pledge_kind", label: "Pledge type", kind: "pledgeKind" },
  { key: "pledge_value", label: "Pledge ($ or %)", kind: "int" },
  { key: "pledge_cap", label: "Pledge cap ($)", kind: "int" },
  { key: "support_type", label: "Type of help", kind: "stype" },
  { key: "no_insurance_only", label: "Only patients without insurance coverage", kind: "bool" },
];

const STATUS_LABEL: Record<string, string> = {
  changed: "Changed", same: "Same as now", not_stated: "Not on page — kept current", needs_manual: "Stated, but you need to fill this in",
};

function show(v: unknown): string {
  if (v == null || v === "") return "—";
  if (Array.isArray(v)) return v.includes("*") ? "Any state" : v.join(", ");
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (v === "residence") return "Where patient lives";
  if (v === "care") return "Where care happens";
  if (v === "procedure") return "Toward procedure";
  if (v === "practical") return "Travel/practical";
  return String(v);
}

export default function Admin() {
  const [funds, setFunds] = useState<FundRow[]>([]);
  const [log, setLog] = useState<AuditRow[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [updating, setUpdating] = useState<FundRow | null>(null);
  const [err, setErr] = useState("");
  const load = () =>
    Promise.all([api<FundRow[]>("/api/admin/funds"), api<AuditRow[]>("/api/admin/audit"), api<Proposal[]>("/api/admin/proposals")])
      .then(([f, a, p]) => { setFunds(f); setLog(a); setProposals(p); })
      .catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);

  return (
    <StaffShell title="Admin" subtitle="Fund rules and audit log">
      {err && <p className="error">{err}</p>}

      <Accounts />

      {proposals.map((p) => <Review key={p.id} p={p} onDone={() => { setUpdating(null); load(); }} />)}

      {updating && !proposals.some((p) => p.fund_id === updating.id) && (
        <ExtractForm fund={updating} onCancel={() => setUpdating(null)} onProposed={load} />
      )}

      <WebsiteChecks onChange={load} />

      <div className="card">
        <h2>Fund eligibility rules (live version)</h2>
        <p className="muted small">To update a fund, paste its policy text. The AI suggests new rules and quotes where each one came from. Nothing changes until you approve.</p>
        <table className="grid">
          <thead><tr><th>Fund</th><th>Type</th><th>States</th><th>Income limit</th><th>Weeks</th><th>Other</th><th>Pledge</th><th className="num">Monthly limit</th><th>Version</th><th /></tr></thead>
          <tbody>
            {funds.map((f) => f.version == null ? (
              <tr key={f.id}>
                <td>{f.name}{f.reference_only && <div><span className="badge real">Real fund · reference only</span></div>}</td>
                <td colSpan={8} className="muted small">No reviewed rules yet. Run a website check below; the AI's suggestion will appear at the top of this page for you to review.</td>
                <td>{proposals.some((p) => p.fund_id === f.id) ? <span className="badge pending">Review above</span> : <button className="btn ghost small-btn" onClick={() => setUpdating(f)}>Update rules</button>}</td>
              </tr>
            ) : (
              <tr key={f.id}>
                <td>{f.name}{f.reference_only && <div><span className="badge real">Real fund · reference only</span></div>}</td>
                <td>{f.kind === "clinic" ? "Clinic fund" : "Independent"}</td>
                <td>{f.states.includes("*") ? "Any" : [...f.states].sort().join(", ")}{f.state_basis === "care" && <div className="muted small">state of care</div>}</td>
                <td>{f.income_max_fpl_pct != null ? `≤ ${f.income_max_fpl_pct}% FPL` : "—"}</td>
                <td>{f.gest_min_weeks != null || f.gest_max_weeks != null ? `${f.gest_min_weeks ?? 0}–${f.gest_max_weeks ?? "any"}` : "—"}</td>
                <td>{[f.requires_travel ? "must travel" : "", f.max_age != null ? `age ≤ ${f.max_age}` : "", f.no_insurance_only ? "no insurance coverage" : ""].filter(Boolean).join(", ") || "—"}</td>
                <td>{f.support_type === "practical" ? `Travel/practical ≤ ${money(f.pledge_cap)}` : f.pledge_kind === "fixed" ? money(f.pledge_value) : `${f.pledge_value}% ≤ ${money(f.pledge_cap)}`}</td>
                <td className="num">{money(f.monthly_limit)}</td>
                <td className="small muted">v{f.version} · {f.verified_by}</td>
                <td>
                  {proposals.some((p) => p.fund_id === f.id)
                    ? <span className="badge pending">Review above</span>
                    : <button className="btn ghost small-btn" onClick={() => setUpdating(f)}>Update rules</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Audit log (latest 200)</h2>
        <table className="grid compact small">
          <thead><tr><th>When (UTC)</th><th>Who</th><th>Action</th><th>Case</th><th>Detail</th></tr></thead>
          <tbody>
            {log.map((r) => (
              <tr key={r.id}>
                <td className="mono">{r.at.replace("T", " ").slice(0, 19)}</td><td>{r.actor}</td><td>{r.action}</td>
                <td className="mono">{r.case_id ? `C-${1000 + r.case_id}` : ""}</td><td className="mono muted">{r.detail ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </StaffShell>
  );
}

function ExtractForm({ fund, onCancel, onProposed }: { fund: FundRow; onCancel: () => void; onProposed: () => void }) {
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      await api(`/api/admin/funds/${fund.id}/extract`, { body: { text, source_url: url || null } });
      onProposed();
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  return (
    <form className="card extract" onSubmit={submit}>
      <h2>Update rules · {fund.name}</h2>
      <label className="field">
        <span className="small muted">Paste the fund's eligibility text (from its website, email or flyer)</span>
        <textarea className="input" rows={8} value={text} onChange={(e) => setText(e.target.value)} minLength={40} required
          placeholder="e.g. We help people who live in Kansas or Missouri with household income under 250% of the federal poverty level. We pledge up to $200…" />
      </label>
      <label className="field">
        <span className="small muted">Where it came from (optional link)</span>
        <input className="input" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
      </label>
      <p className="muted small">Only this text is sent to the AI. No patient information.</p>
      <div className="decide">
        <button className="btn" disabled={busy || text.trim().length < 40}>{busy ? "Reading the policy…" : "Suggest rules with AI"}</button>
        <button type="button" className="btn ghost" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
      {err && <p className="error small" role="alert">{err}</p>}
    </form>
  );
}

function Review({ p, onDone }: { p: Proposal; onDone: () => void }) {
  const [vals, setVals] = useState<Rules>(p.proposed);
  const [statesText, setStatesText] = useState(p.proposed.states.join(", "));
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof Rules, v: unknown) => setVals((x) => ({ ...x, [k]: v }));
  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  const unverified = FIELDS.some((f) => p.evidence[f.key]?.quote && !p.evidence[f.key]?.quote_verified);

  const approve = async () => {
    setBusy(true); setErr("");
    const states = statesText.split(/[,\s]+/).map((s) => s.trim().toUpperCase()).filter(Boolean);
    try {
      await api(`/api/admin/proposals/${p.id}/approve`, { body: { ...vals, states } });
      onDone();
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  const reject = async () => {
    setBusy(true);
    try { await api(`/api/admin/proposals/${p.id}/reject`, { method: "POST" }); onDone(); }
    catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };

  return (
    <div className="card review-card">
      <h2>Review suggested rules · {p.fund_name} (would become v{p.version})</h2>
      {p.evidence._summary && <p className="lead-sm">{p.evidence._summary.text}</p>}
      <p className="muted small">
        Suggested by {p.proposed_by}{p.source_url && <> from <a href={p.source_url} target="_blank" rel="noreferrer">{p.source_url}</a></>}.
        Check each line against the quote, fix anything wrong, then approve.
      </p>
      {unverified && <p className="warn">⚠ Some quotes were not found word-for-word in the text you pasted. Check those lines carefully.</p>}
      <table className="grid review-table">
        <thead><tr><th>Rule</th><th>Now</th><th>Suggested (you can edit)</th><th>Where it came from</th></tr></thead>
        <tbody>
          {FIELDS.map((f) => {
            const ev = p.evidence[f.key];
            const changed = JSON.stringify(vals[f.key]) !== JSON.stringify(p.current[f.key]);
            return (
              <tr key={f.key} className={changed ? "changed" : ""}>
                <td>{f.label}</td>
                <td className="muted">{show(p.current[f.key])}</td>
                <td>
                  {f.kind === "states" && <input className="input" value={statesText} onChange={(e) => setStatesText(e.target.value)} aria-label={f.label} />}
                  {f.kind === "int" && <input className="input amt" type="number" value={(vals[f.key] as number | null) ?? ""} onChange={(e) => set(f.key, num(e.target.value))} aria-label={f.label} />}
                  {f.kind === "bool" && <input type="checkbox" checked={!!vals[f.key]} onChange={(e) => set(f.key, e.target.checked)} aria-label={f.label} />}
                  {f.kind === "basis" && (
                    <select className="input" value={vals.state_basis} onChange={(e) => set("state_basis", e.target.value)} aria-label={f.label}>
                      <option value="residence">Where patient lives</option><option value="care">Where care happens</option>
                    </select>
                  )}
                  {f.kind === "stype" && (
                    <select className="input" value={vals.support_type} onChange={(e) => set("support_type", e.target.value)} aria-label={f.label}>
                      <option value="procedure">Toward procedure</option><option value="practical">Travel/practical</option>
                    </select>
                  )}
                  {f.kind === "pledgeKind" && (
                    <select className="input" value={vals.pledge_kind} onChange={(e) => set("pledge_kind", e.target.value)} aria-label={f.label}>
                      <option value="fixed">Fixed $</option><option value="percent">% of cost</option>
                    </select>
                  )}
                </td>
                <td className="small">
                  {ev && <span className={`ev ev-${ev.status}`}>{STATUS_LABEL[ev.status]}</span>}
                  {ev?.quote && (
                    <blockquote className={ev.quote_verified ? "" : "unverified"}>
                      “{ev.quote}”{!ev.quote_verified && <span className="error"> — not found in text</span>}
                    </blockquote>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {p.evidence._other && p.evidence._other.items.length > 0 && (
        <div className="other-notes">
          <strong className="small">Other rules on the page (not used in matching yet):</strong>
          <ul className="reasons">{p.evidence._other.items.map((i) => <li key={i}>{i}</li>)}</ul>
        </div>
      )}
      <div className="decide">
        <button className="btn" onClick={approve} disabled={busy}>Approve and make live</button>
        <button className="btn ghost" onClick={reject} disabled={busy}>Reject</button>
      </div>
      {err && <p className="error small" role="alert">{err}</p>}
    </div>
  );
}

type CheckFund = { id: number; name: string; kind: string; policy_url: string | null; reference_only: number | boolean; last_checked_at: string | null; last_status: string | null; next_check_at: string | null };
type CheckRow = { id: number; fund_id: number; fund_name: string; url: string; checked_at: string; trigger: string; status: string; note: string; criteria_id: number | null };

const CHECK_LABEL: Record<string, string> = {
  unchanged: "No change", rules_same: "Rules match", proposal_created: "Rules may have changed",
  skipped_pending_review: "Waiting on review", error: "Problem",
};
const CHECK_BADGE: Record<string, string> = {
  unchanged: "approved", rules_same: "approved", proposal_created: "pending", skipped_pending_review: "pending", error: "declined",
};
const when = (iso: string | null) => (!iso ? "—" : iso === "soon" ? "Next run" : iso.replace("T", " ").slice(0, 16));

function WebsiteChecks({ onChange }: { onChange: () => void }) {
  const [data, setData] = useState<{ interval_days: number; funds: CheckFund[]; checks: CheckRow[] } | null>(null);
  const [busy, setBusy] = useState<string>("");
  const [editing, setEditing] = useState<number | null>(null);
  const [url, setUrl] = useState("");
  const [err, setErr] = useState("");
  const load = () => api<typeof data>("/api/admin/website-checks").then(setData).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  const act = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key); setErr("");
    try { await fn(); await load(); onChange(); } catch (e) { setErr(errText(e)); } finally { setBusy(""); }
  };
  if (!data) return null;
  const withLinks = data.funds.filter((f) => f.kind === "independent" || f.policy_url);
  return (
    <div className="card">
      <div className="pledge-head">
        <h2>Fund website checks</h2>
        <span className="muted small">Every {data.interval_days} days, Calma re-reads each fund's eligibility page. If the page changed, the AI suggests updates for you to review. Nothing changes without you. Real funds are tracked for their public rules only: they're never matched with the made-up demo patients.</span>
        <button className="btn small-btn right" disabled={!!busy} onClick={() => act("due", () => api("/api/admin/website-checks/run-due", { method: "POST" }))}>
          {busy === "due" ? "Checking…" : "Run due checks now"}
        </button>
      </div>
      {err && <p className="error small" role="alert">{err}</p>}
      <table className="grid">
        <thead><tr><th>Fund</th><th>Eligibility page</th><th>Last check</th><th>Result</th><th>Next check</th><th /></tr></thead>
        <tbody>
          {withLinks.map((f) => (
            <tr key={f.id}>
              <td>{f.name}{!!f.reference_only && <div><span className="badge real">Real fund · reference only</span></div>}</td>
              <td className="small">
                {editing === f.id ? (
                  <span className="decide">
                    <input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" aria-label={`Eligibility page for ${f.name}`} />
                    <button className="btn small-btn" onClick={() => act(`url${f.id}`, () => api(`/api/admin/funds/${f.id}/policy-url`, { method: "PUT", body: { policy_url: url } })).then(() => setEditing(null))}>Save</button>
                    <button className="btn ghost small-btn" onClick={() => setEditing(null)}>Cancel</button>
                  </span>
                ) : (
                  <>
                    <span className="mono">{f.policy_url ?? <span className="muted">No link</span>}</span>{" "}
                    <button className="link small" onClick={() => { setEditing(f.id); setUrl(f.policy_url ?? ""); }}>edit</button>
                  </>
                )}
              </td>
              <td className="small">{when(f.last_checked_at)}</td>
              <td>{f.last_status ? <span className={`badge ${CHECK_BADGE[f.last_status]}`}>{CHECK_LABEL[f.last_status]}</span> : <span className="muted small">Never checked</span>}</td>
              <td className="small muted">{when(f.next_check_at)}</td>
              <td>{f.policy_url && <button className="btn ghost small-btn" disabled={!!busy} onClick={() => act(`f${f.id}`, () => api(`/api/admin/funds/${f.id}/check-now`, { method: "POST" }))}>{busy === `f${f.id}` ? "Checking…" : "Check now"}</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.checks.length > 0 && (
        <details>
          <summary className="small">Check history ({data.checks.length})</summary>
          <table className="grid compact small">
            <thead><tr><th>When (UTC)</th><th>Fund</th><th>By</th><th>Result</th><th>Note</th></tr></thead>
            <tbody>
              {data.checks.map((c) => (
                <tr key={c.id}>
                  <td className="mono">{when(c.checked_at)}</td><td>{c.fund_name}</td>
                  <td>{c.trigger === "schedule" ? "Schedule" : "Admin"}</td>
                  <td><span className={`badge ${CHECK_BADGE[c.status]}`}>{CHECK_LABEL[c.status]}</span></td>
                  <td className="muted">{c.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}

type Account = {
  id: number; name: string; email: string | null; role: string; status: string; created_at: string | null;
  approved_at: string | null; last_login_at: string | null; clinic_name: string | null; fund_name: string | null;
};
const ROLE: Record<string, string> = { clinic: "Clinic staff", fund: "Fund staff", admin: "Calma admin" };
const ACCT_BADGE: Record<string, [string, string]> = {
  pending: ["Waiting for approval", "pending"], active: ["Active", "approved"], rejected: ["Rejected", "declined"], disabled: ["Disabled", "declined"],
};
const shortDate = (iso: string | null) => (iso ? iso.replace("T", " ").slice(0, 16) : "—");

function Accounts() {
  const [rows, setRows] = useState<Account[]>([]);
  const [err, setErr] = useState("");
  const [showAll, setShowAll] = useState(false);
  useEffect(() => { api<Account[]>("/api/admin/users").then(setRows).catch((e) => setErr(errText(e))); }, []);
  const act = async (id: number, action: string) => {
    setErr("");
    try { setRows(await api<Account[]>(`/api/admin/users/${id}/${action}`, { method: "POST" })); } catch (e) { setErr(errText(e)); }
  };
  const pending = rows.filter((r) => r.status === "pending");
  const shown = showAll ? rows : pending;
  return (
    <div className={`card ${pending.length ? "review-card" : ""}`}>
      <div className="pledge-head">
        <h2>Staff accounts</h2>
        <span className="muted small">
          {pending.length ? `${pending.length} waiting for approval. Check that each person really works where they say before approving.` : "No accounts waiting for approval."}
        </span>
        <button className="btn ghost small-btn right" onClick={() => setShowAll((x) => !x)}>{showAll ? "Show waiting only" : `Show all (${rows.length})`}</button>
      </div>
      {err && <p className="error small" role="alert">{err}</p>}
      {shown.length > 0 && (
        <table className="grid">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Organization</th><th>Status</th><th>Created</th><th>Last log in</th><th /></tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td><td className="small">{r.email}</td><td>{ROLE[r.role]}</td>
                <td>{r.clinic_name ?? r.fund_name ?? "Calma"}</td>
                <td><span className={`badge ${ACCT_BADGE[r.status][1]}`}>{ACCT_BADGE[r.status][0]}</span></td>
                <td className="small mono">{shortDate(r.created_at)}</td><td className="small mono">{shortDate(r.last_login_at)}</td>
                <td className="num">
                  {r.status === "pending" && <span className="decide"><button className="btn small-btn" onClick={() => act(r.id, "approve")}>Approve</button><button className="btn ghost small-btn" onClick={() => act(r.id, "reject")}>Reject</button></span>}
                  {r.status === "active" && <button className="btn ghost small-btn" onClick={() => act(r.id, "disable")}>Disable</button>}
                  {r.status === "disabled" && <button className="btn ghost small-btn" onClick={() => act(r.id, "enable")}>Enable</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
