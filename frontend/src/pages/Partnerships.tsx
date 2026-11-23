import { useEffect, useState } from "react";
import { api, errText } from "../api";

export type Partnership = {
  clinic_id: number; fund_id: number; status: "pending" | "accepted" | "declined"; requested_by: string;
  created_at: string | null; accepted_at: string | null; clinic_name: string; city: string; state: string;
  fund_name: string; fund_description: string;
};

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("en-US") : "—");
const STATUS: Record<string, [string, string]> = {
  accepted: ["Accepted", "approved"], pending: ["Waiting for clinic", "pending"], declined: ["Declined by clinic", "declined"],
};

/** Fund portal: choose which clinics can send you eligible patients. */
export function FundPartnerships({ onChange }: { onChange: () => void }) {
  const [d, setD] = useState<{ partnerships: Partnership[]; available_clinics: { id: number; name: string; city: string; state: string }[] } | null>(null);
  const [adding, setAdding] = useState(false);
  const [confirm, setConfirm] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const load = () => api<typeof d>("/api/fund/partnerships").then(setD).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  const act = async (fn: () => Promise<typeof d>) => {
    setErr("");
    try { setD(await fn()); setConfirm(null); onChange(); } catch (e) { setErr(errText(e)); }
  };
  if (!d) return <p className="muted">{err || "Loading…"}</p>;
  const canAdd = d.available_clinics.length > 0 || d.partnerships.some((p) => p.status === "declined");
  return (
    <div className="card">
      <div className="pledge-head">
        <h2>My partner clinics</h2>
        <span className="muted small">Only clinics you partner with can send you eligible patients. A clinic must accept your request first.</span>
        <button className="btn small-btn right" disabled={!canAdd} onClick={() => setAdding((x) => !x)}>{adding ? "Done" : "Add partner clinic"}</button>
      </div>
      {err && <p className="error small" role="alert">{err}</p>}

      {adding && (
        <div className="add-panel">
          {d.available_clinics.length === 0 && !d.partnerships.some((p) => p.status === "declined") && <p className="muted small">No more clinics to add. You've connected with, or sent a request to, every clinic on Calma.</p>}
          {d.available_clinics.map((c) => (
            <div key={c.id} className="add-row">
              <span><strong>{c.name}</strong> <span className="muted small">{c.city}, {c.state}</span></span>
              <button className="btn small-btn" onClick={() => act(() => api(`/api/fund/partnerships/${c.id}`, { method: "POST" })).then(() => setAdding(false))}>Send request</button>
            </div>
          ))}
        </div>
      )}

      <table className="grid">
        <thead><tr><th>Clinic</th><th>Location</th><th>Status</th><th>Accepted</th><th>Requested</th><th /></tr></thead>
        <tbody>
          {d.partnerships.map((p) => (
            <tr key={p.clinic_id}>
              <td>{p.clinic_name}</td>
              <td className="muted">{p.city}, {p.state}</td>
              <td><span className={`badge ${STATUS[p.status][1]}`}>{STATUS[p.status][0]}</span></td>
              <td>{day(p.accepted_at)}</td>
              <td>{day(p.created_at)}</td>
              <td className="num">
                {p.status === "declined" ? (
                  <button className="btn ghost small-btn" onClick={() => act(() => api(`/api/fund/partnerships/${p.clinic_id}`, { method: "POST" }))}>Ask again</button>
                ) : confirm === p.clinic_id ? (
                  <span className="decide confirm-inline">
                    <span className="small">{p.status === "pending" ? "Cancel this request?" : "Remove? Patients waiting on you there will be declined. Approved pledges stay."}</span>
                    <button className="btn small-btn" onClick={() => act(() => api(`/api/fund/partnerships/${p.clinic_id}`, { method: "DELETE" }))}>Yes, {p.status === "pending" ? "cancel" : "remove"}</button>
                    <button className="btn ghost small-btn" onClick={() => setConfirm(null)}>Keep</button>
                  </span>
                ) : (
                  <button className="btn ghost small-btn" onClick={() => setConfirm(p.clinic_id)}>{p.status === "pending" ? "Cancel request" : "Remove"}</button>
                )}
              </td>
            </tr>
          ))}
          {d.partnerships.length === 0 && <tr><td colSpan={6} className="muted">No partner clinics yet. Click "Add partner clinic" to send a request.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

/** Clinic portal: answer partnership requests and see partner funds. */
export function ClinicPartnerships({ rows, onChange }: { rows: Partnership[]; onChange: () => void }) {
  const [confirm, setConfirm] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const act = async (path: string, method = "POST") => {
    setErr("");
    try { await api(path, { method }); setConfirm(null); onChange(); } catch (e) { setErr(errText(e)); }
  };
  const pending = rows.filter((r) => r.status === "pending");
  const others = rows.filter((r) => r.status !== "pending");
  return (
    <>
      {pending.length > 0 && (
        <div className="card review-card">
          <h2>Funds asking to partner with you</h2>
          {pending.map((r) => (
            <div key={r.fund_id} className="add-row">
              <span><strong>{r.fund_name}</strong> <span className="muted small">{r.fund_description} · asked {day(r.created_at)}</span></span>
              <span className="decide">
                <button className="btn small-btn" onClick={() => act(`/api/clinic/partnerships/${r.fund_id}/accept`)}>Accept</button>
                <button className="btn ghost small-btn" onClick={() => act(`/api/clinic/partnerships/${r.fund_id}/decline`)}>Decline</button>
              </span>
            </div>
          ))}
          <p className="muted small">Once you accept, your patients can be matched with this fund, and the fund sees the cases it's eligible for.</p>
        </div>
      )}
      <div className="card">
        <h2>Partner funds</h2>
        {err && <p className="error small" role="alert">{err}</p>}
        <table className="grid">
          <thead><tr><th>Fund</th><th>About</th><th>Status</th><th>Accepted</th><th /></tr></thead>
          <tbody>
            {others.map((r) => (
              <tr key={r.fund_id}>
                <td>{r.fund_name}</td>
                <td className="muted small">{r.fund_description}</td>
                <td><span className={`badge ${r.status === "accepted" ? "approved" : "declined"}`}>{r.status === "accepted" ? "Accepted" : "You declined"}</span></td>
                <td>{day(r.accepted_at)}</td>
                <td className="num">
                  {r.status === "accepted" && (confirm === r.fund_id ? (
                    <span className="decide confirm-inline">
                      <span className="small">End partnership? Pledges still waiting on this fund will be declined.</span>
                      <button className="btn small-btn" onClick={() => act(`/api/clinic/partnerships/${r.fund_id}`, "DELETE")}>Yes, end it</button>
                      <button className="btn ghost small-btn" onClick={() => setConfirm(null)}>Keep</button>
                    </span>
                  ) : <button className="btn ghost small-btn" onClick={() => setConfirm(r.fund_id)}>End partnership</button>)}
                </td>
              </tr>
            ))}
            {others.length === 0 && <tr><td colSpan={5} className="muted">No partner funds yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
