"""Seed the demo database with made-up clinics, funds and staff.

Every clinic, fund and person here is fictional. Phone numbers use the
555-01xx range reserved for fiction.

    python -m backend.seed        # wipes data/calma.db and reseeds
"""

from __future__ import annotations

import json
import os

from .clock import now_iso
from .db import connect, db_path, init_schema
from .auth import hash_password
from .proposals import insert_rule

CLINICS = [
    (1, "Mesa Women's Health (demo)", "Albuquerque", "NM", "(505) 555-0142"),
    (2, "Prairie Family Clinic (demo)", "Wichita", "KS", "(316) 555-0187"),
]

# id, name, kind, owner_clinic_id, monthly_limit, description
FUNDS = [
    (1, "Mesa Justice Fund", "clinic", 1, 6000, "Mesa's own fund. Covers up to half the cost, max $300."),
    (2, "Prairie Patient Assistance Fund", "clinic", 2, 4000, "Prairie's own fund. Covers up to half the cost, max $250."),
    (3, "Desert Bloom Fund", "independent", None, 8000, "Fictional fund for TX, NM and AZ residents."),
    (4, "Heartland Access Fund", "independent", None, 5000, "Fictional fund for KS, MO and OK residents."),
    (5, "Open Road Travel Fund", "independent", None, 3000, "Fictional practical-support fund: gas, lodging, meals and childcare for TX and OK patients who must travel."),
    (6, "Later Care Fund", "independent", None, 10000, "Fictional fund for care at 14–24 weeks, any state."),
    (7, "Youth Access Fund", "independent", None, 2000, "Fictional fund for patients age 19 and under."),
    (8, "Enchanted Circle Care Fund", "independent", None, 4000, "Fictional fund for anyone getting care in New Mexico, wherever they live."),
]

# Real abortion funds, tracked for their PUBLIC eligibility pages only (reference_only = 1).
# They are never partnered with the made-up clinics or matched with demo patients, and have no
# accounts. Their rules start empty: the first website check suggests rules for an admin to review.
REAL_FUNDS = [
    (10, "Carolina Abortion Fund", "Real fund (reference only). North and South Carolina.",
     "https://www.carolinaabortionfund.org/get-help"),
    (11, "West Fund", "Real fund (reference only). New Mexico and Texas. Page: NNAF profile.",
     "https://abortionfunds.org/fund/west-fund/"),
    (12, "Faith Roots Abortion Fund", "Real fund (reference only). Travel help for people coming to New Mexico. Page: NNAF profile.",
     "https://abortionfunds.org/fund/faith-roots-abortion-fund/"),
    (13, "Mariposa Fund", "Real fund (reference only). New Mexico; people affected by the immigration system. Page: NNAF profile.",
     "https://abortionfunds.org/fund/mariposa-fund/"),
]


def add_real_funds(conn) -> None:
    for fid, name, desc, url in REAL_FUNDS:
        conn.execute(
            """INSERT OR IGNORE INTO funds (id, name, kind, owner_clinic_id, monthly_limit, description, policy_url, reference_only)
               VALUES (?, ?, 'independent', NULL, NULL, ?, ?, 1)""",
            (fid, name, desc, url),
        )


# Demo eligibility "websites": files in data/demo_pages/ (edit one to simulate a fund changing its site).
# Clinic funds have no public page; their rules are set by the clinic.
POLICY_URLS = {
    3: "demo://desert-bloom",
    4: "demo://heartland-access",
    5: "demo://open-road",
    6: "demo://later-care",
    7: "demo://youth-access",
    8: "demo://enchanted-circle",
}

PARTNERSHIPS = [
    (1, 1), (1, 3), (1, 5), (1, 6), (1, 7), (1, 8),
    (2, 2), (2, 4), (2, 5), (2, 6),
]

# fund_id: criteria (version 1, approved)
CRITERIA = {
    1: dict(states=["*"], income_max_fpl_pct=300, pledge_kind="percent", pledge_value=50, pledge_cap=300),
    2: dict(states=["*"], income_max_fpl_pct=250, pledge_kind="percent", pledge_value=50, pledge_cap=250),
    3: dict(states=["TX", "NM", "AZ"], income_max_fpl_pct=300, pledge_kind="fixed", pledge_value=250,
            no_insurance_only=True, extra_questions=["unhoused"]),
    4: dict(states=["KS", "MO", "OK"], income_max_fpl_pct=250, pledge_kind="fixed", pledge_value=200),
    # Practical support: $0.20 per round-trip mile, $90/night, $25/day meals, $40/day childcare, up to $400.
    5: dict(states=["TX", "OK"], support_type="practical", pledge_kind="fixed", pledge_value=0, pledge_cap=400,
            rate_per_mile_cents=20, rate_per_night=90, rate_per_meal_day=25, rate_per_childcare_day=40),
    6: dict(states=["*"], income_max_fpl_pct=400, gest_min_weeks=14, gest_max_weeks=24,
            pledge_kind="percent", pledge_value=20, pledge_cap=500),
    7: dict(states=["*"], max_age=19, pledge_kind="fixed", pledge_value=150, extra_questions=["judicial_bypass"]),
    # Eligibility by state of care (where the abortion happens), not where the patient lives.
    8: dict(states=["NM"], state_basis="care", income_max_fpl_pct=250, pledge_kind="fixed", pledge_value=150),
}

# Demo staff accounts. All share one demo password, stored only as a hash.
# Locally it defaults to the made-up value below (listed in README.md). On a public deployment
# (Render) set CALMA_DEMO_PASSWORD in the host's settings instead, because this repo is public
# and anyone could read the default. With CALMA_REQUIRE_DEMO_PASSWORD=1, seeding refuses to run
# without it rather than fall back to the public default.
LOCAL_DEMO_PASSWORD = "calma-demo-2026"
DEMO_PASSWORD = os.environ.get("CALMA_DEMO_PASSWORD") or LOCAL_DEMO_PASSWORD


class MissingDemoPassword(RuntimeError):
    pass


def check_demo_password() -> None:
    if os.environ.get("CALMA_REQUIRE_DEMO_PASSWORD") == "1":
        pw = os.environ.get("CALMA_DEMO_PASSWORD", "")
        if not pw:
            raise MissingDemoPassword(
                "CALMA_DEMO_PASSWORD is not set. On Render: open this service > Environment > Add "
                "Environment Variable, key CALMA_DEMO_PASSWORD, a password of at least 10 characters that "
                "isn't the public README default. Save, then redeploy. (This keeps the demo accounts private "
                "because the GitHub repo is public.)")
        if pw == LOCAL_DEMO_PASSWORD:
            raise MissingDemoPassword(
                "CALMA_DEMO_PASSWORD is set to the public default from the README, which anyone can read on "
                "GitHub. Choose a different password under this service > Environment, then redeploy.")
        if len(pw) < 10:
            raise MissingDemoPassword("CALMA_DEMO_PASSWORD must be at least 10 characters. Change it under "
                                      "this service > Environment, then redeploy.")
DEMO_EMAILS = {
    1: "rosa@mesa.example.org", 2: "dana@prairie.example.org", 3: "sam@desertbloom.example.org",
    4: "jordan@heartland.example.org", 5: "alex@openroad.example.org", 6: "kai@latercare.example.org",
    7: "mia@youthaccess.example.org", 8: "admin@calma.example.org", 9: "lu@enchantedcircle.example.org",
}


def demo_credentials(user_id: int) -> dict:
    return {"email": DEMO_EMAILS[user_id], "password": DEMO_PASSWORD}


# id, name, role, clinic_id, fund_id
USERS = [
    (1, "Rosa (Mesa front desk)", "clinic", 1, None),
    (2, "Dana (Prairie front desk)", "clinic", 2, None),
    (3, "Sam (Desert Bloom)", "fund", None, 3),
    (4, "Jordan (Heartland Access)", "fund", None, 4),
    (5, "Alex (Open Road Travel)", "fund", None, 5),
    (6, "Kai (Later Care)", "fund", None, 6),
    (7, "Mia (Youth Access)", "fund", None, 7),
    (8, "Admin (Calma)", "admin", None, None),
    (9, "Lu (Enchanted Circle)", "fund", None, 8),
]

# Optional intake questions each clinic chose to ask (beyond what its funds need).
CLINIC_EXTRAS = {2: ["contact"]}


def seed(conn) -> None:
    check_demo_password()
    init_schema(conn)
    conn.executemany("INSERT INTO clinics (id, name, city, state, phone) VALUES (?, ?, ?, ?, ?)", CLINICS)
    conn.executemany(
        "INSERT INTO funds (id, name, kind, owner_clinic_id, monthly_limit, description) VALUES (?, ?, ?, ?, ?, ?)",
        FUNDS,
    )
    conn.executemany("UPDATE funds SET policy_url = ? WHERE id = ?", [(u, i) for i, u in POLICY_URLS.items()])
    add_real_funds(conn)
    conn.executemany(
        """INSERT INTO clinic_fund_partnerships (clinic_id, fund_id, status, requested_by, created_at, accepted_at)
           VALUES (?, ?, 'accepted', 'seed', ?, ?)""",
        [(c, f, now_iso(), now_iso()) for c, f in PARTNERSHIPS],
    )
    for fund_id, c in CRITERIA.items():
        insert_rule(conn, fund_id, 1, "approved", c, last_verified_at=now_iso(), verified_by="seed data")
    for clinic_id, qs in CLINIC_EXTRAS.items():
        conn.execute("UPDATE clinics SET extra_questions = ? WHERE id = ?", (json.dumps(qs), clinic_id))
    for uid, name, role, clinic_id, fund_id in USERS:
        first = name.split(" (")[0]
        last = name.split("(")[1].split(" ")[0].rstrip(")") if "(" in name else ""
        conn.execute(
            """INSERT INTO users (id, name, role, clinic_id, fund_id, first_name, last_name, email, password_hash,
               status, created_at, approved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (uid, name, role, clinic_id, fund_id, first, last, DEMO_EMAILS[uid], hash_password(DEMO_PASSWORD),
             now_iso(), now_iso()),
        )
    conn.commit()


def add_history(conn, n: int = 90, months: int = 6, rng_seed: int = 7) -> int:
    """Made-up past cases (closed, with approved and paid pledges) so reports have something to show.
    Run through the real matching engine, so pledges follow each fund's rules. Deterministic."""
    import random
    import secrets
    from datetime import timedelta

    from . import clock
    from .main import approved_rules, clinic_fund_ids, question_plan, screening_of
    from .matching import match

    rng = random.Random(rng_seed)
    today = clock.today()
    homes = {1: ["TX"] * 10 + ["NM"] * 7 + ["AZ", "AZ", "CO", "OK"], 2: ["KS"] * 11 + ["MO"] * 4 + ["OK"] * 3 + ["TX", "NE"]}
    care_state = {1: "NM", 2: "KS"}
    made = 0
    for _ in range(n):
        clinic = rng.choice([1, 1, 2])
        appt = today - timedelta(days=rng.randint(4, months * 30))
        created = appt - timedelta(days=rng.randint(3, 10))
        home = rng.choice(homes[clinic])
        weeks = min(24, max(5, int(rng.triangular(5, 24, 8))))
        travel = home != care_state[clinic] or rng.random() < 0.25
        cost = rng.randrange(650, 1400, 25) if weeks < 14 else rng.randrange(1500, 3200, 50)
        hh = rng.choice([1, 1, 2, 2, 3, 3, 4, 5])
        cur = conn.execute(
            """INSERT INTO cases (clinic_id, token, token_expires_at, appointment_date, procedure_cost, contact_method,
               language, status, state, household_size, monthly_income, gestational_weeks, needs_travel, age,
               care_state, travel_miles, nights_away, meal_days, childcare_days, insurance_coverage, unhoused,
               created_at, submitted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'closed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (clinic, secrets.token_urlsafe(24), (appt + timedelta(days=2)).isoformat() + "T00:00:00+00:00",
             appt.isoformat(), cost, rng.choice(["text", "text", "email"]), "es" if rng.random() < 0.3 else "en",
             home, hh, rng.randrange(500, 900 * hh + 1800, 50), weeks, int(travel), rng.randint(16, 42),
             care_state[clinic],
             rng.randrange(60, 650, 10) if travel else None, rng.choice([0, 1, 1, 2]) if travel else None,
             rng.choice([0, 1, 2]) if travel else None, rng.choice([0, 0, 1, 2]) if travel else None,
             rng.choice(["no"] * 8 + ["unsure", "yes"]), int(rng.random() < 0.06),
             created.isoformat() + "T15:00:00+00:00", created.isoformat() + "T15:00:00+00:00"),
        )
        case_id = cur.lastrowid
        conn.execute("UPDATE cases SET questions_asked = ? WHERE id = ?",
                     (json.dumps(question_plan(conn, clinic)[0]), case_id))
        case = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        result = match(screening_of(case), cost, approved_rules(conn, clinic_fund_ids(conn, clinic)))
        open_left = False
        for m in result.matches:
            decided = created + timedelta(days=rng.randint(0, 3))
            if rng.random() < 0.13:
                status, amount, paid = "declined", None, None
            else:
                amount = m.suggested_amount if rng.random() < 0.85 else max(25, round(m.suggested_amount * 0.8 / 5) * 5)
                if m.category == "practical":
                    paid = appt - timedelta(days=1)
                elif m.kind == "clinic":
                    paid = appt
                else:
                    paid = appt + timedelta(days=rng.randint(3, 28))
                status = "paid" if paid <= today else "approved"
                open_left = open_left or status == "approved"
                paid = paid if status == "paid" else None
            conn.execute(
                """INSERT INTO pledges (case_id, fund_id, criteria_id, suggested_amount, approved_amount, status,
                   reasons, category, decided_by, decided_at, paid_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                (case_id, m.fund_id, m.criteria_id, m.suggested_amount, amount, status, json.dumps(m.reasons),
                 m.category, decided.isoformat() + "T16:00:00+00:00",
                 paid.isoformat() + "T17:00:00+00:00" if paid else None),
            )
        if open_left:
            conn.execute("UPDATE cases SET status = 'appointment_done' WHERE id = ?", (case_id,))
        made += 1
    conn.commit()
    return made


def reset() -> None:
    check_demo_password()  # before touching the database, so a bad setting never leaves an empty file behind
    p = db_path()
    if p.exists():
        p.unlink()
    conn = connect(p)
    try:
        seed(conn)
        n = add_history(conn)
    finally:
        conn.close()
    print(f"Seeded {p} (with {n} past cases for reports)")


if __name__ == "__main__":
    reset()
