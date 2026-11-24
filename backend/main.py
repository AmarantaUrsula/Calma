"""Calma API: patient, clinic and fund portals.

    cd calma
    python -m backend.seed                         # create demo data
    uvicorn backend.main:app --port 8020           # run the API

DEMO-ONLY AUTH: staff "log in" by picking a seeded user. Sessions live in
memory and expire after 30 idle minutes. A real deployment needs proper
authentication (SSO/MFA), HTTPS, encryption at rest and BAAs (see DESIGN.md).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from typing import Iterator, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import auth, clock
from .db import audit, connect, init_schema
from . import questions as Q
from .matching import FundRule, Screening, income_fpl_pct, match
from .proposals import row_to_rules

log = logging.getLogger("calma")


def _needs_demo_data(path) -> bool:
    """True if there's no database yet, or it has no accounts (e.g. an earlier start failed halfway)."""
    if not path.exists() or path.stat().st_size == 0:
        return True
    try:
        conn = sqlite3.connect(path)
        try:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        finally:
            conn.close()
    except sqlite3.Error:
        return True


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """On start: create demo data if there's no database yet (fresh Render instance).
    Then run the background scheduler for fund website checks (off when CALMA_SCHEDULER=0)."""
    from .db import db_path

    if os.environ.get("CALMA_SEED_IF_EMPTY") == "1" and _needs_demo_data(db_path()):
        from .seed import reset

        reset()
    task = None
    if os.environ.get("CALMA_SCHEDULER", "1") != "0":
        task = asyncio.create_task(_scheduler_loop())
    yield
    if task:
        task.cancel()


async def _scheduler_loop() -> None:
    from . import website_check

    poll = float(os.environ.get("CALMA_CHECK_POLL_HOURS", "6")) * 3600
    await asyncio.sleep(30)  # let the server finish starting
    while True:
        conn = connect()
        try:
            init_schema(conn)
            results = await website_check.run(conn, model_for_extraction())
            conn.commit()
            for r in results:
                log.info("website check %s: %s", r.fund_name, r.status)
        except Exception:
            log.exception("website check run failed")
        finally:
            conn.close()
        await asyncio.sleep(poll)


app = FastAPI(title="Calma API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5178", "http://127.0.0.1:5178"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION_IDLE = timedelta(minutes=30)
_sessions: dict[str, tuple[int, datetime]] = {}

US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
    "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
]


# ---------- plumbing ----------

def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    init_schema(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def case_ref(case_id: int) -> str:
    return f"C-{1000 + case_id}"


def month_key() -> str:
    return clock.today().isoformat()[:7]


class User(BaseModel):
    """What the app knows about a signed-in staff member. Deliberately has no password field."""
    id: int
    name: str
    role: str
    clinic_id: int | None
    fund_id: int | None
    email: str | None = None


def user_from_row(r: sqlite3.Row) -> User:
    return User(id=r["id"], name=r["name"], role=r["role"], clinic_id=r["clinic_id"], fund_id=r["fund_id"],
                email=r["email"])


def current_user(authorization: str = Header(default=""), db: sqlite3.Connection = Depends(get_db)) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    key = hashlib.sha256(token.encode()).hexdigest()  # sessions are kept by token hash, not the token itself
    entry = _sessions.get(key)
    if not entry or clock.now() - entry[1] > SESSION_IDLE:
        _sessions.pop(key, None)
        raise HTTPException(401, "Please log in again.")
    row = db.execute("SELECT * FROM users WHERE id = ?", (entry[0],)).fetchone()
    if not row or row["status"] != "active":  # disabled accounts are signed out right away
        _sessions.pop(key, None)
        raise HTTPException(401, "Please log in again.")
    _sessions[key] = (entry[0], clock.now())
    return user_from_row(row)


def require(role: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role != role:
            raise HTTPException(403, "Not allowed for your role.")
        return user
    return dep


def approved_rules(db: sqlite3.Connection, fund_ids: list[int]) -> list[FundRule]:
    if not fund_ids:
        return []
    q = f"""
        SELECT f.id AS fund_id, f.name AS fund_name, f.kind, c.*
        FROM funds f
        JOIN fund_criteria c ON c.fund_id = f.id AND c.status = 'approved'
        WHERE f.id IN ({','.join('?' * len(fund_ids))})
          AND c.version = (SELECT MAX(version) FROM fund_criteria
                           WHERE fund_id = f.id AND status = 'approved')
    """
    rules = []
    for r in db.execute(q, fund_ids).fetchall():
        v = row_to_rules(r)
        rules.append(FundRule(
            fund_id=r["fund_id"], fund_name=r["fund_name"], kind=r["kind"], criteria_id=r["id"],
            states=tuple(v["states"]), income_max_fpl_pct=v["income_max_fpl_pct"],
            gest_min_weeks=v["gest_min_weeks"], gest_max_weeks=v["gest_max_weeks"],
            requires_travel=v["requires_travel"], max_age=v["max_age"],
            pledge_kind=v["pledge_kind"], pledge_value=v["pledge_value"], pledge_cap=v["pledge_cap"],
            state_basis=v["state_basis"], support_type=v["support_type"],
            rate_per_mile_cents=v["rate_per_mile_cents"], rate_per_night=v["rate_per_night"],
            rate_per_meal_day=v["rate_per_meal_day"], rate_per_childcare_day=v["rate_per_childcare_day"],
            no_insurance_only=v["no_insurance_only"], extra_questions=tuple(v["extra_questions"]),
        ))
    return rules


def clinic_fund_ids(db: sqlite3.Connection, clinic_id: int) -> list[int]:
    """The clinic's own funds plus every partner fund."""
    rows = db.execute(
        """SELECT id FROM funds WHERE owner_clinic_id = ?
           UNION SELECT p.fund_id FROM clinic_fund_partnerships p JOIN funds f ON f.id = p.fund_id
                 WHERE p.clinic_id = ? AND p.status = 'accepted' AND f.reference_only = 0""",
        (clinic_id, clinic_id),
    ).fetchall()
    return [r[0] for r in rows]


def _opt_bool(v):
    return None if v is None else bool(v)


def screening_of(case: sqlite3.Row) -> Screening:
    return Screening(
        state=case["state"], household_size=case["household_size"], monthly_income=case["monthly_income"],
        gestational_weeks=case["gestational_weeks"], needs_travel=bool(case["needs_travel"]), age=case["age"],
        care_state=case["care_state"], travel_miles=case["travel_miles"], nights_away=case["nights_away"],
        meal_days=case["meal_days"], childcare_days=case["childcare_days"],
        insurance_coverage=case["insurance_coverage"], unhoused=_opt_bool(case["unhoused"]),
        judicial_bypass=_opt_bool(case["judicial_bypass"]),
    )


# Answers by question id (for showing staff only what they asked).
ANSWER_FIELDS = {
    "state": ["state"], "household": ["household_size"], "income": ["monthly_income"],
    "pregnancy": ["gestational_weeks"], "travel": ["needs_travel"], "age": ["age"],
    "travel_miles": ["travel_miles"], "nights_away": ["nights_away"], "meal_days": ["meal_days"],
    "childcare_days": ["childcare_days"], "insurance": ["insurance_coverage"], "unhoused": ["unhoused"],
    "judicial_bypass": ["judicial_bypass"],
}


def answers_of(case: sqlite3.Row, question_ids: set[str] | None = None) -> dict:
    s = screening_of(case)
    out: dict = {"care_state": s.care_state}
    for q, fields in ANSWER_FIELDS.items():
        if question_ids is None or q in question_ids:
            for f in fields:
                out[f] = getattr(s, f)
    return out


def fund_month_used(db: sqlite3.Connection, fund_id: int) -> int:
    row = db.execute(
        """SELECT COALESCE(SUM(approved_amount), 0) FROM pledges
           WHERE fund_id = ? AND status IN ('approved', 'paid') AND substr(decided_at, 1, 7) = ?""",
        (fund_id, month_key()),
    ).fetchone()
    return row[0]


def pledge_rows(db: sqlite3.Connection, where: str, params: tuple) -> list[sqlite3.Row]:
    return db.execute(
        f"""SELECT p.*, f.name AS fund_name, f.kind AS fund_kind, c.clinic_id, c.appointment_date,
                   c.procedure_cost, c.status AS case_status, c.state, c.household_size,
                   c.monthly_income, c.gestational_weeks, c.needs_travel, c.submitted_at, cl.name AS clinic_name
            FROM pledges p
            JOIN funds f ON f.id = p.fund_id
            JOIN cases c ON c.id = p.case_id
            JOIN clinics cl ON cl.id = c.clinic_id
            WHERE {where}
            ORDER BY c.appointment_date, p.id""",
        params,
    ).fetchall()


# Decision policy: clinics and funds approve or decline each pledge within this many hours of the
# patient submitting the form. Shown to patients ("check back by...") and to staff ("decide by...").
# Pledges past the deadline are flagged as overdue; they are never approved or declined automatically.
def decision_hours() -> int:
    return int(os.environ.get("CALMA_DECISION_HOURS", "24"))


def decide_by(submitted_at: str | None) -> str | None:
    if not submitted_at:
        return None
    return (datetime.fromisoformat(submitted_at) + timedelta(hours=decision_hours())).isoformat(timespec="seconds")


def is_overdue(status: str, submitted_at: str | None) -> bool:
    due = decide_by(submitted_at)
    return status == "pending" and due is not None and clock.now() > datetime.fromisoformat(due)


def pledge_out(p: sqlite3.Row) -> dict:
    return {
        "decide_by": decide_by(p["submitted_at"]), "overdue": is_overdue(p["status"], p["submitted_at"]),
        "id": p["id"], "case_id": p["case_id"], "case_ref": case_ref(p["case_id"]),
        "fund_id": p["fund_id"], "fund_name": p["fund_name"], "fund_kind": p["fund_kind"],
        "suggested_amount": p["suggested_amount"], "approved_amount": p["approved_amount"],
        "status": p["status"], "reasons": json.loads(p["reasons"]), "category": p["category"],
        "decided_at": p["decided_at"], "paid_at": p["paid_at"],
    }


def approved_total_excluding(db: sqlite3.Connection, case_id: int, pledge_id: int) -> int:
    row = db.execute(
        """SELECT COALESCE(SUM(approved_amount), 0) FROM pledges
           WHERE case_id = ? AND id != ? AND status IN ('approved', 'paid') AND category = 'procedure'""",
        (case_id, pledge_id),
    ).fetchone()
    return row[0]


class Decision(BaseModel):
    decision: Literal["approve", "decline"]
    amount: int | None = Field(default=None, ge=1)


def decide_pledge(db: sqlite3.Connection, user: User, p: sqlite3.Row, body: Decision) -> dict:
    if p["status"] != "pending":
        raise HTTPException(409, "This pledge was already decided.")
    if body.decision == "decline":
        db.execute(
            "UPDATE pledges SET status='declined', decided_by=?, decided_at=? WHERE id=?",
            (user.id, clock.now_iso(), p["id"]),
        )
        audit(db, f"user:{user.id}", "pledge_declined", p["case_id"], {"pledge_id": p["id"]})
        return {"ok": True}

    amount = body.amount or p["suggested_amount"]
    if p["category"] == "procedure":
        room = p["procedure_cost"] - approved_total_excluding(db, p["case_id"], p["id"])
        if amount > room:
            raise HTTPException(409, f"Approved pledges can't exceed the procedure cost. At most ${room} is left.")
    fund = db.execute("SELECT * FROM funds WHERE id = ?", (p["fund_id"],)).fetchone()
    if fund["kind"] == "clinic" and fund["monthly_limit"] is not None:
        left = fund["monthly_limit"] - fund_month_used(db, fund["id"])
        if amount > left:
            raise HTTPException(409, f"Over this month's limit for {fund['name']}. ${left} left this month.")
    db.execute(
        "UPDATE pledges SET status='approved', approved_amount=?, decided_by=?, decided_at=? WHERE id=?",
        (amount, user.id, clock.now_iso(), p["id"]),
    )
    audit(db, f"user:{user.id}", "pledge_approved", p["case_id"], {"pledge_id": p["id"], "amount": amount})
    return {"ok": True}


def maybe_close_case(db: sqlite3.Connection, case_id: int) -> None:
    case = db.execute("SELECT status FROM cases WHERE id = ?", (case_id,)).fetchone()
    if case["status"] != "appointment_done":
        return
    open_ = db.execute(
        "SELECT COUNT(*) FROM pledges WHERE case_id = ? AND status IN ('pending', 'approved')", (case_id,)
    ).fetchone()[0]
    if open_ == 0:
        db.execute("UPDATE cases SET status = 'closed' WHERE id = ?", (case_id,))
        db.execute("DELETE FROM case_contacts WHERE case_id = ?", (case_id,))  # retention: contact details go when the case closes
        audit(db, "system", "case_closed", case_id)


# ---------- home ----------

# In production (Render), the built React app lives here and this server serves it too.
WEB_DIST = Path(os.environ.get("CALMA_WEB_DIST", Path(__file__).resolve().parent.parent / "frontend" / "dist"))


@app.get("/api/health", include_in_schema=False)
def health() -> dict:
    return {"ok": True}


@app.get("/", include_in_schema=False)
def home():
    """Production: serve the app. Local development: the API is on 8020 and the app on 5178, so redirect."""
    if (WEB_DIST / "index.html").exists():
        return FileResponse(WEB_DIST / "index.html")
    return RedirectResponse(os.environ.get("CALMA_WEB_URL", "http://localhost:5178"))


# ---------- staff accounts: create account, log in, log out ----------
# Patients never log in: they use the private link their clinic sends.

def _new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    _sessions[hashlib.sha256(token.encode()).hexdigest()] = (user_id, clock.now())
    return token


@app.get("/api/auth/organizations")
def organizations(db: sqlite3.Connection = Depends(get_db)) -> dict:
    """For the create-account form: which clinic or fund do you work for?"""
    clinics = db.execute("SELECT id, name, city, state FROM clinics ORDER BY name").fetchall()
    funds = db.execute("SELECT id, name FROM funds WHERE kind = 'independent' AND reference_only = 0 ORDER BY name").fetchall()
    return {"clinics": [dict(c) for c in clinics], "funds": [dict(f) for f in funds]}


class SignupBody(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)
    confirm_password: str = Field(min_length=1, max_length=200)
    role: Literal["clinic", "fund", "admin"]
    org_id: int | None = None


@app.post("/api/auth/signup", status_code=201)
def signup(body: SignupBody, db: sqlite3.Connection = Depends(get_db)) -> dict:
    """Create a staff account. It starts as 'pending' until a Calma admin approves it, so nobody
    can give themselves access to a clinic's or fund's patients just by signing up."""
    email = auth.normalize_email(body.email)
    first, last = body.first_name.strip(), body.last_name.strip()
    if not first or not last:
        raise HTTPException(422, "Please enter your first and last name.")
    if not auth.EMAIL_RE.match(email):
        raise HTTPException(422, "Please enter a valid email address.")
    if body.password != body.confirm_password:
        raise HTTPException(422, "The passwords don't match.")
    problem = auth.password_problem(body.password, email, first, last)
    if problem:
        raise HTTPException(422, problem)
    clinic_id = fund_id = None
    if body.role == "clinic":
        if not body.org_id or not db.execute("SELECT 1 FROM clinics WHERE id = ?", (body.org_id,)).fetchone():
            raise HTTPException(422, "Please choose your clinic.")
        clinic_id = body.org_id
    elif body.role == "fund":
        if not body.org_id or not db.execute("SELECT 1 FROM funds WHERE id = ? AND kind = 'independent' AND reference_only = 0", (body.org_id,)).fetchone():
            raise HTTPException(422, "Please choose your fund.")
        fund_id = body.org_id
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise HTTPException(409, "An account with this email already exists. Try logging in.")
    cur = db.execute(
        """INSERT INTO users (name, role, clinic_id, fund_id, first_name, last_name, email, password_hash, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (f"{first} {last}", body.role, clinic_id, fund_id, first, last, email,
         auth.hash_password(body.password), clock.now_iso()),
    )
    audit(db, f"user:{cur.lastrowid}", "account_requested", detail={"role": body.role, "clinic_id": clinic_id, "fund_id": fund_id})
    return {"ok": True, "message": "Account created. A Calma administrator will review it, and then you can log in."}


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


BAD_LOGIN = "That email and password don't match an account."


@app.post("/api/auth/login")
def login(body: LoginBody, db: sqlite3.Connection = Depends(get_db)) -> dict:
    email = auth.normalize_email(body.email)
    if auth.locked_out(email):
        raise HTTPException(429, "Too many tries. Please wait 15 minutes and try again.")
    row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not auth.check_login(body.password, row["password_hash"] if row else None):
        auth.record_failure(email)
        audit(db, "anonymous", "login_failed")  # no email or password in the log
        raise HTTPException(401, BAD_LOGIN)
    if row["status"] == "pending":
        raise HTTPException(403, "Your account is waiting for an administrator to approve it.")
    if row["status"] != "active":
        raise HTTPException(403, "This account is not active. Please contact your administrator.")
    auth.clear_failures(email)
    db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (clock.now_iso(), row["id"]))
    audit(db, f"user:{row['id']}", "login")
    return {"token": _new_session(row["id"]), "user": user_from_row(row).model_dump()}


@app.post("/api/auth/logout")
def logout(authorization: str = Header(default="")) -> dict:
    _sessions.pop(hashlib.sha256(authorization.removeprefix("Bearer ").strip().encode()).hexdigest(), None)
    return {"ok": True}


@app.get("/api/me")
def me(user: User = Depends(current_user)) -> User:
    return user


# ---------- patient portal (link token, no login) ----------

def case_by_token(db: sqlite3.Connection, token: str) -> sqlite3.Row:
    case = db.execute(
        """SELECT c.*, cl.name AS clinic_name, cl.phone AS clinic_phone, cl.state AS clinic_state
           FROM cases c JOIN clinics cl ON cl.id = c.clinic_id WHERE c.token = ?""",
        (token,),
    ).fetchone()
    if not case:
        raise HTTPException(404, "This link doesn't work.")
    if clock.now().isoformat() > case["token_expires_at"]:
        raise HTTPException(410, {"message": "expired", "clinic_name": case["clinic_name"],
                                  "clinic_phone": case["clinic_phone"]})
    return case


def question_plan(db: sqlite3.Connection, clinic_id: int) -> tuple[list[str], dict[str, list[str]]]:
    return Q.plan(db, clinic_id, approved_rules(db, clinic_fund_ids(db, clinic_id)))


@app.get("/api/p/{token}")
def patient_view(token: str, db: sqlite3.Connection = Depends(get_db)) -> dict:
    c = case_by_token(db, token)
    pledges = pledge_rows(db, "p.case_id = ?", (c["id"],))
    shown = []
    for p in pledges:
        amount = p["approved_amount"] if p["status"] in ("approved", "paid") else p["suggested_amount"]
        shown.append({"fund_name": p["fund_name"], "fund_kind": p["fund_kind"], "status": p["status"],
                      "amount": amount, "category": p["category"]})
    proc = [x for x in shown if x["category"] == "procedure"]
    prac = [x for x in shown if x["category"] == "practical"]
    approved = sum(x["amount"] for x in proc if x["status"] in ("approved", "paid"))
    pending = sum(x["amount"] for x in proc if x["status"] == "pending")
    out = {
        "clinic_name": c["clinic_name"], "clinic_phone": c["clinic_phone"], "clinic_state": c["clinic_state"],
        "appointment_date": c["appointment_date"], "language": c["language"],
        "submitted": c["submitted_at"] is not None, "procedure_cost": c["procedure_cost"],
        "pledges": shown, "approved_total": approved, "pending_total": pending,
        "you_may_owe": max(0, c["procedure_cost"] - approved),
        "practical_approved": sum(x["amount"] for x in prac if x["status"] in ("approved", "paid")),
        "practical_pending": sum(x["amount"] for x in prac if x["status"] == "pending"),
        "states": US_STATES,
        "contact_method": c["contact_method"],
        "decision_hours": decision_hours(),
        "decide_by": decide_by(c["submitted_at"]),
        "any_pending": any(x["status"] == "pending" for x in shown),
        "overdue": any(x["status"] == "pending" for x in shown) and is_overdue("pending", c["submitted_at"]),
    }
    if not c["submitted_at"]:
        out["questions"] = question_plan(db, c["clinic_id"])[0]
    return out


class LanguageBody(BaseModel):
    language: Literal["en", "es"]


@app.post("/api/p/{token}/language")
def patient_language(token: str, body: LanguageBody, db: sqlite3.Connection = Depends(get_db)) -> dict:
    c = case_by_token(db, token)
    db.execute("UPDATE cases SET language = ? WHERE id = ?", (body.language, c["id"]))
    return {"ok": True}


class ContactBody(BaseModel):
    first_name: str | None = Field(default=None, max_length=60)
    last_name: str | None = Field(default=None, max_length=60)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=120)
    notify_pref: Literal["text", "email"] | None = None


class ScreeningBody(BaseModel):
    state: str
    household_size: int = Field(ge=1, le=20)
    monthly_income: int = Field(ge=0, le=100_000)
    lmp_date: date | None = None                       # first day of last period (preferred)
    gestational_weeks: int | None = Field(default=None, ge=1, le=42)  # if the patient doesn't know the date
    needs_travel: bool
    age: int | None = Field(default=None, ge=10, le=60)
    travel_miles: int | None = Field(default=None, ge=0, le=3000)
    nights_away: int | None = Field(default=None, ge=0, le=7)
    meal_days: int | None = Field(default=None, ge=0, le=7)
    childcare_days: int | None = Field(default=None, ge=0, le=7)
    insurance_coverage: Literal["yes", "no", "unsure"] | None = None
    unhoused: bool | None = None
    judicial_bypass: bool | None = None
    contact: ContactBody | None = None


@app.post("/api/p/{token}/screening")
def patient_screening(token: str, body: ScreeningBody, db: sqlite3.Connection = Depends(get_db)) -> dict:
    c = case_by_token(db, token)
    if c["submitted_at"]:
        raise HTTPException(409, "already_submitted")
    if body.state not in US_STATES:
        raise HTTPException(422, "Unknown state.")
    asked, _ = question_plan(db, c["clinic_id"])
    a = set(asked)

    # Weeks pregnant on the day of the visit, from the first day of the last period.
    weeks = body.gestational_weeks
    if body.lmp_date:
        appt = date.fromisoformat(c["appointment_date"])
        if body.lmp_date > clock.today() or (appt - body.lmp_date).days > 45 * 7:
            raise HTTPException(422, "Please check the date of your last period.")
        weeks = (appt - body.lmp_date).days // 7

    # Keep only answers to questions this patient was actually asked (data minimization).
    keep = lambda q, v: v if q in a else None  # noqa: E731
    age = keep("age", body.age)
    travel = body.needs_travel
    miles = keep("travel_miles", body.travel_miles) if travel else None
    nights = keep("nights_away", body.nights_away) if travel else None
    meals = keep("meal_days", body.meal_days) if travel else None
    care = keep("childcare_days", body.childcare_days) if travel else None
    bypass = keep("judicial_bypass", body.judicial_bypass) if (age is None or age < 18) else None
    insurance = keep("insurance", body.insurance_coverage)
    unhoused = keep("unhoused", body.unhoused)

    db.execute(
        """UPDATE cases SET state=?, household_size=?, monthly_income=?, gestational_weeks=?, needs_travel=?,
           age=?, care_state=?, travel_miles=?, nights_away=?, meal_days=?, childcare_days=?,
           insurance_coverage=?, unhoused=?, judicial_bypass=?, questions_asked=?,
           status='screened', submitted_at=? WHERE id=?""",
        (body.state, body.household_size, body.monthly_income, weeks, int(travel), age, c["clinic_state"],
         miles, nights, meals, care, insurance, None if unhoused is None else int(unhoused),
         None if bypass is None else int(bypass), json.dumps(asked), clock.now_iso(), c["id"]),
    )
    if "contact" in a and body.contact and any(body.contact.model_dump().values()):
        k = body.contact
        db.execute(
            """INSERT OR REPLACE INTO case_contacts (case_id, first_name, last_name, phone, email, notify_pref)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (c["id"], k.first_name, k.last_name, k.phone, k.email, k.notify_pref),
        )
    audit(db, "patient", "screening_submitted", c["id"])

    case = db.execute("SELECT * FROM cases WHERE id = ?", (c["id"],)).fetchone()
    result = match(screening_of(case), c["procedure_cost"], approved_rules(db, clinic_fund_ids(db, c["clinic_id"])))
    for m in result.matches:
        db.execute(
            """INSERT INTO pledges (case_id, fund_id, criteria_id, suggested_amount, reasons, category)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (c["id"], m.fund_id, m.criteria_id, m.suggested_amount, json.dumps(m.reasons), m.category),
        )
        # "Ping": the fund (or clinic) now sees this in its queue of eligible patients.
        audit(db, "system", "fund_notified", c["id"], {"fund_id": m.fund_id, "amount": m.suggested_amount})
    return patient_view(token, db)


# ---------- clinic portal ----------

def clinic_fund_status(db: sqlite3.Connection, clinic_id: int) -> list[dict]:
    rows = db.execute("SELECT * FROM funds WHERE owner_clinic_id = ?", (clinic_id,)).fetchall()
    out = []
    for f in rows:
        used = fund_month_used(db, f["id"])
        out.append({"id": f["id"], "name": f["name"], "monthly_limit": f["monthly_limit"],
                    "used_this_month": used, "left_this_month": (f["monthly_limit"] or 0) - used})
    return out


@app.get("/api/clinic/summary")
def clinic_summary(user: User = Depends(require("clinic")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    clinic = db.execute("SELECT * FROM clinics WHERE id = ?", (user.clinic_id,)).fetchone()
    partners = db.execute(
        """SELECT f.id, f.name, f.description FROM funds f
           JOIN clinic_fund_partnerships p ON p.fund_id = f.id
           WHERE p.clinic_id = ? AND p.status = 'accepted' AND f.kind = 'independent' ORDER BY f.name""",
        (user.clinic_id,),
    ).fetchall()
    return {"clinic": dict(clinic), "own_funds": clinic_fund_status(db, user.clinic_id),
            "partner_funds": [dict(r) for r in partners]}


class NewCase(BaseModel):
    appointment_date: date
    procedure_cost: int = Field(ge=1, le=50_000)
    contact_method: Literal["text", "email"]
    language: Literal["en", "es"] = "en"
    clinic_ref: str | None = Field(default=None, max_length=60)  # clinic's own appointment/chart number


def _clean_ref(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


@app.post("/api/clinic/cases")
def create_case(body: NewCase, user: User = Depends(require("clinic")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    if body.appointment_date < clock.today():
        raise HTTPException(422, "Appointment date is in the past.")
    token = secrets.token_urlsafe(24)
    # The link works until the end of the day after the appointment.
    expires = datetime.combine(body.appointment_date + timedelta(days=2), datetime.min.time(),
                               tzinfo=clock.now().tzinfo)
    cur = db.execute(
        """INSERT INTO cases (clinic_id, token, token_expires_at, appointment_date, procedure_cost,
           contact_method, language, created_at, clinic_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user.clinic_id, token, expires.isoformat(timespec="seconds"), body.appointment_date.isoformat(),
         body.procedure_cost, body.contact_method, body.language, clock.now_iso(), _clean_ref(body.clinic_ref)),
    )
    audit(db, f"user:{user.id}", "case_created", cur.lastrowid)
    return {"case_id": cur.lastrowid, "case_ref": case_ref(cur.lastrowid), "patient_path": f"/p/{token}"}


def own_case(db: sqlite3.Connection, user: User, case_id: int) -> sqlite3.Row:
    c = db.execute("SELECT * FROM cases WHERE id = ? AND clinic_id = ?", (case_id, user.clinic_id)).fetchone()
    if not c:
        raise HTTPException(404, "Case not found.")
    return c


# What the clinic needs to do next, in plain words (shown instead of the internal status).
CLINIC_STATUS_ORDER = ["needs_approval", "waiting_funds", "approved", "waiting_patient", "visit_completed", "closed"]


def clinic_status(c: sqlite3.Row, pledges: list[dict]) -> str:
    if c["status"] == "link_sent":
        return "waiting_patient"
    if c["status"] == "appointment_done":
        return "visit_completed"
    if c["status"] == "closed":
        return "closed"
    if any(p["status"] == "pending" and p["fund_kind"] == "clinic" for p in pledges):
        return "needs_approval"
    if any(p["status"] == "pending" for p in pledges):
        return "waiting_funds"
    return "approved"


def case_out(db: sqlite3.Connection, c: sqlite3.Row, detail: bool = False) -> dict:
    pledges = [pledge_out(p) for p in pledge_rows(db, "p.case_id = ?", (c["id"],))]
    approved = sum(p["approved_amount"] or 0 for p in pledges
                   if p["status"] in ("approved", "paid") and p["category"] == "procedure")
    practical = sum(p["approved_amount"] or 0 for p in pledges
                    if p["status"] in ("approved", "paid") and p["category"] == "practical")
    out = {
        "id": c["id"], "case_ref": case_ref(c["id"]), "appointment_date": c["appointment_date"],
        "procedure_cost": c["procedure_cost"], "status": c["status"], "language": c["language"],
        "contact_method": c["contact_method"], "submitted_at": c["submitted_at"],
        "patient_path": f"/p/{c['token']}" if c["status"] == "link_sent" else None,
        "pledges": pledges, "approved_total": approved, "practical_approved": practical,
        "patient_owes": max(0, c["procedure_cost"] - approved),
        "clinic_ref": c["clinic_ref"],
        "clinic_status": clinic_status(c, pledges),
        "overdue": any(p["overdue"] and p["fund_kind"] == "clinic" for p in pledges),
    }
    if detail and c["submitted_at"]:
        s = screening_of(c)
        result = match(s, c["procedure_cost"], approved_rules(db, clinic_fund_ids(db, c["clinic_id"])))
        out["screening"] = {**answers_of(c), "income_fpl_pct": income_fpl_pct(s.monthly_income, s.household_size)}
        out["questions_asked"] = json.loads(c["questions_asked"] or "[]")
        contact = db.execute("SELECT * FROM case_contacts WHERE case_id = ?", (c["id"],)).fetchone()
        out["contact"] = {k: contact[k] for k in ("first_name", "last_name", "phone", "email", "notify_pref")} if contact else None
        out["not_matched"] = [{"fund_name": k.fund_name, "reasons": k.reasons} for k in result.skipped]
    return out


@app.get("/api/clinic/cases")
def clinic_cases(user: User = Depends(require("clinic")), db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = db.execute("SELECT * FROM cases WHERE clinic_id = ?", (user.clinic_id,)).fetchall()
    cases = [case_out(db, c) for c in rows]

    # Overdue approvals first, then what needs the clinic, then upcoming work by soonest visit;
    # finished cases last, most recent first.
    def key(x):
        rank = CLINIC_STATUS_ORDER.index(x["clinic_status"])
        done = x["clinic_status"] in ("visit_completed", "closed")
        d = date.fromisoformat(x["appointment_date"]).toordinal()
        return (0 if x["overdue"] else 1, rank, -d if done else d, x["id"])
    return sorted(cases, key=key)


class ClinicRefBody(BaseModel):
    clinic_ref: str | None = Field(default=None, max_length=60)


@app.put("/api/clinic/cases/{case_id}/ref")
def set_clinic_ref(case_id: int, body: ClinicRefBody, user: User = Depends(require("clinic")),
                   db: sqlite3.Connection = Depends(get_db)) -> dict:
    own_case(db, user, case_id)
    db.execute("UPDATE cases SET clinic_ref = ? WHERE id = ?", (_clean_ref(body.clinic_ref), case_id))
    audit(db, f"user:{user.id}", "clinic_ref_set", case_id)  # the reference itself isn't logged
    return {"ok": True, "clinic_ref": _clean_ref(body.clinic_ref)}


@app.get("/api/clinic/cases/{case_id}")
def clinic_case(case_id: int, user: User = Depends(require("clinic")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    c = own_case(db, user, case_id)
    audit(db, f"user:{user.id}", "case_viewed", case_id)
    return case_out(db, c, detail=True)


@app.post("/api/clinic/pledges/{pledge_id}/decide")
def clinic_decide(pledge_id: int, body: Decision, user: User = Depends(require("clinic")),
                  db: sqlite3.Connection = Depends(get_db)) -> dict:
    rows = pledge_rows(db, "p.id = ? AND c.clinic_id = ? AND f.owner_clinic_id = ?",
                       (pledge_id, user.clinic_id, user.clinic_id))
    if not rows:
        raise HTTPException(404, "Clinic staff can only decide pledges from the clinic's own fund.")
    return decide_pledge(db, user, rows[0], body)


@app.post("/api/clinic/cases/{case_id}/appointment-done")
def appointment_done(case_id: int, user: User = Depends(require("clinic")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    c = own_case(db, user, case_id)
    if c["status"] != "screened":
        raise HTTPException(409, "Only screened cases can be marked done.")
    db.execute("UPDATE cases SET status = 'appointment_done' WHERE id = ?", (case_id,))
    # The clinic's own fund pays at the visit: approved clinic-fund pledges are completed.
    db.execute(
        """UPDATE pledges SET status = 'paid', paid_at = ? WHERE case_id = ? AND status = 'approved'
           AND fund_id IN (SELECT id FROM funds WHERE kind = 'clinic')""",
        (clock.now_iso(), case_id),
    )
    audit(db, f"user:{user.id}", "appointment_done", case_id)
    maybe_close_case(db, case_id)
    return {"ok": True}


@app.get("/api/clinic/reimbursements")
def clinic_reimbursements(user: User = Depends(require("clinic")), db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = pledge_rows(
        db, "c.clinic_id = ? AND f.kind = 'independent' AND p.category = 'procedure' AND p.status IN ('approved', 'paid')",
        (user.clinic_id,),
    )
    return [{**pledge_out(p), "appointment_date": p["appointment_date"], "case_status": p["case_status"]}
            for p in rows]


# ---------- fund portal ----------

def fund_case_view(p: sqlite3.Row, case: sqlite3.Row, rule: FundRule | None) -> dict:
    """Only what a fund needs to decide: no raw income, no contact details, and only
    answers to questions this fund needs or asked for."""
    asked = set(json.loads(case["questions_asked"] or "[]"))
    mine = (Q.asked_by_fund(rule) if rule else set()) & asked
    if rule and (rule.gest_min_weeks is not None or rule.gest_max_weeks is not None):
        mine.add("pregnancy")
    if rule and (rule.requires_travel or rule.support_type == "practical"):
        mine.add("travel")
    answers = {k: v for k, v in answers_of(case, mine).items() if v is not None}
    return {
        **pledge_out(p), "clinic_name": p["clinic_name"], "appointment_date": p["appointment_date"],
        "case_status": p["case_status"], "state": p["state"], "household_size": p["household_size"],
        "income_fpl_pct": income_fpl_pct(p["monthly_income"], p["household_size"]),
        "answers": answers,
    }


# What a fund can see: pledges at clinics it partners with, plus anything it already decided
# (so approved pledges can still be marked paid after a partnership ends).
FUND_SCOPE = """p.fund_id = ? AND (p.status != 'pending' OR c.clinic_id IN
    (SELECT clinic_id FROM clinic_fund_partnerships WHERE fund_id = ? AND status = 'accepted'))"""
# What a fund can decide: only pending pledges at accepted partner clinics.
FUND_DECIDE_SCOPE = """p.fund_id = ? AND c.clinic_id IN
    (SELECT clinic_id FROM clinic_fund_partnerships WHERE fund_id = ? AND status = 'accepted')"""


@app.get("/api/fund/summary")
def fund_summary(user: User = Depends(require("fund")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    f = db.execute("SELECT * FROM funds WHERE id = ?", (user.fund_id,)).fetchone()
    clinics = db.execute(
        """SELECT cl.id, cl.name, cl.city, cl.state, cl.phone FROM clinics cl
           JOIN clinic_fund_partnerships p ON p.clinic_id = cl.id
           WHERE p.fund_id = ? AND p.status = 'accepted' ORDER BY cl.name""",
        (user.fund_id,),
    ).fetchall()
    crit = approved_rules(db, [user.fund_id])
    used = fund_month_used(db, user.fund_id)
    pend = pledge_rows(db, f"{FUND_DECIDE_SCOPE} AND p.status = 'pending'", (user.fund_id, user.fund_id))
    return {
        "overdue": sum(1 for p in pend if is_overdue(p["status"], p["submitted_at"])), "decision_hours": decision_hours(),
        "fund": dict(f), "partner_clinics": [dict(c) for c in clinics],
        "monthly_budget": f["monthly_limit"], "approved_this_month": used,
        "criteria": crit[0].__dict__ if crit else None,
    }


@app.get("/api/fund/pledges")
def fund_pledges(user: User = Depends(require("fund")), db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = pledge_rows(db, FUND_SCOPE, (user.fund_id, user.fund_id))
    audit(db, f"user:{user.id}", "fund_queue_viewed")
    rule = next(iter(approved_rules(db, [user.fund_id])), None)
    cases = {r["id"]: r for r in db.execute(
        f"SELECT * FROM cases WHERE id IN ({','.join('?' * len(rows))})", [p["case_id"] for p in rows]
    ).fetchall()} if rows else {}
    return [fund_case_view(p, cases[p["case_id"]], rule) for p in rows]


@app.post("/api/fund/pledges/{pledge_id}/decide")
def fund_decide(pledge_id: int, body: Decision, user: User = Depends(require("fund")),
                db: sqlite3.Connection = Depends(get_db)) -> dict:
    rows = pledge_rows(db, f"p.id = ? AND {FUND_DECIDE_SCOPE}", (pledge_id, user.fund_id, user.fund_id))
    if not rows:
        raise HTTPException(404, "Pledge not found.")
    return decide_pledge(db, user, rows[0], body)


@app.post("/api/fund/pledges/{pledge_id}/mark-paid")
def fund_mark_paid(pledge_id: int, user: User = Depends(require("fund")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    rows = pledge_rows(db, f"p.id = ? AND {FUND_SCOPE}", (pledge_id, user.fund_id, user.fund_id))
    if not rows:
        raise HTTPException(404, "Pledge not found.")
    p = rows[0]
    if p["status"] != "approved":
        raise HTTPException(409, "Only approved pledges can be marked paid.")
    # Procedure pledges are paid to the clinic after the visit; practical help (travel, lodging) comes before it.
    if p["category"] == "procedure" and p["case_status"] not in ("appointment_done", "closed"):
        raise HTTPException(409, "The clinic hasn't marked this appointment done yet.")
    db.execute("UPDATE pledges SET status = 'paid', paid_at = ? WHERE id = ?", (clock.now_iso(), pledge_id))
    audit(db, f"user:{user.id}", "pledge_paid", p["case_id"], {"pledge_id": pledge_id})
    maybe_close_case(db, p["case_id"])
    return {"ok": True}


# ---------- admin ----------

@app.get("/api/admin/funds")
def admin_funds(user: User = Depends(require("admin")), db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        """SELECT f.id, f.name, f.kind, f.monthly_limit, f.description, f.reference_only, c.*
           FROM funds f LEFT JOIN fund_criteria c ON c.fund_id = f.id AND c.status = 'approved'
           ORDER BY f.reference_only, f.kind, f.name"""
    ).fetchall()
    return [{"id": r[0], "name": r["name"], "kind": r["kind"], "monthly_limit": r["monthly_limit"],
             "description": r["description"], "reference_only": bool(r["reference_only"]), "version": r["version"],
             "last_verified_at": r["last_verified_at"], "verified_by": r["verified_by"], **row_to_rules(r)} for r in rows]


@app.get("/api/admin/audit")
def admin_audit(user: User = Depends(require("admin")), db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


# ---------- fund rules: AI-proposed updates, approved by a person ----------

from . import llm, rules_extractor  # noqa: E402
from .proposals import create_proposal, current_rule_dict, insert_rule, next_version, update_rule  # noqa: E402

# Tests swap this for a fake model so no real AI call is made.
model_for_extraction = llm.get_model


class ExtractBody(BaseModel):
    text: str = Field(min_length=40, max_length=rules_extractor.MAX_SOURCE_CHARS)
    source_url: str | None = Field(default=None, max_length=500)


@app.post("/api/admin/funds/{fund_id}/extract")
async def admin_extract(fund_id: int, body: ExtractBody, user: User = Depends(require("admin")),
                        db: sqlite3.Connection = Depends(get_db)) -> dict:
    fund = db.execute("SELECT * FROM funds WHERE id = ?", (fund_id,)).fetchone()
    if not fund:
        raise HTTPException(404, "Fund not found.")
    try:
        criteria_id = await create_proposal(db, fund_id, body.text, body.source_url, f"user:{user.id}",
                                            model_for_extraction(), user_id=user.id)
    except Exception as e:  # model/network errors: tell the admin, never apply anything
        audit(db, f"user:{user.id}", "rules_extract_failed", detail={"fund_id": fund_id, "error": type(e).__name__})
        raise HTTPException(502, f"The AI helper couldn't read this text: {llm.explain_ai_error(e)} Nothing was changed.")
    return proposal_out(db, criteria_id)


def proposal_out(db: sqlite3.Connection, criteria_id: int) -> dict:
    r = db.execute(
        """SELECT c.*, f.name AS fund_name FROM fund_criteria c JOIN funds f ON f.id = c.fund_id
           WHERE c.id = ? AND c.status = 'proposed'""",
        (criteria_id,),
    ).fetchone()
    if not r:
        raise HTTPException(404, "Proposal not found.")
    proposed = row_to_rules(r)
    current = current_rule_dict(db, r["fund_id"])
    return {
        "id": r["id"], "fund_id": r["fund_id"], "fund_name": r["fund_name"], "version": r["version"],
        "source_url": r["source_url"], "proposed_by": r["proposed_by"],
        "current": {k: current.get(k) for k in rules_extractor.RULE_FIELDS},
        "proposed": proposed, "evidence": json.loads(r["evidence"] or "{}"),
    }


@app.get("/api/admin/proposals")
def admin_proposals(user: User = Depends(require("admin")), db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    ids = db.execute("SELECT id FROM fund_criteria WHERE status = 'proposed' ORDER BY id").fetchall()
    return [proposal_out(db, i[0]) for i in ids]


class RuleValues(BaseModel):
    states: list[str] = Field(min_length=1)
    income_max_fpl_pct: int | None = Field(default=None, ge=1, le=1000)
    gest_min_weeks: int | None = Field(default=None, ge=0, le=42)
    gest_max_weeks: int | None = Field(default=None, ge=0, le=42)
    requires_travel: bool = False
    max_age: int | None = Field(default=None, ge=10, le=100)
    pledge_kind: Literal["fixed", "percent"] = "fixed"
    pledge_value: int = Field(default=0, ge=0)
    pledge_cap: int | None = Field(default=None, ge=1)
    state_basis: Literal["residence", "care", "either"] = "residence"
    support_type: Literal["procedure", "practical"] = "procedure"
    rate_per_mile_cents: int | None = Field(default=None, ge=0, le=500)
    rate_per_night: int | None = Field(default=None, ge=0, le=1000)
    rate_per_meal_day: int | None = Field(default=None, ge=0, le=500)
    rate_per_childcare_day: int | None = Field(default=None, ge=0, le=1000)
    no_insurance_only: bool = False
    extra_questions: list[str] = Field(default_factory=list)


def clean_rules(body: RuleValues) -> dict:
    """Validate rule values typed by a person and return them normalized."""
    states = ["*"] if "*" in body.states else sorted({s.strip().upper() for s in body.states if s.strip()})
    if not states:
        raise HTTPException(422, "Pick at least one state, or * for any state.")
    if any(s != "*" and s not in US_STATES for s in states):
        bad = [s for s in states if s != "*" and s not in US_STATES]
        raise HTTPException(422, f"Unknown state code: {', '.join(bad)}. Use two-letter codes like TX.")
    if body.support_type == "procedure" and body.pledge_value < 1:
        raise HTTPException(422, "Pledge amount must be at least $1 (or 1%).")
    if body.support_type == "practical" and not (body.pledge_value or body.rate_per_mile_cents or body.rate_per_night
                                                 or body.rate_per_meal_day or body.rate_per_childcare_day):
        raise HTTPException(422, "Practical support needs a flat amount or at least one rate (miles, nights, meals, childcare).")
    bad_q = [q for q in body.extra_questions if q not in Q.FUND_ASKABLE]
    if bad_q:
        raise HTTPException(422, f"Unknown question: {', '.join(bad_q)}.")
    if body.pledge_kind == "percent" and body.pledge_value > 100:
        raise HTTPException(422, "Percent pledge can't be over 100.")
    if body.gest_min_weeks is not None and body.gest_max_weeks is not None and body.gest_min_weeks > body.gest_max_weeks:
        raise HTTPException(422, "Minimum weeks is more than maximum weeks.")
    d = body.model_dump()
    d["states"] = states
    d["extra_questions"] = [q for q in Q.FUND_ASKABLE if q in body.extra_questions]
    if body.support_type == "practical":
        d["pledge_kind"] = "fixed"          # practical: flat amount + rates, cap applies
    else:
        for k in ("rate_per_mile_cents", "rate_per_night", "rate_per_meal_day", "rate_per_childcare_day"):
            d[k] = None
        if body.pledge_kind == "fixed":
            d["pledge_cap"] = None
    return d


@app.post("/api/admin/proposals/{criteria_id}/approve")
def admin_approve(criteria_id: int, body: RuleValues, user: User = Depends(require("admin")),
                  db: sqlite3.Connection = Depends(get_db)) -> dict:
    """The person's (possibly edited) values become the new live rules."""
    p = proposal_out(db, criteria_id)
    values = clean_rules(body)
    db.execute("UPDATE fund_criteria SET status = 'retired' WHERE fund_id = ? AND status = 'approved'", (p["fund_id"],))
    update_rule(db, criteria_id, values, status="approved", last_verified_at=clock.now_iso(), verified_by=user.name)
    edited = [k for k, v in values.items() if p["proposed"].get(k) != v]
    audit(db, f"user:{user.id}", "rules_approved",
          detail={"fund_id": p["fund_id"], "version": p["version"], "edited_fields": edited})
    return {"ok": True, "version": p["version"]}


@app.post("/api/admin/proposals/{criteria_id}/reject")
def admin_reject(criteria_id: int, user: User = Depends(require("admin")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    p = proposal_out(db, criteria_id)
    db.execute("DELETE FROM fund_criteria WHERE id = ?", (criteria_id,))
    audit(db, f"user:{user.id}", "rules_rejected", detail={"fund_id": p["fund_id"], "version": p["version"]})
    return {"ok": True}


# ---------- scheduled website checks ----------

from . import website_check  # noqa: E402


def _fund_check_rows(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        """SELECT f.id, f.name, f.kind, f.policy_url, f.reference_only,
                  (SELECT checked_at FROM page_checks WHERE fund_id = f.id ORDER BY id DESC LIMIT 1) AS last_checked_at,
                  (SELECT status FROM page_checks WHERE fund_id = f.id ORDER BY id DESC LIMIT 1) AS last_status
           FROM funds f ORDER BY f.kind, f.name"""
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d["policy_url"] and d["last_checked_at"]:
            due = datetime.fromisoformat(d["last_checked_at"]) + timedelta(days=website_check.interval_days())
            d["next_check_at"] = due.isoformat(timespec="seconds")
        else:
            d["next_check_at"] = "soon" if d["policy_url"] else None
        out.append(d)
    return out


@app.get("/api/admin/website-checks")
def admin_website_checks(user: User = Depends(require("admin")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    checks = db.execute(
        """SELECT pc.id, pc.fund_id, f.name AS fund_name, pc.url, pc.checked_at, pc.trigger, pc.status,
                  pc.note, pc.criteria_id
           FROM page_checks pc JOIN funds f ON f.id = pc.fund_id ORDER BY pc.id DESC LIMIT 50"""
    ).fetchall()
    return {"interval_days": website_check.interval_days(), "funds": _fund_check_rows(db),
            "checks": [dict(c) for c in checks]}


class PolicyUrlBody(BaseModel):
    policy_url: str | None = Field(default=None, max_length=500)


@app.put("/api/admin/funds/{fund_id}/policy-url")
def admin_set_policy_url(fund_id: int, body: PolicyUrlBody, user: User = Depends(require("admin")),
                         db: sqlite3.Connection = Depends(get_db)) -> dict:
    url = (body.policy_url or "").strip() or None
    if url:
        try:
            website_check.validate_url(url)
        except website_check.CheckError as e:
            raise HTTPException(422, str(e))
    if not db.execute("UPDATE funds SET policy_url = ? WHERE id = ?", (url, fund_id)).rowcount:
        raise HTTPException(404, "Fund not found.")
    audit(db, f"user:{user.id}", "policy_url_set", detail={"fund_id": fund_id, "url": url})
    return {"ok": True}


@app.post("/api/admin/funds/{fund_id}/check-now")
async def admin_check_now(fund_id: int, user: User = Depends(require("admin")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        r = await website_check.check_fund(db, fund_id, model_for_extraction(), trigger=f"user:{user.id}")
    except website_check.CheckError as e:
        raise HTTPException(422, str(e))
    return r.__dict__


@app.post("/api/admin/website-checks/run-due")
async def admin_run_due(user: User = Depends(require("admin")), db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    results = await website_check.run(db, model_for_extraction(), trigger=f"user:{user.id}")
    return [r.__dict__ for r in results]


# ---------- fund portal: funds keep their own rules up to date ----------

CONFIRM_EVERY_DAYS = 60


def _rules_view(db: sqlite3.Connection, fund_id: int) -> dict:
    cur = current_rule_dict(db, fund_id)
    verified = cur.get("last_verified_at")
    days = (clock.now() - datetime.fromisoformat(verified)).days if verified else None
    history = db.execute(
        """SELECT version, status, verified_by, last_verified_at, source_url FROM fund_criteria
           WHERE fund_id = ? AND status IN ('approved', 'retired') ORDER BY version DESC LIMIT 10""",
        (fund_id,),
    ).fetchall()
    pending = db.execute("SELECT 1 FROM fund_criteria WHERE fund_id = ? AND status = 'proposed'", (fund_id,)).fetchone()
    return {
        "rules": {k: cur.get(k) for k in rules_extractor.RULE_FIELDS},
        "version": cur.get("version"), "verified_by": cur.get("verified_by"), "last_verified_at": verified,
        "days_since_confirmed": days, "confirm_every_days": CONFIRM_EVERY_DAYS,
        "needs_confirm": days is None or days >= CONFIRM_EVERY_DAYS,
        "pending_ai_review": bool(pending),
        "history": [dict(h) for h in history],
    }


@app.get("/api/fund/rules")
def fund_rules(user: User = Depends(require("fund")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    return _rules_view(db, user.fund_id)


def _save_rules(db: sqlite3.Connection, user: User, fund_id: int, body: RuleValues, source: str) -> dict:
    """An owner's edit is authoritative: it goes live right away as a new version."""
    new = clean_rules(body)
    cur = current_rule_dict(db, fund_id)
    changed = [k for k in rules_extractor.RULE_FIELDS if new[k] != cur.get(k)]
    if not changed:
        raise HTTPException(422, "Nothing changed. If your rules are still right, use \"Yes, still accurate\".")
    # The owner's word replaces any AI suggestion waiting for an admin.
    superseded = db.execute("DELETE FROM fund_criteria WHERE fund_id = ? AND status = 'proposed'", (fund_id,)).rowcount
    version = next_version(db, fund_id)
    db.execute("UPDATE fund_criteria SET status = 'retired' WHERE fund_id = ? AND status = 'approved'", (fund_id,))
    insert_rule(db, fund_id, version, "approved", new, source_url=source, last_verified_at=clock.now_iso(),
                verified_by=user.name)
    audit(db, f"user:{user.id}", f"rules_updated_by_{user.role}",
          detail={"fund_id": fund_id, "version": version, "changed_fields": changed,
                  "superseded_ai_suggestion": bool(superseded)})
    return _rules_view(db, fund_id)


def _confirm_rules(db: sqlite3.Connection, user: User, fund_id: int) -> dict:
    """One click: 'these rules are still right'. Resets the reminder; no new version."""
    n = db.execute(
        "UPDATE fund_criteria SET last_verified_at = ?, verified_by = ? WHERE fund_id = ? AND status = 'approved'",
        (clock.now_iso(), user.name, fund_id),
    ).rowcount
    if not n:
        raise HTTPException(404, "No rules on file yet.")
    audit(db, f"user:{user.id}", f"rules_confirmed_by_{user.role}", detail={"fund_id": fund_id})
    return _rules_view(db, fund_id)


@app.put("/api/fund/rules")
def fund_update_rules(body: RuleValues, user: User = Depends(require("fund")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    return _save_rules(db, user, user.fund_id, body, "fund portal")


@app.post("/api/fund/rules/confirm")
def fund_confirm_rules(user: User = Depends(require("fund")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    return _confirm_rules(db, user, user.fund_id)


# ---------- clinic portal: clinics keep their own fund's rules up to date ----------

def own_clinic_fund(db: sqlite3.Connection, user: User, fund_id: int) -> sqlite3.Row:
    f = db.execute("SELECT * FROM funds WHERE id = ? AND owner_clinic_id = ?", (fund_id, user.clinic_id)).fetchone()
    if not f:
        raise HTTPException(404, "Clinic staff can only edit the clinic's own fund.")
    return f


def _clinic_rules_view(db: sqlite3.Connection, fund: sqlite3.Row) -> dict:
    used = fund_month_used(db, fund["id"])
    return {**_rules_view(db, fund["id"]), "fund_id": fund["id"], "fund_name": fund["name"],
            "monthly_limit": fund["monthly_limit"], "used_this_month": used}


@app.get("/api/clinic/funds/{fund_id}/rules")
def clinic_fund_rules(fund_id: int, user: User = Depends(require("clinic")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    return _clinic_rules_view(db, own_clinic_fund(db, user, fund_id))


@app.put("/api/clinic/funds/{fund_id}/rules")
def clinic_update_fund_rules(fund_id: int, body: RuleValues, user: User = Depends(require("clinic")),
                             db: sqlite3.Connection = Depends(get_db)) -> dict:
    f = own_clinic_fund(db, user, fund_id)
    _save_rules(db, user, fund_id, body, "clinic portal")
    return _clinic_rules_view(db, f)


@app.post("/api/clinic/funds/{fund_id}/rules/confirm")
def clinic_confirm_fund_rules(fund_id: int, user: User = Depends(require("clinic")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    f = own_clinic_fund(db, user, fund_id)
    _confirm_rules(db, user, fund_id)
    return _clinic_rules_view(db, f)


class MonthlyLimitBody(BaseModel):
    monthly_limit: int = Field(ge=0, le=10_000_000)


@app.put("/api/clinic/funds/{fund_id}/monthly-limit")
def clinic_set_monthly_limit(fund_id: int, body: MonthlyLimitBody, user: User = Depends(require("clinic")),
                             db: sqlite3.Connection = Depends(get_db)) -> dict:
    """The clinic's block grant: how much its own fund can pledge each month."""
    f = own_clinic_fund(db, user, fund_id)
    db.execute("UPDATE funds SET monthly_limit = ? WHERE id = ?", (body.monthly_limit, fund_id))
    audit(db, f"user:{user.id}", "monthly_limit_set",
          detail={"fund_id": fund_id, "from": f["monthly_limit"], "to": body.monthly_limit})
    return _clinic_rules_view(db, db.execute("SELECT * FROM funds WHERE id = ?", (fund_id,)).fetchone())


# ---------- intake questions: which questions patients see ----------

@app.get("/api/questions/catalog")
def question_catalog(user: User = Depends(current_user)) -> list[dict]:
    return [{"id": q, "group": g, "label": label, "fund_askable": q in Q.FUND_ASKABLE}
            for q, (g, label) in Q.CATALOG.items()]


@app.get("/api/clinic/questions")
def clinic_questions(user: User = Depends(require("clinic")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    asked, why = question_plan(db, user.clinic_id)
    return {"asked": asked, "why": why, "clinic_extras": Q.clinic_extras(db, user.clinic_id),
            "catalog": question_catalog(user)}


class ClinicQuestionsBody(BaseModel):
    extra_questions: list[str]


@app.put("/api/clinic/questions")
def clinic_set_questions(body: ClinicQuestionsBody, user: User = Depends(require("clinic")),
                         db: sqlite3.Connection = Depends(get_db)) -> dict:
    bad = [q for q in body.extra_questions if q not in Q.OPTIONAL]
    if bad:
        raise HTTPException(422, f"Unknown question: {', '.join(bad)}.")
    extras = [q for q in Q.OPTIONAL if q in body.extra_questions]
    db.execute("UPDATE clinics SET extra_questions = ? WHERE id = ?", (json.dumps(extras), user.clinic_id))
    audit(db, f"user:{user.id}", "clinic_questions_set", detail={"extra_questions": extras})
    return clinic_questions(user, db)


# ---------- partnerships: funds choose clinics, clinics accept ----------

def _partner_rows(db: sqlite3.Connection, where: str, params: tuple) -> list[dict]:
    rows = db.execute(
        f"""SELECT p.clinic_id, p.fund_id, p.status, p.requested_by, p.created_at, p.accepted_at,
                   cl.name AS clinic_name, cl.city, cl.state, f.name AS fund_name, f.description AS fund_description
            FROM clinic_fund_partnerships p JOIN clinics cl ON cl.id = p.clinic_id JOIN funds f ON f.id = p.fund_id
            WHERE f.kind = 'independent' AND {where} ORDER BY cl.name, f.name""",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/fund/partnerships")
def fund_partnerships(user: User = Depends(require("fund")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    mine = _partner_rows(db, "p.fund_id = ?", (user.fund_id,))
    linked = {r["clinic_id"] for r in mine}
    others = db.execute("SELECT id, name, city, state FROM clinics ORDER BY name").fetchall()
    return {"partnerships": mine,
            "available_clinics": [dict(c) for c in others if c["id"] not in linked]}


@app.post("/api/fund/partnerships/{clinic_id}")
def fund_request_partnership(clinic_id: int, user: User = Depends(require("fund")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    if not db.execute("SELECT 1 FROM clinics WHERE id = ?", (clinic_id,)).fetchone():
        raise HTTPException(404, "Clinic not found.")
    row = db.execute("SELECT status FROM clinic_fund_partnerships WHERE clinic_id = ? AND fund_id = ?",
                     (clinic_id, user.fund_id)).fetchone()
    if row and row["status"] in ("pending", "accepted"):
        raise HTTPException(409, "You already have a partnership or request with this clinic.")
    db.execute(
        """INSERT OR REPLACE INTO clinic_fund_partnerships (clinic_id, fund_id, status, requested_by, created_at, accepted_at)
           VALUES (?, ?, 'pending', 'fund', ?, NULL)""",
        (clinic_id, user.fund_id, clock.now_iso()),
    )
    audit(db, f"user:{user.id}", "partnership_requested", detail={"clinic_id": clinic_id, "fund_id": user.fund_id})
    return fund_partnerships(user, db)


def _end_partnership(db: sqlite3.Connection, user: User, clinic_id: int, fund_id: int) -> None:
    """Remove the link. Pledges still waiting for this fund at this clinic are declined so cases don't stall;
    already-approved pledges stay (the fund keeps its word and can still mark them paid)."""
    n = db.execute("DELETE FROM clinic_fund_partnerships WHERE clinic_id = ? AND fund_id = ?", (clinic_id, fund_id)).rowcount
    if not n:
        raise HTTPException(404, "No partnership with that clinic.")
    pend = db.execute(
        """SELECT p.id, p.case_id FROM pledges p JOIN cases c ON c.id = p.case_id
           WHERE p.fund_id = ? AND c.clinic_id = ? AND p.status = 'pending'""",
        (fund_id, clinic_id),
    ).fetchall()
    for p in pend:
        db.execute("UPDATE pledges SET status = 'declined', decided_by = ?, decided_at = ? WHERE id = ?",
                   (user.id, clock.now_iso(), p["id"]))
        audit(db, f"user:{user.id}", "pledge_declined_partnership_ended", p["case_id"], {"pledge_id": p["id"]})
    audit(db, f"user:{user.id}", "partnership_removed",
          detail={"clinic_id": clinic_id, "fund_id": fund_id, "pending_pledges_declined": len(pend)})


@app.delete("/api/fund/partnerships/{clinic_id}")
def fund_remove_partnership(clinic_id: int, user: User = Depends(require("fund")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    _end_partnership(db, user, clinic_id, user.fund_id)
    return fund_partnerships(user, db)


@app.get("/api/clinic/partnerships")
def clinic_partnerships(user: User = Depends(require("clinic")), db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    return _partner_rows(db, "p.clinic_id = ?", (user.clinic_id,))


@app.post("/api/clinic/partnerships/{fund_id}/{decision}")
def clinic_answer_partnership(fund_id: int, decision: Literal["accept", "decline"], user: User = Depends(require("clinic")),
                              db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    row = db.execute("SELECT status FROM clinic_fund_partnerships WHERE clinic_id = ? AND fund_id = ?",
                     (user.clinic_id, fund_id)).fetchone()
    if not row or row["status"] != "pending":
        raise HTTPException(404, "No pending request from that fund.")
    if decision == "accept":
        db.execute("UPDATE clinic_fund_partnerships SET status = 'accepted', accepted_at = ? WHERE clinic_id = ? AND fund_id = ?",
                   (clock.now_iso(), user.clinic_id, fund_id))
    else:
        db.execute("UPDATE clinic_fund_partnerships SET status = 'declined' WHERE clinic_id = ? AND fund_id = ?",
                   (user.clinic_id, fund_id))
    audit(db, f"user:{user.id}", f"partnership_{decision}ed", detail={"clinic_id": user.clinic_id, "fund_id": fund_id})
    return clinic_partnerships(user, db)


@app.delete("/api/clinic/partnerships/{fund_id}")
def clinic_remove_partnership(fund_id: int, user: User = Depends(require("clinic")), db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    f = db.execute("SELECT kind FROM funds WHERE id = ?", (fund_id,)).fetchone()
    if f and f["kind"] == "clinic":
        raise HTTPException(422, "That's your clinic's own fund.")
    _end_partnership(db, user, user.clinic_id, fund_id)
    return clinic_partnerships(user, db)



# ---------- admin: approve staff accounts ----------

@app.get("/api/admin/users")
def admin_users(user: User = Depends(require("admin")), db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        """SELECT u.id, u.name, u.first_name, u.last_name, u.email, u.role, u.status, u.created_at,
                  u.approved_at, u.last_login_at, cl.name AS clinic_name, f.name AS fund_name
           FROM users u LEFT JOIN clinics cl ON cl.id = u.clinic_id LEFT JOIN funds f ON f.id = u.fund_id
           ORDER BY CASE u.status WHEN 'pending' THEN 0 ELSE 1 END, u.role, u.name"""
    ).fetchall()
    return [dict(r) for r in rows]  # explicit columns: never the password hash


@app.post("/api/admin/users/{user_id}/{action}")
def admin_user_action(user_id: int, action: Literal["approve", "reject", "disable", "enable"],
                      user: User = Depends(require("admin")), db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    target = db.execute("SELECT id, status FROM users WHERE id = ?", (user_id,)).fetchone()
    if not target:
        raise HTTPException(404, "Account not found.")
    if user_id == user.id:
        raise HTTPException(422, "You can't change your own account here.")
    allowed = {"approve": ("pending",), "reject": ("pending",), "disable": ("active",), "enable": ("disabled",)}
    if target["status"] not in allowed[action]:
        raise HTTPException(409, f"Can't {action} an account that is {target['status']}.")
    new = {"approve": "active", "reject": "rejected", "disable": "disabled", "enable": "active"}[action]
    if action == "approve":
        db.execute("UPDATE users SET status = 'active', approved_by = ?, approved_at = ? WHERE id = ?",
                   (user.id, clock.now_iso(), user_id))
    else:
        db.execute("UPDATE users SET status = ? WHERE id = ?", (new, user_id))
    audit(db, f"user:{user.id}", f"account_{action}d", detail={"user_id": user_id})
    return admin_users(user, db)


# ---------- reports: tables, charts, Excel, and the Report Builder agent ----------

from fastapi.responses import Response  # noqa: E402

from . import ai_budget, report_agent, reports  # noqa: E402

# Tests swap this for a fake model so no real AI call is made.
model_for_reports = llm.get_model


def _report_user(user: User) -> User:
    if user.role not in ("clinic", "fund", "admin"):
        raise HTTPException(403, "Not allowed.")
    return user


def _scope_name(db: sqlite3.Connection, user: User) -> str:
    if user.role == "clinic":
        return db.execute("SELECT name FROM clinics WHERE id = ?", (user.clinic_id,)).fetchone()[0]
    if user.role == "fund":
        return db.execute("SELECT name FROM funds WHERE id = ?", (user.fund_id,)).fetchone()[0]
    return "All organizations (admin)"


class ReportParams(BaseModel):
    measure: Literal["disbursed", "pledged"] = "disbursed"
    date_basis: Literal["paid", "approved", "appointment"] = "paid"
    start: date
    end: date
    group_by: list[str] = Field(default_factory=list, max_length=3)


def _check_params(p: ReportParams, user: User) -> None:
    allowed = {d["id"] for d in reports.dims_for(user.role)}
    bad = [d for d in p.group_by if d not in allowed]
    if bad:
        raise HTTPException(422, f"Not available for your role: {', '.join(bad)}.")
    if len(set(p.group_by)) != len(p.group_by):
        raise HTTPException(422, "Each criterion can only be used once.")
    if p.start > p.end:
        raise HTTPException(422, "The start date is after the end date.")


def _run(db: sqlite3.Connection, user: User, p: ReportParams) -> tuple[list[dict], dict]:
    rows = reports.fetch_rows(db, user.role, user.clinic_id, user.fund_id, p.measure, p.date_basis, p.start, p.end)
    return rows, reports.group(rows, p.group_by)


@app.get("/api/reports/options")
def report_options(user: User = Depends(current_user), db: sqlite3.Connection = Depends(get_db)) -> dict:
    _report_user(user)
    return {"dimensions": reports.dims_for(user.role),
            "measures": [{"id": k, "label": v[0]} for k, v in reports.MEASURES.items()],
            "date_bases": [{"id": k, "label": v} for k, v in reports.DATE_BASES.items()],
            "scope_name": _scope_name(db, user), "today": clock.today().isoformat()}


@app.post("/api/reports/run")
def report_run(p: ReportParams, user: User = Depends(current_user), db: sqlite3.Connection = Depends(get_db)) -> dict:
    _report_user(user)
    _check_params(p, user)
    _, result = _run(db, user, p)
    return {**result, "group_by": p.group_by, "labels": [reports.DIMENSIONS[d][0] for d in p.group_by]}


@app.post("/api/reports/export")
def report_export(p: ReportParams, user: User = Depends(current_user), db: sqlite3.Connection = Depends(get_db)) -> Response:
    _report_user(user)
    _check_params(p, user)
    rows, result = _run(db, user, p)
    filters = reports.describe_filters(p.measure, p.date_basis, p.start, p.end, p.group_by, _scope_name(db, user))
    data = reports.to_xlsx("Calma report", filters, p.group_by, result, rows, user.role)
    audit(db, f"user:{user.id}", "report_downloaded", detail=reports.audit_detail(p.measure, p.date_basis, p.start, p.end, p.group_by, len(rows)))
    name = f"calma-report-{p.start.isoformat()}-to-{p.end.isoformat()}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


class AskBody(BaseModel):
    request: str = Field(min_length=3, max_length=500)


@app.post("/api/reports/ask")
async def report_ask(body: AskBody, user: User = Depends(current_user), db: sqlite3.Connection = Depends(get_db)) -> dict:
    """Report Builder: plain English -> settings (AI) -> numbers (report engine, no AI)."""
    _report_user(user)
    try:
        ai_budget.check(db, user.id)
    except ai_budget.BudgetExceeded as e:
        raise HTTPException(429, str(e))
    try:
        spec, notes = await report_agent.build_spec(
            body.request, user.role, clock.today(), model_for_reports(),
            on_usage=lambda u: ai_budget.record(db, user.id, "report_builder", llm.model_name(), u))
    except Exception as e:
        raise HTTPException(502, f"The report helper couldn't run: {llm.explain_ai_error(e)} You can still use the controls below.")
    p = ReportParams(measure=spec.measure, date_basis=spec.date_basis, start=spec.start, end=spec.end, group_by=spec.group_by)
    _, result = _run(db, user, p)
    audit(db, f"user:{user.id}", "report_builder_used", detail={"group_by": p.group_by, "view": spec.view})
    return {"spec": {**p.model_dump(mode="json"), "view": spec.view, "chart_value": spec.chart_value, "title": spec.title},
            "notes": notes, "result": {**result, "group_by": p.group_by, "labels": [reports.DIMENSIONS[d][0] for d in p.group_by]}}


# ---------- admin: AI usage and spending ----------

@app.get("/api/admin/ai-usage")
def admin_ai_usage(user: User = Depends(require("admin")), db: sqlite3.Connection = Depends(get_db)) -> dict:
    return ai_budget.summary(db)


# ---------- the web app (production only; must be the last route) ----------

@app.get("/{path:path}", include_in_schema=False)
def web_app(path: str):
    """Serve built files (JS, CSS, images); any other page (/clinic, /p/<link>, ...) gets index.html
    so the React app can show it. Unknown /api paths stay a 404."""
    if path.startswith("api/") or not (WEB_DIST / "index.html").exists():
        raise HTTPException(404, "Not found.")
    f = (WEB_DIST / path).resolve()
    if f.is_file() and WEB_DIST.resolve() in f.parents:
        return FileResponse(f)
    return FileResponse(WEB_DIST / "index.html")
