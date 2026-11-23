"""End-to-end flow: clinic books -> patient screens -> clinic & fund approve -> reimbursement."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend import clock
from backend.db import connect
from backend.seed import demo_credentials, seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("CALMA_DB", str(db))
    conn = connect(db)
    seed(conn)
    conn.close()
    clock.freeze(datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc))
    from backend.main import app
    yield TestClient(app)
    clock.freeze(None)


def login(client, user_id):
    tok = client.post("/api/auth/login", json=demo_credentials(user_id)).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def book(client, h, cost=900, date="2026-11-30"):
    r = client.post("/api/clinic/cases", headers=h,
                    json={"appointment_date": date, "procedure_cost": cost, "contact_method": "text"})
    assert r.status_code == 200, r.text
    return r.json()


def test_full_flow(client):
    rosa = login(client, 1)  # Mesa clinic (NM)
    case = book(client, rosa)
    token = case["patient_path"].split("/")[-1]

    v = client.get(f"/api/p/{token}").json()
    assert v["submitted"] is False and v["clinic_phone"]

    assert set(v["questions"]) >= {"state", "income", "pregnancy", "age", "insurance", "travel_miles", "nights_away"}

    # TX patient, 3 people, $2000/mo (90% FPL), 16 weeks, must travel 200 miles, 1 night, 2 days of meals, age 22
    answers = {"state": "TX", "household_size": 3, "monthly_income": 2000, "gestational_weeks": 16,
               "needs_travel": True, "age": 22, "insurance_coverage": "no", "travel_miles": 200,
               "nights_away": 1, "meal_days": 2, "childcare_days": 0}
    r = client.post(f"/api/p/{token}/screening", json=answers)
    assert r.status_code == 200, r.text
    names = {p["fund_name"]: p for p in r.json()["pledges"]}
    # Mesa Justice (clinic) + Desert Bloom (TX, no insurance) + Later Care (16 wks) + Enchanted Circle (care in NM)
    # + Open Road practical help. Not Youth (age 22).
    assert set(names) == {"Mesa Justice Fund", "Desert Bloom Fund", "Open Road Travel Fund", "Later Care Fund",
                          "Enchanted Circle Care Fund"}
    assert all(p["status"] == "pending" for p in names.values())
    assert names["Mesa Justice Fund"]["amount"] == 300
    # practical: 400 round-trip miles x $0.20 + 1 night x $90 + 2 days meals x $25 = $220, separate from the bill
    assert names["Open Road Travel Fund"]["amount"] == 220 and names["Open Road Travel Fund"]["category"] == "practical"

    # Second submit is refused
    assert client.post(f"/api/p/{token}/screening", json=answers).status_code == 409

    # Clinic approves its own fund; can't decide a partner fund's pledge
    detail = client.get(f"/api/clinic/cases/{case['case_id']}", headers=rosa).json()
    own = next(p for p in detail["pledges"] if p["fund_kind"] == "clinic")
    other = next(p for p in detail["pledges"] if p["fund_name"] == "Desert Bloom Fund")
    assert client.post(f"/api/clinic/pledges/{own['id']}/decide", headers=rosa, json={"decision": "approve"}).status_code == 200
    assert client.post(f"/api/clinic/pledges/{other['id']}/decide", headers=rosa, json={"decision": "approve"}).status_code == 404
    assert any(n["fund_name"] == "Youth Access Fund" for n in detail["not_matched"])

    # Fund sees it (no raw income), approves a smaller amount
    sam = login(client, 3)  # Desert Bloom
    q = client.get("/api/fund/pledges", headers=sam).json()
    assert len(q) == 1 and "monthly_income" not in q[0] and q[0]["income_fpl_pct"] == 90
    assert client.post(f"/api/fund/pledges/{q[0]['id']}/decide", headers=sam,
                       json={"decision": "approve", "amount": 200}).status_code == 200

    # Heartland (KS fund, not a Mesa partner) sees nothing
    assert client.get("/api/fund/pledges", headers=login(client, 4)).json() == []

    # Can't mark paid before appointment is done
    assert client.post(f"/api/fund/pledges/{q[0]['id']}/mark-paid", headers=sam).status_code == 409

    # Other funds decline / approve
    alex, kai = login(client, 5), login(client, 6)
    pid = client.get("/api/fund/pledges", headers=alex).json()[0]["id"]
    client.post(f"/api/fund/pledges/{pid}/decide", headers=alex, json={"decision": "decline"})
    pid = client.get("/api/fund/pledges", headers=kai).json()[0]["id"]
    client.post(f"/api/fund/pledges/{pid}/decide", headers=kai, json={"decision": "approve"})
    lu = login(client, 9)
    lq = client.get("/api/fund/pledges", headers=lu).json()
    assert lq[0]["answers"]["care_state"] == "NM" and "age" not in lq[0]["answers"]  # only what this fund needs
    client.post(f"/api/fund/pledges/{lq[0]['id']}/decide", headers=lu, json={"decision": "decline"})

    v = client.get(f"/api/p/{token}").json()
    assert v["approved_total"] == 300 + 200 + 180  # Later Care: 20% of 900
    assert v["you_may_owe"] == 900 - 680

    # Appointment done -> clinic fund completed; fund pledges owed
    assert client.post(f"/api/clinic/cases/{case['case_id']}/appointment-done", headers=rosa).status_code == 200
    owed = client.get("/api/clinic/reimbursements", headers=rosa).json()
    assert {o["fund_name"] for o in owed if o["status"] == "approved"} == {"Desert Bloom Fund", "Later Care Fund"}

    client.post(f"/api/fund/pledges/{q[0]['id']}/mark-paid", headers=sam)
    client.post(f"/api/fund/pledges/{pid}/mark-paid", headers=kai)
    cases = client.get("/api/clinic/cases", headers=rosa).json()
    assert cases[0]["status"] == "closed"


def test_clinic_monthly_limit(client):
    dana = login(client, 2)  # Prairie fund: $4000/month, 50% up to $250
    for _ in range(17):
        c = book(client, dana, cost=1000)
        tok = c["patient_path"].split("/")[-1]
        client.post(f"/api/p/{tok}/screening", json={
            "state": "KS", "household_size": 1, "monthly_income": 1000,
            "gestational_weeks": 8, "needs_travel": False})
    pending = [p for c in client.get("/api/clinic/cases", headers=dana).json() for p in c["pledges"]
               if p["fund_kind"] == "clinic"]
    codes = [client.post(f"/api/clinic/pledges/{p['id']}/decide", headers=dana,
                         json={"decision": "approve"}).status_code for p in pending]
    assert codes[:16] == [200] * 16 and codes[16] == 409  # 16 x 250 = 4000


def test_auth_and_expiry(client):
    assert client.get("/api/clinic/cases").status_code == 401
    assert client.get("/api/fund/pledges", headers=login(client, 1)).status_code == 403
    c = book(client, login(client, 1), date="2026-11-23")
    tok = c["patient_path"].split("/")[-1]
    clock.freeze(datetime(2026, 11, 26, tzinfo=timezone.utc))
    r = client.get(f"/api/p/{tok}")
    assert r.status_code == 410 and r.json()["detail"]["clinic_phone"]
