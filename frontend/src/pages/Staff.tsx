import { useEffect, useState } from "react";
import { api, errText, getUser, money, navigate, setSession } from "../api";

export type StaffUser = { id: number; name: string; role: "clinic" | "fund" | "admin"; email?: string | null };

export function StaffShell({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  const user = getUser<StaffUser>();
  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    setSession(null);
    navigate("/login");
  };
  return (
    <div className="staff">
      <header className="staff-top">
        <span className="brand">Calma</span>
        <div>
          <div className="staff-title">{title}</div>
          {subtitle && <div className="muted small">{subtitle}</div>}
        </div>
        <div className="right small">
          <span className="muted">{user?.name}</span>
          <button className="btn ghost small-btn" onClick={logout}>Log out</button>
        </div>
      </header>
      <main className="staff-main">{children}</main>
      <footer className="demo-note">Demo data only — all clinics, funds and people are made up.</footer>
    </div>
  );
}

export function Badge({ status }: { status: string }) {
  const label: Record<string, string> = {
    pending: "Needs decision", approved: "Approved", declined: "Declined", paid: "Completed",
    link_sent: "Link sent", screened: "Screened", appointment_done: "Visit done", closed: "Closed",
  };
  return <span className={`badge ${status}`}>{label[status] ?? status}</span>;
}

type Pledge = {
  id: number; case_ref: string; fund_name: string; fund_kind: string; suggested_amount: number;
  approved_amount: number | null; status: string; reasons: string[];
};

export function DecisionControls({ p, path, onDone }: { p: Pledge; path: string; onDone: () => void }) {
  const [amount, setAmount] = useState(p.suggested_amount);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const decide = async (decision: "approve" | "decline") => {
    setBusy(true); setErr("");
    try {
      await api(path, { body: { decision, amount: decision === "approve" ? amount : undefined } });
      onDone();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="decide">
      <label className="small">
        Amount $
        <input className="input amt" type="number" min={1} value={amount} onChange={(e) => setAmount(Number(e.target.value))} aria-label={`Amount for ${p.fund_name}`} />
      </label>
      <button className="btn" disabled={busy || amount < 1} onClick={() => decide("approve")}>Approve</button>
      <button className="btn ghost" disabled={busy} onClick={() => decide("decline")}>Decline</button>
      {err && <p className="error small" role="alert">{err}</p>}
    </div>
  );
}

export { money };

// Plain-English rows for a patient's answers (staff views). Only keys present are shown.
export function answerRows(a: Record<string, unknown>): [string, string][] {
  const yn = (v: unknown) => (v == null ? "—" : v ? "Yes" : "No");
  const n = (v: unknown, unit: string) =>
    v == null ? "—" : `${v}${Number(v) >= 3 ? "+" : ""} ${Number(v) === 1 ? unit.replace(/s$/, "") : unit}`;
  const rows: [string, string, unknown][] = [
    ["Lives in", String(a.state ?? "—"), a.state],
    ["Getting care in", String(a.care_state ?? "—"), a.care_state],
    ["Household", String(a.household_size ?? "—"), a.household_size],
    ["Weeks pregnant at visit", a.gestational_weeks == null ? "Not sure" : String(a.gestational_weeks), "gestational_weeks" in a ? 1 : undefined],
    ["Needs to travel", yn(a.needs_travel), "needs_travel" in a ? 1 : undefined],
    ["Age", a.age == null ? "Not given" : String(a.age), "age" in a ? 1 : undefined],
    ["Miles to clinic (one way)", a.travel_miles == null ? "—" : `${a.travel_miles} mi`, a.travel_miles],
    ["Nights away", n(a.nights_away, "nights"), a.nights_away],
    ["Days of meals", n(a.meal_days, "days"), a.meal_days],
    ["Days of dependent care", n(a.childcare_days, "days"), a.childcare_days],
    ["Insurance covers abortion", a.insurance_coverage === "unsure" ? "Not sure" : a.insurance_coverage === "yes" ? "Yes" : a.insurance_coverage === "no" ? "No" : "—", a.insurance_coverage],
    ["Unhoused", yn(a.unhoused), a.unhoused],
    ["Minor seeking judicial bypass", yn(a.judicial_bypass), a.judicial_bypass],
  ];
  return rows.filter(([, , present]) => present !== undefined && present !== null).map(([k, v]) => [k, v]);
}

/** "Decide by Tue 3:15 PM" for a pending pledge, or a red "Overdue" flag past the 24-hour policy. */
export function DueBadge({ decideBy, overdue }: { decideBy: string | null; overdue: boolean }) {
  if (!decideBy) return null;
  const when = new Date(decideBy).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  return overdue
    ? <span className="badge overdue" title="Past the 24-hour decision policy">Overdue · was due {when}</span>
    : <span className="badge due">Decide by {when}</span>;
}
