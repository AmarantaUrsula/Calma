"""Funds add/remove partner clinics; clinics accept. Only accepted partnerships count for matching."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend import clock
from backend.db import connect
from backend.seed import demo_credentials, seed

KS_PATIENT = {"state": "KS", "household_size": 1, "monthly_income": 1000, "gestational_weeks": 8, "needs_travel": False}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "p.db"
    monkeypatch.setenv("CALMA_DB", str(db))
    clock.freeze(datetime(2026, 11, 22, 15, tzinfo=timezone.utc))
    conn = connect(db)
    seed(conn)
    conn.close()
    from backend.main import app
    yield TestClient(app)
    clock.freeze(None)


def login(c, uid):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json=demo_credentials(uid)).json()["token"]}


def screen(c, clinic_h, answers):
    r = c.post("/api/clinic/cases", headers=clinic_h, json={"appointment_date": "2026-11-30", "procedure_cost": 900, "contact_method": "text"}).json()
    tok = r["patient_path"].split("/")[-1]
    return r["case_id"], {p["fund_name"] for p in c.post(f"/api/p/{tok}/screening", json=answers).json()["pledges"]}


def test_list_shows_partners_and_available_clinics(client):
    kai = login(client, 6)  # Later Care partners with both clinics
    d = client.get("/api/fund/partnerships", headers=kai).json()
    assert {p["clinic_name"] for p in d["partnerships"]} == {"Mesa Women's Health (demo)", "Prairie Family Clinic (demo)"}
    assert all(p["status"] == "accepted" and p["accepted_at"] for p in d["partnerships"])
    assert d["available_clinics"] == []
    jordan = login(client, 4)  # Heartland: Prairie only
    d = client.get("/api/fund/partnerships", headers=jordan).json()
    assert [c["name"] for c in d["available_clinics"]] == ["Mesa Women's Health (demo)"]
    assert client.get("/api/fund/partnerships", headers=login(client, 1)).status_code == 403


def test_request_needs_clinic_acceptance_before_matching(client):
    jordan, rosa = login(client, 4), login(client, 1)  # Heartland (KS/MO/OK) asks to partner with Mesa
    d = client.post("/api/fund/partnerships/1", headers=jordan).json()
    assert next(p for p in d["partnerships"] if p["clinic_id"] == 1)["status"] == "pending"
    assert client.post("/api/fund/partnerships/1", headers=jordan).status_code == 409
    # still pending: a KS patient at Mesa doesn't match Heartland
    _, names = screen(client, rosa, KS_PATIENT)
    assert "Heartland Access Fund" not in names
    # Mesa sees the request and accepts
    req = next(p for p in client.get("/api/clinic/partnerships", headers=rosa).json() if p["fund_id"] == 4)
    assert req["status"] == "pending" and req["requested_by"] == "fund"
    client.post("/api/clinic/partnerships/4/accept", headers=rosa)
    _, names = screen(client, rosa, KS_PATIENT)
    assert "Heartland Access Fund" in names
    assert "Heartland Access Fund" in {f["name"] for f in client.get("/api/clinic/summary", headers=rosa).json()["partner_funds"]}


def test_clinic_can_decline_and_fund_can_ask_again(client):
    jordan, rosa = login(client, 4), login(client, 1)
    client.post("/api/fund/partnerships/1", headers=jordan)
    client.post("/api/clinic/partnerships/4/decline", headers=rosa)
    d = client.get("/api/fund/partnerships", headers=jordan).json()
    assert next(p for p in d["partnerships"] if p["clinic_id"] == 1)["status"] == "declined"
    assert client.post("/api/clinic/partnerships/4/accept", headers=rosa).status_code == 404  # nothing pending
    assert client.post("/api/fund/partnerships/1", headers=jordan).status_code == 200      # can ask again


def test_removing_partner_declines_waiting_pledges_but_keeps_approved(client):
    dana, jordan = login(client, 2), login(client, 4)  # Prairie + Heartland
    c1, names = screen(client, dana, KS_PATIENT)
    c2, _ = screen(client, dana, KS_PATIENT)
    assert "Heartland Access Fund" in names
    q = client.get("/api/fund/pledges", headers=jordan).json()
    client.post(f"/api/fund/pledges/{q[0]['id']}/decide", headers=jordan, json={"decision": "approve"})
    client.delete("/api/fund/partnerships/2", headers=jordan)

    q = {p["case_id"]: p for p in client.get("/api/fund/pledges", headers=jordan).json()}
    assert q[c1]["status"] == "approved" and q[c2]["status"] == "declined"
    # approved pledge can still be paid after the visit
    client.post(f"/api/clinic/cases/{c1}/appointment-done", headers=dana)
    assert client.post(f"/api/fund/pledges/{q[c1]['id']}/mark-paid", headers=jordan).status_code == 200
    # no new matches at Prairie
    _, names = screen(client, dana, KS_PATIENT)
    assert "Heartland Access Fund" not in names
    log = client.get("/api/admin/audit", headers=login(client, 8)).json()
    assert any(e["action"] == "partnership_removed" for e in log)


def test_clinic_can_end_partnership_but_not_own_fund(client):
    dana = login(client, 2)
    assert client.delete("/api/clinic/partnerships/2", headers=dana).status_code == 422  # own fund
    rows = client.delete("/api/clinic/partnerships/4", headers=dana).json()
    assert all(r["fund_id"] != 4 for r in rows)
