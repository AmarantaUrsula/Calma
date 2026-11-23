"""Funds edit and confirm their own eligibility rules."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from backend import clock
from backend.db import connect
from backend.seed import demo_credentials, seed

START = datetime(2026, 11, 22, 15, tzinfo=timezone.utc)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "f.db"
    monkeypatch.setenv("CALMA_DB", str(db))
    clock.freeze(START)  # before seeding, so "last verified" is START
    conn = connect(db)
    seed(conn)
    conn.close()
    from backend import main
    yield TestClient(main.app), main
    clock.freeze(None)


def login(c, uid):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json=demo_credentials(uid)).json()["token"]}


def rules(c, h):
    return c.get("/api/fund/rules", headers=h).json()


def test_view_and_permissions(client):
    c, _ = client
    sam = login(c, 3)
    v = rules(c, sam)
    assert v["version"] == 1 and v["rules"]["states"] == ["AZ", "NM", "TX"] and v["rules"]["pledge_value"] == 250
    assert v["needs_confirm"] is False and v["pending_ai_review"] is False
    assert c.get("/api/fund/rules", headers=login(c, 1)).status_code == 403  # clinic staff
    assert c.put("/api/fund/rules", headers=login(c, 8), json=v["rules"]).status_code == 403  # admin uses its own screen


def test_edit_goes_live_and_changes_matching(client):
    c, _ = client
    sam, rosa = login(c, 3), login(c, 1)
    new = {**rules(c, sam)["rules"], "states": ["tx", "nm", "az", "co"], "pledge_value": 300}
    r = c.put("/api/fund/rules", headers=sam, json=new)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["version"] == 2 and v["rules"]["states"] == ["AZ", "CO", "NM", "TX"] and v["verified_by"] == "Sam (Desert Bloom)"
    assert [h["status"] for h in v["history"]] == ["approved", "retired"]

    case = c.post("/api/clinic/cases", headers=rosa, json={"appointment_date": "2026-11-30", "procedure_cost": 900, "contact_method": "text"}).json()
    tok = case["patient_path"].split("/")[-1]
    out = c.post(f"/api/p/{tok}/screening", json={"state": "CO", "household_size": 2, "monthly_income": 1500, "gestational_weeks": 8, "needs_travel": False}).json()
    db = next(p for p in out["pledges"] if p["fund_name"] == "Desert Bloom Fund")
    assert db["amount"] == 300

    log = c.get("/api/admin/audit", headers=login(c, 8)).json()
    e = next(x for x in log if x["action"] == "rules_updated_by_fund")
    assert "states" in e["detail"] and "pledge_value" in e["detail"]


def test_bad_values_rejected(client):
    c, _ = client
    sam = login(c, 3)
    base = rules(c, sam)["rules"]
    assert c.put("/api/fund/rules", headers=sam, json={**base, "states": ["XX"]}).status_code == 422
    assert c.put("/api/fund/rules", headers=sam, json={**base, "pledge_kind": "percent", "pledge_value": 150}).status_code == 422
    assert c.put("/api/fund/rules", headers=sam, json={**base, "gest_min_weeks": 20, "gest_max_weeks": 10}).status_code == 422
    r = c.put("/api/fund/rules", headers=sam, json=base)
    assert r.status_code == 422 and "Nothing changed" in r.json()["detail"]


def test_confirm_resets_reminder_without_new_version(client):
    c, _ = client
    sam = login(c, 3)
    clock.freeze(START + timedelta(days=61))
    sam = login(c, 3)  # session from before the time jump would have expired
    v = rules(c, sam)
    assert v["needs_confirm"] is True and v["days_since_confirmed"] == 61
    v = c.post("/api/fund/rules/confirm", headers=sam).json()
    assert v["needs_confirm"] is False and v["version"] == 1 and v["verified_by"] == "Sam (Desert Bloom)"


def test_fund_edit_replaces_pending_ai_suggestion(client, monkeypatch):
    c, main = client
    fake = {
        "summary": "x", "states": {"stated": True, "value": ["TX"], "quote": "Texas"},
        "income_max_fpl_pct": {"stated": False}, "gest_min_weeks": {"stated": False}, "gest_max_weeks": {"stated": False},
        "requires_travel": {"stated": False}, "max_age": {"stated": False},
        "pledge": {"stated": False}, "other_requirements": [],
    }
    monkeypatch.setattr(main, "model_for_extraction", lambda: TestModel(custom_output_args=fake))
    admin, sam = login(c, 8), login(c, 3)
    c.post("/api/admin/funds/3/extract", headers=admin, json={"text": "We help people in Texas only. " * 3})
    assert rules(c, sam)["pending_ai_review"] is True
    c.put("/api/fund/rules", headers=sam, json={**rules(c, sam)["rules"], "pledge_value": 260})
    assert rules(c, sam)["pending_ai_review"] is False
    assert c.get("/api/admin/proposals", headers=admin).json() == []


# ---------- clinics edit their own fund ----------

def test_clinic_edits_own_fund_only(client):
    c, _ = client
    rosa = login(c, 1)  # Mesa clinic, owns fund 1
    v = c.get("/api/clinic/funds/1/rules", headers=rosa).json()
    assert v["fund_name"] == "Mesa Justice Fund" and v["rules"]["pledge_cap"] == 300 and v["monthly_limit"] == 6000
    assert c.get("/api/clinic/funds/2/rules", headers=rosa).status_code == 404   # Prairie's fund
    assert c.get("/api/clinic/funds/3/rules", headers=rosa).status_code == 404   # a partner fund
    assert c.get("/api/clinic/funds/1/rules", headers=login(c, 3)).status_code == 403  # fund staff

    r = c.put("/api/clinic/funds/1/rules", headers=rosa, json={**v["rules"], "pledge_cap": 400})
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["verified_by"] == "Rosa (Mesa front desk)"

    case = c.post("/api/clinic/cases", headers=rosa, json={"appointment_date": "2026-11-30", "procedure_cost": 1000, "contact_method": "text"}).json()
    tok = case["patient_path"].split("/")[-1]
    out = c.post(f"/api/p/{tok}/screening", json={"state": "NM", "household_size": 1, "monthly_income": 1000, "gestational_weeks": 8, "needs_travel": False}).json()
    assert next(p for p in out["pledges"] if p["fund_name"] == "Mesa Justice Fund")["amount"] == 400

    log = c.get("/api/admin/audit", headers=login(c, 8)).json()
    assert any(e["action"] == "rules_updated_by_clinic" for e in log)


def test_clinic_monthly_limit_changes_budget_check(client):
    c, _ = client
    rosa = login(c, 1)
    r = c.put("/api/clinic/funds/1/monthly-limit", headers=rosa, json={"monthly_limit": 250})
    assert r.status_code == 200 and r.json()["monthly_limit"] == 250
    assert c.put("/api/clinic/funds/2/monthly-limit", headers=rosa, json={"monthly_limit": 1}).status_code == 404
    assert c.put("/api/clinic/funds/1/monthly-limit", headers=rosa, json={"monthly_limit": -5}).status_code == 422

    case = c.post("/api/clinic/cases", headers=rosa, json={"appointment_date": "2026-11-30", "procedure_cost": 1000, "contact_method": "text"}).json()
    tok = case["patient_path"].split("/")[-1]
    c.post(f"/api/p/{tok}/screening", json={"state": "NM", "household_size": 1, "monthly_income": 1000, "gestational_weeks": 8, "needs_travel": False})
    pledge = next(p for p in c.get(f"/api/clinic/cases/{case['case_id']}", headers=rosa).json()["pledges"] if p["fund_kind"] == "clinic")
    r = c.post(f"/api/clinic/pledges/{pledge['id']}/decide", headers=rosa, json={"decision": "approve"})  # $300 > $250 limit
    assert r.status_code == 409 and "limit" in r.json()["detail"]


def test_clinic_confirm(client):
    c, _ = client
    clock.freeze(START + timedelta(days=90))
    rosa = login(c, 1)
    assert c.get("/api/clinic/funds/1/rules", headers=rosa).json()["needs_confirm"] is True
    v = c.post("/api/clinic/funds/1/rules/confirm", headers=rosa).json()
    assert v["needs_confirm"] is False and v["version"] == 1
