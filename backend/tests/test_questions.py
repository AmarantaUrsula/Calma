"""Configurable intake questions, state-of-care funds, practical support and insurance rules."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend import clock
from backend.db import connect
from backend.matching import FundRule, Screening, match
from backend.seed import seed


def rule(fid, **kw):
    base = dict(fund_id=fid, fund_name=f"F{fid}", kind="independent", criteria_id=fid, states=("*",),
                income_max_fpl_pct=None, gest_min_weeks=None, gest_max_weeks=None, requires_travel=False,
                max_age=None, pledge_kind="fixed", pledge_value=100, pledge_cap=None)
    base.update(kw)
    return FundRule(**base)


S = Screening(state="TX", household_size=1, monthly_income=1000, gestational_weeks=8, needs_travel=True,
              care_state="NM", travel_miles=300, nights_away=2, meal_days=2, childcare_days=1,
              insurance_coverage="no")


def test_state_of_care_vs_residence():
    r = match(S, 1000, [rule(1, states=("NM",), state_basis="care"), rule(2, states=("NM",))])
    assert [m.fund_id for m in r.matches] == [1]
    assert any("Getting care in NM" in x for x in r.matches[0].reasons)
    assert any("Lives in TX" in x for x in r.skipped[0].reasons)


def test_insurance_rule():
    covered = Screening(**{**S.__dict__, "insurance_coverage": "yes"})
    assert not match(covered, 1000, [rule(1, no_insurance_only=True)]).matches
    unsure = Screening(**{**S.__dict__, "insurance_coverage": "unsure"})
    m = match(unsure, 1000, [rule(1, no_insurance_only=True)]).matches[0]
    assert any("check before approving" in x for x in m.reasons)


def test_practical_support_amount_cap_and_separate_from_bill():
    prac = rule(5, support_type="practical", pledge_value=20, rate_per_mile_cents=25, rate_per_night=100,
                rate_per_meal_day=30, rate_per_childcare_day=50, pledge_cap=None)
    r = match(S, 500, [rule(1, pledge_value=500), prac])
    p = next(m for m in r.matches if m.fund_id == 5)
    # 20 flat + 600 mi x .25 = 150 + 2 x 100 + 2 x 30 + 1 x 50 = 480
    assert p.suggested_amount == 480 and p.category == "practical"
    assert r.total_suggested == 500 and r.practical_suggested == 480  # bill fully used; practical unaffected
    capped = match(S, 500, [rule(5, **{**prac.__dict__, "fund_id": 5, "pledge_cap": 300})]).matches[0]
    assert capped.suggested_amount == 300
    no_travel = Screening(**{**S.__dict__, "needs_travel": False})
    assert not match(no_travel, 500, [prac]).matches


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "q.db"
    monkeypatch.setenv("CALMA_DB", str(db))
    clock.freeze(datetime(2026, 11, 22, 15, tzinfo=timezone.utc))
    conn = connect(db)
    seed(conn)
    conn.close()
    from backend.main import app
    yield TestClient(app)
    clock.freeze(None)


def login(c, uid):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"user_id": uid}).json()["token"]}


def new_case(c, h, date="2026-11-30", cost=900):
    r = c.post("/api/clinic/cases", headers=h, json={"appointment_date": date, "procedure_cost": cost, "contact_method": "text"}).json()
    return r["case_id"], r["patient_path"].split("/")[-1]


def test_clinic_sees_why_each_question_is_asked_and_can_add_more(client):
    rosa = login(client, 1)
    q = client.get("/api/clinic/questions", headers=rosa).json()
    assert "unhoused" in q["asked"] and any("Desert Bloom" in w for w in q["why"]["unhoused"])
    assert "insurance" in q["asked"] and "contact" not in q["asked"]
    q = client.put("/api/clinic/questions", headers=rosa, json={"extra_questions": ["contact"]}).json()
    assert "contact" in q["asked"] and q["why"]["contact"] == ["Mesa Women's Health (demo) (clinic)"]
    assert client.put("/api/clinic/questions", headers=rosa, json={"extra_questions": ["ssn"]}).status_code == 422
    _, tok = new_case(client, rosa)
    assert "contact" in client.get(f"/api/p/{tok}").json()["questions"]


def test_unasked_answers_are_dropped_and_lmp_sets_weeks(client):
    dana = login(client, 2)  # Prairie: no fund asks about unhoused or insurance
    cid, tok = new_case(client, dana, date="2026-11-30")
    client.post(f"/api/p/{tok}/screening", json={
        "state": "KS", "household_size": 2, "monthly_income": 1500, "lmp_date": "2026-10-05",
        "needs_travel": False, "unhoused": True, "insurance_coverage": "yes", "judicial_bypass": True, "age": 30})
    s = client.get(f"/api/clinic/cases/{cid}", headers=dana).json()["screening"]
    assert s["gestational_weeks"] == 8          # Oct 5 -> Nov 30 = 56 days
    assert s["unhoused"] is None and s["insurance_coverage"] is None and s["judicial_bypass"] is None
    assert s["care_state"] == "KS"


def test_contact_details_clinic_only_and_deleted_on_close(client):
    dana = login(client, 2)  # Prairie asks for contact details
    cid, tok = new_case(client, dana)
    client.post(f"/api/p/{tok}/screening", json={
        "state": "KS", "household_size": 1, "monthly_income": 1000, "gestational_weeks": 8, "needs_travel": False,
        "contact": {"first_name": "Jessie", "phone": "(555) 010-0000", "notify_pref": "text"}})
    d = client.get(f"/api/clinic/cases/{cid}", headers=dana).json()
    assert d["contact"]["first_name"] == "Jessie"
    jordan = login(client, 4)  # Heartland, a Prairie partner
    item = client.get("/api/fund/pledges", headers=jordan).json()[0]
    assert "Jessie" not in str(item) and "contact" not in item
    # close the case: decide everything, mark visit done, fund pays
    for p in d["pledges"]:
        h = dana if p["fund_kind"] == "clinic" else jordan
        path = f"/api/clinic/pledges/{p['id']}/decide" if p["fund_kind"] == "clinic" else f"/api/fund/pledges/{p['id']}/decide"
        client.post(path, headers=h, json={"decision": "decline"})
    client.post(f"/api/clinic/cases/{cid}/appointment-done", headers=dana)
    d = client.get(f"/api/clinic/cases/{cid}", headers=dana).json()
    assert d["status"] == "closed" and d["contact"] is None


def test_practical_pledge_can_be_paid_before_visit_and_not_in_reimbursement(client):
    rosa, alex = login(client, 1), login(client, 5)
    cid, tok = new_case(client, rosa)
    client.post(f"/api/p/{tok}/screening", json={
        "state": "TX", "household_size": 1, "monthly_income": 900, "gestational_weeks": 8, "needs_travel": True,
        "travel_miles": 250, "nights_away": 1, "meal_days": 1, "childcare_days": 0, "insurance_coverage": "no", "age": 25})
    item = client.get("/api/fund/pledges", headers=alex).json()[0]
    assert item["category"] == "practical" and item["answers"]["travel_miles"] == 250
    client.post(f"/api/fund/pledges/{item['id']}/decide", headers=alex, json={"decision": "approve"})
    assert client.post(f"/api/fund/pledges/{item['id']}/mark-paid", headers=alex).status_code == 200
    assert all(o["fund_name"] != "Open Road Travel Fund" for o in client.get("/api/clinic/reimbursements", headers=rosa).json())
    v = client.get(f"/api/p/{tok}").json()
    assert v["practical_approved"] == 215 and v["you_may_owe"] == 900  # 500 mi x .20 + 90 + 25; bill unchanged


def test_fund_can_ask_extra_questions_and_switch_basis(client):
    jordan = login(client, 4)
    rules = client.get("/api/fund/rules", headers=jordan).json()["rules"]
    r = client.put("/api/fund/rules", headers=jordan, json={**rules, "extra_questions": ["unhoused", "insurance"], "state_basis": "care"})
    assert r.status_code == 200 and r.json()["rules"]["state_basis"] == "care"
    assert client.put("/api/fund/rules", headers=jordan, json={**rules, "extra_questions": ["contact"]}).status_code == 422
    q = client.get("/api/clinic/questions", headers=login(client, 2)).json()
    assert {"unhoused", "insurance"} <= set(q["asked"])
