"""Seed the demo database with made-up clinics, funds and staff.

Every clinic, fund and person here is fictional. Phone numbers use the
555-01xx range reserved for fiction.

    python -m backend.seed        # wipes data/calma.db and reseeds
"""

from __future__ import annotations

import json

from .clock import now_iso
from .db import connect, db_path, init_schema
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
    init_schema(conn)
    conn.executemany("INSERT INTO clinics (id, name, city, state, phone) VALUES (?, ?, ?, ?, ?)", CLINICS)
    conn.executemany(
        "INSERT INTO funds (id, name, kind, owner_clinic_id, monthly_limit, description) VALUES (?, ?, ?, ?, ?, ?)",
        FUNDS,
    )
    conn.executemany("UPDATE funds SET policy_url = ? WHERE id = ?", [(u, i) for i, u in POLICY_URLS.items()])
    conn.executemany(
        """INSERT INTO clinic_fund_partnerships (clinic_id, fund_id, status, requested_by, created_at, accepted_at)
           VALUES (?, ?, 'accepted', 'seed', ?, ?)""",
        [(c, f, now_iso(), now_iso()) for c, f in PARTNERSHIPS],
    )
    for fund_id, c in CRITERIA.items():
        insert_rule(conn, fund_id, 1, "approved", c, last_verified_at=now_iso(), verified_by="seed data")
    for clinic_id, qs in CLINIC_EXTRAS.items():
        conn.execute("UPDATE clinics SET extra_questions = ? WHERE id = ?", (json.dumps(qs), clinic_id))
    conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", USERS)
    conn.commit()


def reset() -> None:
    p = db_path()
    if p.exists():
        p.unlink()
    conn = connect(p)
    try:
        seed(conn)
    finally:
        conn.close()
    print(f"Seeded {p}")


if __name__ == "__main__":
    reset()
