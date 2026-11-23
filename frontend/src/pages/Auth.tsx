import { useEffect, useState } from "react";
import { api, errText, navigate, setSession } from "../api";
import type { StaffUser } from "./Staff";

// Staff only. Patients never log in: they use the private link their clinic sends.

function AuthShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="staff">
      <header className="staff-top"><span className="brand">Calma</span><div className="staff-title">{title}</div></header>
      <main className="staff-main auth-main">{children}</main>
      <footer className="demo-note">For clinic, abortion fund and Calma staff. Patients: please use the link your clinic sent you.</footer>
    </div>
  );
}

function PasswordInput({ id, label, value, onChange, autoComplete, hint }: {
  id: string; label: string; value: string; onChange: (v: string) => void; autoComplete: string; hint?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <span className="pw-row">
        <input id={id} className="input" type={show ? "text" : "password"} value={value} required
          autoComplete={autoComplete} onChange={(e) => onChange(e.target.value)} />
        <button type="button" className="link small" onClick={() => setShow((s) => !s)} aria-label={show ? `Hide ${label}` : `Show ${label}`}>
          {show ? "Hide" : "Show"}
        </button>
      </span>
      {hint && <span className="muted small">{hint}</span>}
    </label>
  );
}

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const r = await api<{ token: string; user: StaffUser }>("/api/auth/login", { body: { email, password } });
      setSession(r.token, r.user);
      navigate(`/${r.user.role}`);
    } catch (e) { setErr(errText(e)); setPassword(""); } finally { setBusy(false); }
  };
  return (
    <AuthShell title="Staff log in">
      <form className="card auth-card" onSubmit={submit}>
        <h1>Log in</h1>
        <label className="field" htmlFor="li-email">
          <span>Email</span>
          <input id="li-email" className="input" type="email" value={email} required autoComplete="username"
            onChange={(e) => setEmail(e.target.value)} />
        </label>
        <PasswordInput id="li-pw" label="Password" value={password} onChange={setPassword} autoComplete="current-password" />
        {err && <p className="error small" role="alert">{err}</p>}
        <button className="btn auth-btn" disabled={busy || !email || !password}>{busy ? "Logging in…" : "Log in"}</button>
        <p className="muted small center">New to Calma? <button type="button" className="link" onClick={() => navigate("/signup")}>Create an account</button></p>
      </form>
    </AuthShell>
  );
}

type Orgs = { clinics: { id: number; name: string; city: string; state: string }[]; funds: { id: number; name: string }[] };

export function Signup() {
  const [orgs, setOrgs] = useState<Orgs | null>(null);
  const [f, setF] = useState({ first_name: "", last_name: "", email: "", password: "", confirm_password: "", where: "" });
  const [err, setErr] = useState("");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<Orgs>("/api/auth/organizations").then(setOrgs).catch((e) => setErr(errText(e))); }, []);
  const set = (p: Partial<typeof f>) => setF((x) => ({ ...x, ...p }));
  const mismatch = f.confirm_password.length > 0 && f.password !== f.confirm_password;
  const tooShort = f.password.length > 0 && f.password.length < 10;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    const [role, id] = f.where.split(":");
    try {
      const r = await api<{ message: string }>("/api/auth/signup", {
        body: { first_name: f.first_name, last_name: f.last_name, email: f.email, password: f.password,
                confirm_password: f.confirm_password, role, org_id: id ? Number(id) : null },
      });
      setDone(r.message);
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };

  if (done) {
    return (
      <AuthShell title="Create account">
        <div className="card auth-card">
          <h1>Thanks!</h1>
          <p className="lead-sm">{done}</p>
          <p className="muted small">An administrator checks that you work where you said, so patients' information stays protected.</p>
          <button className="btn auth-btn" onClick={() => navigate("/login")}>Back to log in</button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Create account">
      <form className="card auth-card" onSubmit={submit}>
        <h1>Create an account</h1>
        <div className="two-fields">
          <label className="field" htmlFor="su-first"><span>First name</span>
            <input id="su-first" className="input" value={f.first_name} required autoComplete="given-name" onChange={(e) => set({ first_name: e.target.value })} />
          </label>
          <label className="field" htmlFor="su-last"><span>Last name</span>
            <input id="su-last" className="input" value={f.last_name} required autoComplete="family-name" onChange={(e) => set({ last_name: e.target.value })} />
          </label>
        </div>
        <label className="field" htmlFor="su-email"><span>Work email</span>
          <input id="su-email" className="input" type="email" value={f.email} required autoComplete="email" onChange={(e) => set({ email: e.target.value })} />
        </label>
        <label className="field" htmlFor="su-where"><span>Where do you work?</span>
          <select id="su-where" className="input" value={f.where} required onChange={(e) => set({ where: e.target.value })}>
            <option value="">Choose one</option>
            <optgroup label="Clinics">{orgs?.clinics.map((c) => <option key={c.id} value={`clinic:${c.id}`}>{c.name} — {c.city}, {c.state}</option>)}</optgroup>
            <optgroup label="Abortion funds">{orgs?.funds.map((x) => <option key={x.id} value={`fund:${x.id}`}>{x.name}</option>)}</optgroup>
            <optgroup label="Calma"><option value="admin">Calma administrator</option></optgroup>
          </select>
        </label>
        <PasswordInput id="su-pw" label="Password" value={f.password} onChange={(v) => set({ password: v })} autoComplete="new-password"
          hint="At least 10 characters. A short phrase of a few words works well." />
        <PasswordInput id="su-pw2" label="Confirm password" value={f.confirm_password} onChange={(v) => set({ confirm_password: v })} autoComplete="new-password" />
        {tooShort && <p className="muted small">{10 - f.password.length} more characters needed.</p>}
        {mismatch && <p className="error small">The passwords don't match yet.</p>}
        {err && <p className="error small" role="alert">{err}</p>}
        <button className="btn auth-btn" disabled={busy || mismatch || tooShort || !f.where}>{busy ? "Creating…" : "Create account"}</button>
        <p className="muted small center">Already have an account? <button type="button" className="link" onClick={() => navigate("/login")}>Log in</button></p>
      </form>
    </AuthShell>
  );
}
