import { useEffect, useState } from "react";
import { api, ApiError, money } from "../api";
import { formatDate, Lang, STRINGS, Strings } from "../i18n";
import { STATE_NAMES } from "../states";

type Pledge = { fund_name: string; fund_kind: string; status: string; amount: number; category: "procedure" | "practical" };
type View = {
  clinic_name: string; clinic_phone: string; appointment_date: string; language: Lang;
  submitted: boolean; procedure_cost: number; pledges: Pledge[];
  approved_total: number; pending_total: number; you_may_owe: number; states: string[];
  practical_approved: number; practical_pending: number; questions?: string[];
};
type YN = boolean | null;
type Answers = {
  state: string; household_size: number; income_amount: number | null; income_period: "month" | "year";
  lmp_date: string; lmp_unknown: boolean; gestational_weeks: number | null; weeks_unknown: boolean;
  needs_travel: YN; age: number | null; age_skipped: boolean;
  travel_miles: number | null; nights_away: number | null; meal_days: number | null; childcare_days: number | null;
  insurance_coverage: "yes" | "no" | "unsure" | null; unhoused: YN; judicial_bypass: YN;
  first_name: string; last_name: string; phone: string; email: string; notify_pref: "text" | "email" | "";
  skipped: Record<string, boolean>;
};

const TRAVEL_DETAILS = ["travel_miles", "nights_away", "meal_days", "childcare_days"];
const OPTIONAL_STEPS = new Set(["age", ...TRAVEL_DETAILS, "insurance", "unhoused", "judicial_bypass", "contact"]);

// Which screens this patient sees: core questions, plus whatever the clinic's funds need or asked for.
function stepsFor(questions: string[], a: Answers): string[] {
  const has = (q: string) => questions.includes(q);
  const steps = ["state", "household", "income", "pregnancy"];
  if (has("age")) steps.push("age");
  steps.push("travel");
  if (a.needs_travel) TRAVEL_DETAILS.forEach((q) => has(q) && steps.push(q));
  if (has("insurance")) steps.push("insurance");
  if (has("unhoused")) steps.push("unhoused");
  if (has("judicial_bypass") && (a.age == null || a.age_skipped || a.age < 18)) steps.push("judicial_bypass");
  if (has("contact")) steps.push("contact");
  steps.push("review");
  return steps;
}

export default function Patient({ token }: { token: string }) {
  const [view, setView] = useState<View | null>(null);
  const [lang, setLang] = useState<Lang | null>(null);
  const [fatal, setFatal] = useState<{ kind: "expired" | "bad" | "error"; phone?: string; clinic?: string } | null>(null);
  const [stage, setStage] = useState<"lang" | "intro" | "form" | "done">("lang");

  const load = async () => {
    try {
      const v = await api<View>(`/api/p/${token}`);
      setView(v);
      if (v.submitted) {
        setLang((l) => l ?? v.language);
        setStage("done");
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 410) {
        const d = e.detail as { clinic_phone: string; clinic_name: string };
        setFatal({ kind: "expired", phone: d.clinic_phone, clinic: d.clinic_name });
      } else if (e instanceof ApiError && e.status === 404) setFatal({ kind: "bad" });
      else setFatal({ kind: "error" });
    }
  };
  useEffect(() => { load(); }, [token]);

  const t = STRINGS[lang ?? view?.language ?? "en"];

  if (fatal) {
    return (
      <PatientShell t={t} lang={lang ?? "en"} setLang={setLang}>
        <div className="card center">
          <h1>{fatal.kind === "expired" ? t.expired : fatal.kind === "bad" ? t.badLink : t.error}</h1>
          {fatal.phone && (
            <p className="lead">{t.callClinic}<br /><a className="phone" href={`tel:${fatal.phone}`}>{fatal.clinic} · {fatal.phone}</a></p>
          )}
        </div>
      </PatientShell>
    );
  }
  if (!view) return <PatientShell t={t} lang="en" setLang={setLang}><p className="muted center">{t.loading}</p></PatientShell>;

  const chooseLang = async (l: Lang) => {
    setLang(l);
    document.documentElement.lang = l;
    api(`/api/p/${token}/language`, { body: { language: l } }).catch(() => {});
    setStage("intro");
  };

  return (
    <PatientShell t={t} lang={lang ?? view.language} setLang={stage === "lang" ? undefined : chooseLangQuiet(setLang, token)} footer={view}>
      {stage === "lang" && (
        <div className="card center">
          <div className="brand-big" aria-hidden>Calma</div>
          <h1>What language do you want to use?<br /><span className="muted">¿Qué idioma quiere usar?</span></h1>
          <div className="choice-row">
            <button className="btn big" onClick={() => chooseLang("en")}>English</button>
            <button className="btn big" onClick={() => chooseLang("es")}>Español</button>
          </div>
        </div>
      )}
      {stage === "intro" && (
        <div className="card">
          <h1>{t.hello}</h1>
          <p className="lead">{t.introBody}</p>
          <p className="muted">{t.appointment}: <strong>{view.clinic_name}</strong>, {formatDate(view.appointment_date, lang ?? "en")}</p>
          <button className="btn big" onClick={() => setStage("form")}>{t.start}</button>
        </div>
      )}
      {stage === "form" && (
        <ScreeningForm t={t} lang={lang ?? "en"} states={view.states} questions={view.questions ?? []} token={token} onDone={(v) => { setView(v); setStage("done"); }} />
      )}
      {stage === "done" && <Results t={t} view={view} lang={lang ?? view.language} onRefresh={load} />}
    </PatientShell>
  );
}

function chooseLangQuiet(setLang: (l: Lang) => void, token: string) {
  return (l: Lang) => {
    setLang(l);
    document.documentElement.lang = l;
    api(`/api/p/${token}/language`, { body: { language: l } }).catch(() => {});
  };
}

function PatientShell({ t, lang, setLang, footer, children }: {
  t: Strings; lang: Lang; setLang?: (l: Lang) => void; footer?: View; children: React.ReactNode;
}) {
  return (
    <div className="patient">
      <header className="patient-top">
        <span className="brand">Calma</span>
        {setLang && (
          <div className="lang-toggle" role="group" aria-label="Language / Idioma">
            <button aria-pressed={lang === "en"} onClick={() => setLang("en")}>EN</button>
            <button aria-pressed={lang === "es"} onClick={() => setLang("es")}>ES</button>
          </div>
        )}
      </header>
      <main className="patient-main">{children}</main>
      {footer && (
        <footer className="clinic-bar">
          {t.questions} <strong>{footer.clinic_name}</strong>:{" "}
          <a className="phone" href={`tel:${footer.clinic_phone}`}>{footer.clinic_phone}</a>
        </footer>
      )}
    </div>
  );
}

function ScreeningForm({ t, lang, states, questions, token, onDone }: {
  t: Strings; lang: Lang; states: string[]; questions: string[]; token: string; onDone: (v: View) => void;
}) {
  const [i, setI] = useState(0);
  const [a, setA] = useState<Answers>({
    state: "", household_size: 1, income_amount: null, income_period: "month",
    lmp_date: "", lmp_unknown: false, gestational_weeks: null, weeks_unknown: false,
    needs_travel: null, age: null, age_skipped: false,
    travel_miles: null, nights_away: null, meal_days: null, childcare_days: null,
    insurance_coverage: null, unhoused: null, judicial_bypass: null,
    first_name: "", last_name: "", phone: "", email: "", notify_pref: "", skipped: {},
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const steps = stepsFor(questions, a);
  const step = steps[Math.min(i, steps.length - 1)];
  const set = (p: Partial<Answers>) => setA((x) => ({ ...x, ...p }));
  const next = () => setI((n) => Math.min(n + 1, steps.length - 1));
  const back = () => setI((n) => Math.max(n - 1, 0));
  const skip = () => { set({ skipped: { ...a.skipped, [step]: true } }); next(); };
  const today = new Date().toISOString().slice(0, 10);

  const canNext: Record<string, boolean> = {
    state: !!a.state,
    household: a.household_size >= 1,
    income: a.income_amount != null && a.income_amount >= 0,
    pregnancy: a.lmp_unknown
      ? a.weeks_unknown || (a.gestational_weeks != null && a.gestational_weeks >= 1 && a.gestational_weeks <= 42)
      : !!a.lmp_date && a.lmp_date <= today,
    age: a.age_skipped || (a.age != null && a.age >= 10 && a.age <= 60),
    travel: a.needs_travel != null,
    travel_miles: a.travel_miles != null && a.travel_miles >= 0,
    nights_away: a.nights_away != null, meal_days: a.meal_days != null, childcare_days: a.childcare_days != null,
    insurance: a.insurance_coverage != null, unhoused: a.unhoused != null, judicial_bypass: a.judicial_bypass != null,
    contact: true, review: true,
  };

  const monthly = a.income_amount == null ? null : a.income_period === "year" ? Math.round(a.income_amount / 12) : a.income_amount;
  const val = <T,>(q: string, v: T): T | null => (a.skipped[q] || !steps.includes(q) ? null : v);

  const submit = async () => {
    setBusy(true); setErr("");
    const contactOn = steps.includes("contact") && !a.skipped.contact;
    try {
      const v = await api<View>(`/api/p/${token}/screening`, {
        body: {
          state: a.state, household_size: a.household_size, monthly_income: monthly,
          lmp_date: a.lmp_unknown ? null : a.lmp_date,
          gestational_weeks: a.lmp_unknown && !a.weeks_unknown ? a.gestational_weeks : null,
          needs_travel: a.needs_travel,
          age: val("age", a.age_skipped ? null : a.age),
          travel_miles: val("travel_miles", a.travel_miles), nights_away: val("nights_away", a.nights_away),
          meal_days: val("meal_days", a.meal_days), childcare_days: val("childcare_days", a.childcare_days),
          insurance_coverage: val("insurance", a.insurance_coverage), unhoused: val("unhoused", a.unhoused),
          judicial_bypass: val("judicial_bypass", a.judicial_bypass),
          contact: contactOn ? {
            first_name: a.first_name || null, last_name: a.last_name || null, phone: a.phone || null,
            email: a.email || null, notify_pref: a.notify_pref || null,
          } : null,
        },
      });
      onDone(v);
    } catch {
      setErr(t.error);
    } finally {
      setBusy(false);
    }
  };

  const yn = (v: YN) => (v == null ? t.skipped : v ? t.yes : t.no);
  const count = (v: number | null) => (v == null ? t.skipped : v === 0 ? t.none : v >= 3 ? t.threePlus : String(v));
  const YesNo = ({ value, onPick, unsure }: { value: unknown; onPick: (v: never) => void; unsure?: boolean }) => (
    <div className="choice-row">
      {([[true, t.yes], [false, t.no], ...(unsure ? [["unsure", t.notSure]] : [])] as [unknown, string][]).map(([v, label]) => {
        const real = unsure ? (v === true ? "yes" : v === false ? "no" : v) : v;
        return (
          <button key={label} type="button" className={`btn big ${value === real ? "" : "ghost"}`} aria-pressed={value === real}
            onClick={() => onPick(real as never)}>{label}</button>
        );
      })}
    </div>
  );
  const Counter = ({ field }: { field: "nights_away" | "meal_days" | "childcare_days" }) => (
    <div className="choice-row count-row">
      {[0, 1, 2, 3].map((n) => (
        <button key={n} type="button" className={`btn ${a[field] === n ? "" : "ghost"}`} aria-pressed={a[field] === n}
          onClick={() => set({ [field]: n } as Partial<Answers>)}>{n === 0 ? t.none : n === 3 ? t.threePlus : n}</button>
      ))}
    </div>
  );

  const review: [string, string, string][] = [
    [t.state, STATE_NAMES[a.state] ?? a.state, "state"],
    [t.household, String(a.household_size), "household"],
    [t.income, `${money(a.income_amount)} ${a.income_period === "year" ? t.eachYear : t.eachMonth}`, "income"],
    [a.lmp_unknown ? t.weeksPregnant : t.lmp,
      a.lmp_unknown ? (a.weeks_unknown ? t.notSure : String(a.gestational_weeks)) : formatDate(a.lmp_date, lang), "pregnancy"],
    ...(steps.includes("age") ? [[t.age, a.age_skipped ? t.skipped : String(a.age), "age"] as [string, string, string]] : []),
    [t.travel, yn(a.needs_travel), "travel"],
    ...(steps.includes("travel_miles") ? [[t.milesLabel, a.skipped.travel_miles ? t.skipped : `${a.travel_miles} ${t.miles}`, "travel_miles"] as [string, string, string]] : []),
    ...(steps.includes("nights_away") ? [[t.nightsLabel, a.skipped.nights_away ? t.skipped : count(a.nights_away), "nights_away"] as [string, string, string]] : []),
    ...(steps.includes("meal_days") ? [[t.mealsLabel, a.skipped.meal_days ? t.skipped : count(a.meal_days), "meal_days"] as [string, string, string]] : []),
    ...(steps.includes("childcare_days") ? [[t.childcareLabel, a.skipped.childcare_days ? t.skipped : count(a.childcare_days), "childcare_days"] as [string, string, string]] : []),
    ...(steps.includes("insurance") ? [[t.insuranceLabel, a.skipped.insurance || !a.insurance_coverage ? t.skipped : a.insurance_coverage === "unsure" ? t.notSure : a.insurance_coverage === "yes" ? t.yes : t.no, "insurance"] as [string, string, string]] : []),
    ...(steps.includes("unhoused") ? [[t.unhousedLabel, a.skipped.unhoused ? t.skipped : yn(a.unhoused), "unhoused"] as [string, string, string]] : []),
    ...(steps.includes("judicial_bypass") ? [[t.bypassLabel, a.skipped.judicial_bypass ? t.skipped : yn(a.judicial_bypass), "judicial_bypass"] as [string, string, string]] : []),
    ...(steps.includes("contact") ? [[t.contactLabel, a.skipped.contact || !(a.first_name || a.phone || a.email) ? t.skipped : [a.first_name, a.last_name, a.phone, a.email].filter(Boolean).join(" · "), "contact"] as [string, string, string]] : []),
  ];

  return (
    <form className="card" onSubmit={(e) => { e.preventDefault(); if (step === "review") submit(); else if (canNext[step]) next(); }}>
      <div className="progress" aria-hidden><div style={{ width: `${((i + 1) / steps.length) * 100}%` }} /></div>
      <p className="muted small">{t.step(Math.min(i, steps.length - 1) + 1, steps.length)}{OPTIONAL_STEPS.has(step) && ` · ${t.optional}`}</p>

      {step === "state" && (
        <Question id="q-state" label={t.stateQ} hint={t.stateHint}>
          <select id="q-state" className="input big" value={a.state} onChange={(e) => set({ state: e.target.value })}>
            <option value="">{t.choose}</option>
            {[...states].sort((x, y) => (STATE_NAMES[x] ?? x).localeCompare(STATE_NAMES[y] ?? y)).map((s) => <option key={s} value={s}>{STATE_NAMES[s] ?? s}</option>)}
          </select>
        </Question>
      )}
      {step === "household" && (
        <Question id="q-house" label={t.householdQ} hint={t.householdHint}>
          <div className="stepper">
            <button type="button" className="btn ghost" aria-label="−" onClick={() => set({ household_size: Math.max(1, a.household_size - 1) })}>−</button>
            <input id="q-house" className="input big num-input" type="number" min={1} max={20} value={a.household_size}
              onChange={(e) => set({ household_size: Math.max(1, Number(e.target.value) || 1) })} />
            <button type="button" className="btn ghost" aria-label="+" onClick={() => set({ household_size: Math.min(20, a.household_size + 1) })}>+</button>
          </div>
        </Question>
      )}
      {step === "income" && (
        <Question id="q-income" label={t.incomeQ2} hint={t.incomeHint}>
          <div className="money-input">
            <span>$</span>
            <input id="q-income" className="input big" type="number" inputMode="numeric" min={0} placeholder="0"
              value={a.income_amount ?? ""} onChange={(e) => set({ income_amount: e.target.value === "" ? null : Number(e.target.value) })} />
          </div>
          <div className="lang-toggle period-toggle" role="group" aria-label={t.income}>
            <button type="button" aria-pressed={a.income_period === "month"} onClick={() => set({ income_period: "month" })}>{t.eachMonth}</button>
            <button type="button" aria-pressed={a.income_period === "year"} onClick={() => set({ income_period: "year" })}>{t.eachYear}</button>
          </div>
        </Question>
      )}
      {step === "pregnancy" && (
        !a.lmp_unknown ? (
          <Question id="q-lmp" label={t.lmpQ} hint={t.lmpHint}>
            <input id="q-lmp" className="input big" type="date" max={today} value={a.lmp_date} onChange={(e) => set({ lmp_date: e.target.value })} />
            <label className="check"><input type="checkbox" checked={a.lmp_unknown} onChange={(e) => set({ lmp_unknown: e.target.checked })} /> {t.lmpUnknown}</label>
          </Question>
        ) : (
          <Question id="q-weeks" label={t.weeksIfUnknown} hint={t.weeksHint}>
            <div className="money-input">
              <input id="q-weeks" className="input big num-input" type="number" min={1} max={42} disabled={a.weeks_unknown}
                value={a.gestational_weeks ?? ""} onChange={(e) => set({ gestational_weeks: e.target.value === "" ? null : Number(e.target.value) })} />
              <span className="muted">{t.weeks}</span>
            </div>
            <label className="check"><input type="checkbox" checked={a.weeks_unknown} onChange={(e) => set({ weeks_unknown: e.target.checked })} /> {t.notSure}</label>
            <button type="button" className="link small" onClick={() => set({ lmp_unknown: false })}>← {t.lmpQ}</button>
          </Question>
        )
      )}
      {step === "age" && (
        <Question id="q-age" label={t.ageQ} hint={t.ageHint}>
          <div className="money-input">
            <input id="q-age" className="input big num-input" type="number" min={10} max={60} disabled={a.age_skipped}
              value={a.age ?? ""} onChange={(e) => set({ age: e.target.value === "" ? null : Number(e.target.value) })} />
            <span className="muted">{t.years}</span>
          </div>
          <label className="check">
            <input type="checkbox" checked={a.age_skipped} onChange={(e) => set({ age_skipped: e.target.checked })} /> {t.skip}
          </label>
        </Question>
      )}
      {step === "travel" && (
        <Question id="q-travel" label={t.travelQ} hint={t.travelHint}>
          <YesNo value={a.needs_travel} onPick={(v) => set({ needs_travel: v })} />
        </Question>
      )}
      {step === "travel_miles" && (
        <Question id="q-miles" label={t.milesQ} hint={t.milesHint}>
          <div className="money-input">
            <input id="q-miles" className="input big num-input" type="number" min={0} max={3000}
              value={a.travel_miles ?? ""} onChange={(e) => set({ travel_miles: e.target.value === "" ? null : Number(e.target.value) })} />
            <span className="muted">{t.miles}</span>
          </div>
        </Question>
      )}
      {step === "nights_away" && <Question id="q-nights" label={t.nightsQ} hint={t.countHint}><Counter field="nights_away" /></Question>}
      {step === "meal_days" && <Question id="q-meals" label={t.mealsQ} hint={t.countHint}><Counter field="meal_days" /></Question>}
      {step === "childcare_days" && <Question id="q-care" label={t.childcareQ} hint={t.countHint}><Counter field="childcare_days" /></Question>}
      {step === "insurance" && (
        <Question id="q-ins" label={t.insuranceQ} hint={t.insuranceHint}>
          <YesNo unsure value={a.insurance_coverage} onPick={(v) => set({ insurance_coverage: v })} />
        </Question>
      )}
      {step === "unhoused" && (
        <Question id="q-unhoused" label={t.unhousedQ} hint={t.unhousedHint}>
          <YesNo value={a.unhoused} onPick={(v) => set({ unhoused: v })} />
        </Question>
      )}
      {step === "judicial_bypass" && (
        <Question id="q-bypass" label={t.bypassQ} hint={t.bypassHint}>
          <YesNo value={a.judicial_bypass} onPick={(v) => set({ judicial_bypass: v })} />
        </Question>
      )}
      {step === "contact" && (
        <Question id="q-first" label={t.contactQ} hint={t.contactHint}>
          <div className="contact-grid">
            <label>{t.firstName}<input id="q-first" className="input" value={a.first_name} onChange={(e) => set({ first_name: e.target.value })} autoComplete="given-name" /></label>
            <label>{t.lastName}<input className="input" value={a.last_name} onChange={(e) => set({ last_name: e.target.value })} autoComplete="family-name" /></label>
            <label>{t.phone}<input className="input" type="tel" value={a.phone} onChange={(e) => set({ phone: e.target.value })} autoComplete="tel" /></label>
            <label>{t.email}<input className="input" type="email" value={a.email} onChange={(e) => set({ email: e.target.value })} autoComplete="email" /></label>
            <label>{t.notifyPref}
              <select className="input" value={a.notify_pref} onChange={(e) => set({ notify_pref: e.target.value as Answers["notify_pref"] })}>
                <option value="">—</option><option value="text">{t.byText}</option><option value="email">{t.byEmail}</option>
              </select>
            </label>
          </div>
        </Question>
      )}
      {step === "review" && (
        <>
          <h1>{t.reviewTitle}</h1>
          <dl className="review">
            {review.map(([k, v, q]) => (
              <div key={q}>
                <dt>{k}</dt><dd>{v}</dd>
                <button type="button" className="link" onClick={() => { set({ skipped: { ...a.skipped, [q]: false } }); setI(steps.indexOf(q)); }}>{t.edit}</button>
              </div>
            ))}
          </dl>
          {err && <p className="error" role="alert">{err}</p>}
        </>
      )}

      <div className="nav-row">
        {i > 0 && <button type="button" className="btn ghost" onClick={back}>{t.back}</button>}
        {OPTIONAL_STEPS.has(step) && step !== "age" && step !== "contact" && (
          <button type="button" className="link" onClick={skip}>{t.skip}</button>
        )}
        {step === "review"
          ? <button type="submit" className="btn big" disabled={busy}>{busy ? t.sending : t.submit}</button>
          : <button type="submit" className="btn big" disabled={!canNext[step]}>{t.next}</button>}
      </div>
    </form>
  );
}

function Question({ id, label, hint, children }: { id: string; label: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="question">
      <label htmlFor={id}><h1>{label}</h1></label>
      <p className="muted">{hint}</p>
      {children}
    </div>
  );
}

function Results({ t, view, lang, onRefresh }: { t: Strings; view: View; lang: Lang; onRefresh: () => void }) {
  useEffect(() => {
    const id = setInterval(onRefresh, 30000);
    return () => clearInterval(id);
  }, []);
  const proc = view.pledges.filter((p) => p.category !== "practical");
  const prac = view.pledges.filter((p) => p.category === "practical");
  const List = ({ items }: { items: Pledge[] }) => (
    <ul className="pledge-list">
      {items.map((p) => (
        <li key={p.fund_name} className={`pledge ${p.status}`}>
          <div>
            <div className="fund-name">{p.fund_name}</div>
            <div className="muted small">{p.category === "practical" ? t.travelFund : p.fund_kind === "clinic" ? t.clinicFund : t.outsideFund}</div>
          </div>
          <div className="right">
            <div className="amount">{money(p.amount)}</div>
            <span className={`badge ${p.status}`}>{t.status[p.status]}</span>
          </div>
        </li>
      ))}
    </ul>
  );
  return (
    <div className="card">
      <h1>{view.pledges.length ? t.resultsTitle : t.noHelp}</h1>
      {!view.pledges.length && <p className="lead">{t.noHelpBody}</p>}
      {proc.length > 0 && <><h2>{t.visitHelpTitle}</h2><List items={proc} /></>}
      <dl className="totals">
        <div><dt>{t.visitCost}</dt><dd>{money(view.procedure_cost)}</dd></div>
        <div><dt>{t.helpApproved}</dt><dd className="accent">− {money(view.approved_total)}</dd></div>
        {view.pending_total > 0 && <div><dt>{t.helpWaiting}</dt><dd className="muted">{money(view.pending_total)}</dd></div>}
        <div className="owe"><dt>{t.youMayOwe}</dt><dd>{money(view.you_may_owe)}</dd></div>
      </dl>
      {view.pending_total > 0 && <p className="muted small">{t.owedNote}</p>}
      {prac.length > 0 && (
        <>
          <h2>{t.practicalTitle}</h2>
          <p className="muted small">{t.practicalNote}</p>
          <List items={prac} />
        </>
      )}
      <p className="muted">{t.appointment}: <strong>{view.clinic_name}</strong>, {formatDate(view.appointment_date, lang)}</p>
      <p className="note">{t.saveLink}</p>
    </div>
  );
}
