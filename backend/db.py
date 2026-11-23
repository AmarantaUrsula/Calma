"""SQLite storage for Calma.

Data minimization is the default: a case stores only what matching needs
(state, household size, monthly income, gestational weeks, travel need, age).
No names, phone numbers or emails are stored here; in a real deployment the
clinic's scheduling system sends the link.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DB = DATA_DIR / "calma.db"


def db_path() -> Path:
    return Path(os.environ.get("CALMA_DB", DEFAULT_DB))


SCHEMA = """
CREATE TABLE IF NOT EXISTS clinics (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    phone TEXT NOT NULL
);

-- kind = 'clinic' (a clinic's own justice/internal fund, a block grant with a
-- monthly limit) or 'independent' (an outside abortion fund that partners with
-- several clinics).
CREATE TABLE IF NOT EXISTS funds (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('clinic', 'independent')),
    owner_clinic_id INTEGER REFERENCES clinics(id),
    monthly_limit INTEGER,           -- dollars; enforced for clinic funds, shown for independent funds
    description TEXT NOT NULL DEFAULT ''
);

-- The clinic is the hub: a fund only sees cases from clinics it partners with.
CREATE TABLE IF NOT EXISTS clinic_fund_partnerships (
    clinic_id INTEGER NOT NULL REFERENCES clinics(id),
    fund_id INTEGER NOT NULL REFERENCES funds(id),
    PRIMARY KEY (clinic_id, fund_id)
);

-- Versioned eligibility rules. Matching reads only the newest approved version.
CREATE TABLE IF NOT EXISTS fund_criteria (
    id INTEGER PRIMARY KEY,
    fund_id INTEGER NOT NULL REFERENCES funds(id),
    version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('proposed', 'approved', 'retired')),
    states TEXT NOT NULL,            -- JSON list of state codes, or ["*"] for any state
    income_max_fpl_pct INTEGER,      -- NULL = no income limit
    gest_min_weeks INTEGER,
    gest_max_weeks INTEGER,
    requires_travel INTEGER NOT NULL DEFAULT 0,
    max_age INTEGER,                 -- identity criterion, e.g. youth funds
    pledge_kind TEXT NOT NULL CHECK (pledge_kind IN ('fixed', 'percent')),
    pledge_value INTEGER NOT NULL,   -- dollars (fixed) or percent of procedure cost
    pledge_cap INTEGER,              -- dollars; cap for percent pledges
    source_url TEXT,
    last_verified_at TEXT,
    verified_by TEXT,
    UNIQUE (fund_id, version)
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('clinic', 'fund', 'admin')),
    clinic_id INTEGER REFERENCES clinics(id),
    fund_id INTEGER REFERENCES funds(id)
);

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY,
    clinic_id INTEGER NOT NULL REFERENCES clinics(id),
    token TEXT NOT NULL UNIQUE,
    token_expires_at TEXT NOT NULL,
    appointment_date TEXT NOT NULL,
    procedure_cost INTEGER NOT NULL,
    contact_method TEXT NOT NULL CHECK (contact_method IN ('text', 'email')),
    language TEXT NOT NULL DEFAULT 'en',
    status TEXT NOT NULL DEFAULT 'link_sent'
        CHECK (status IN ('link_sent', 'screened', 'appointment_done', 'closed')),
    -- screening answers (filled in by the patient)
    state TEXT,
    household_size INTEGER,
    monthly_income INTEGER,
    gestational_weeks INTEGER,       -- NULL = patient not sure
    needs_travel INTEGER,
    age INTEGER,
    created_at TEXT NOT NULL,
    submitted_at TEXT
);

-- status: pending (waiting for a person to approve) -> approved | declined -> paid (completed)
CREATE TABLE IF NOT EXISTS pledges (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES cases(id),
    fund_id INTEGER NOT NULL REFERENCES funds(id),
    criteria_id INTEGER NOT NULL REFERENCES fund_criteria(id),
    suggested_amount INTEGER NOT NULL,
    approved_amount INTEGER,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'declined', 'paid')),
    reasons TEXT NOT NULL,           -- JSON list of plain-English reasons
    decided_by INTEGER REFERENCES users(id),
    decided_at TEXT,
    paid_at TEXT,
    UNIQUE (case_id, fund_id)
);

-- Scheduled website checks: one row per fetch of a fund's eligibility page.
-- status: unchanged | rules_same | proposal_created | skipped_pending_review | error
CREATE TABLE IF NOT EXISTS page_checks (
    id INTEGER PRIMARY KEY,
    fund_id INTEGER NOT NULL REFERENCES funds(id),
    url TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    trigger TEXT NOT NULL,           -- 'schedule' or 'user:<id>'
    status TEXT NOT NULL,
    content_hash TEXT,               -- set only when this check becomes the new baseline
    page_text TEXT,                  -- snapshot of the extracted text (truncated)
    note TEXT,
    criteria_id INTEGER              -- proposal created by this check, if any
);

-- Optional contact details. Only the patient's clinic sees these; never funds, never the AI.
-- Deleted when the case closes.
CREATE TABLE IF NOT EXISTS case_contacts (
    case_id INTEGER PRIMARY KEY REFERENCES cases(id),
    first_name TEXT,
    last_name TEXT,
    phone TEXT,
    email TEXT,
    notify_pref TEXT                 -- 'text' | 'email'
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,             -- 'user:<id>', 'patient', or 'system'
    action TEXT NOT NULL,
    case_id INTEGER,
    detail TEXT
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Columns added after v1. SQLite can add columns in place, so existing demo databases keep working.
ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "fund_criteria": [
        ("evidence", "TEXT"),                       # AI-extracted quotes for a proposed version
        ("proposed_by", "TEXT"),
        ("state_basis", "TEXT NOT NULL DEFAULT 'residence'"),   # 'residence' or 'care' (state where the abortion happens)
        ("support_type", "TEXT NOT NULL DEFAULT 'procedure'"),  # 'procedure' (toward the clinic bill) or 'practical' (travel, food, lodging, childcare)
        ("rate_per_mile_cents", "INTEGER"),         # practical support: per round-trip mile
        ("rate_per_night", "INTEGER"),              # practical support: lodging per night
        ("rate_per_meal_day", "INTEGER"),           # practical support: meals per day
        ("rate_per_childcare_day", "INTEGER"),      # practical support: dependent care per day
        ("no_insurance_only", "INTEGER NOT NULL DEFAULT 0"),    # only helps if insurance doesn't cover abortion
        ("extra_questions", "TEXT NOT NULL DEFAULT '[]'"),      # optional intake questions this fund wants asked
    ],
    "funds": [
        ("policy_url", "TEXT"),
        # Real funds tracked for their public rules only: never partnered with the made-up demo clinics,
        # never matched with demo patients, no staff accounts.
        ("reference_only", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "clinics": [("extra_questions", "TEXT NOT NULL DEFAULT '[]'")],
    "cases": [
        ("care_state", "TEXT"),                     # from the clinic's location, not asked
        ("travel_miles", "INTEGER"),
        ("nights_away", "INTEGER"),
        ("meal_days", "INTEGER"),
        ("childcare_days", "INTEGER"),
        ("unhoused", "INTEGER"),
        ("judicial_bypass", "INTEGER"),
        ("insurance_coverage", "TEXT"),             # 'yes' | 'no' | 'unsure'
        ("questions_asked", "TEXT"),                # JSON list of question ids shown to this patient
    ],
    "pledges": [("category", "TEXT NOT NULL DEFAULT 'procedure'")],
    # Staff accounts. password_hash is a salted scrypt hash (see backend/auth.py), never the password.
    "users": [
        ("first_name", "TEXT"),
        ("last_name", "TEXT"),
        ("email", "TEXT"),                               # stored lowercase; unique
        ("password_hash", "TEXT"),
        ("status", "TEXT NOT NULL DEFAULT 'active'"),    # 'pending' | 'active' | 'rejected' | 'disabled'
        ("created_at", "TEXT"),
        ("approved_by", "INTEGER"),
        ("approved_at", "TEXT"),
        ("last_login_at", "TEXT"),
    ],
    # A fund asks to partner with a clinic; the clinic accepts. Only accepted partnerships count.
    "clinic_fund_partnerships": [
        ("status", "TEXT NOT NULL DEFAULT 'accepted'"),   # 'pending' | 'accepted' | 'declined'
        ("requested_by", "TEXT"),                        # 'fund' | 'clinic' | 'seed'
        ("created_at", "TEXT"),
        ("accepted_at", "TEXT"),
    ],
}


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for table, cols in ADDED_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email ON users(email) WHERE email IS NOT NULL")


def audit(conn: sqlite3.Connection, actor: str, action: str, case_id: int | None = None, detail: dict | None = None) -> None:
    from .clock import now_iso

    conn.execute(
        "INSERT INTO audit_log (at, actor, action, case_id, detail) VALUES (?, ?, ?, ?, ?)",
        (now_iso(), actor, action, case_id, json.dumps(detail) if detail else None),
    )
