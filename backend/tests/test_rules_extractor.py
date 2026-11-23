"""Rules Extractor: proposal building, quote checking, and the approve/reject flow (fake model, no API calls)."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from backend import clock
from backend.db import connect
from backend.rules_extractor import ExtractedCriteria, build_proposal, quote_found
from backend.seed import demo_credentials, seed

POLICY = """Desert Bloom Fund helps people who live in Texas, New Mexico, Arizona, or Colorado.
You may qualify if your household income is at or below 250% of the federal poverty level.
We pledge up to $300 toward your procedure. We can help up to 22 weeks of pregnancy.
Please call our hotline to get started."""

FAKE = {
    "summary": "Helps TX, NM, AZ and CO residents with low income.",
    "states": {"stated": True, "value": ["TX", "NM", "AZ", "CO"],
               "quote": "helps people who live in Texas, New Mexico, Arizona, or Colorado"},
    "income_max_fpl_pct": {"stated": True, "value": 250,
                           "quote": "household income is at or below 250% of the federal poverty level"},
    "gest_min_weeks": {"stated": False},
    "gest_max_weeks": {"stated": True, "value": 22, "quote": "We can help up to 22 weeks of pregnancy."},
    "requires_travel": {"stated": False},
    "max_age": {"stated": False},
    "pledge": {"stated": True, "kind": "fixed", "value": 300, "quote": "We pledge up to $300 toward your procedure."},
    "other_requirements": ["Must call the hotline"],
}


def test_quote_found_ignores_case_and_spacing():
    assert quote_found("we PLEDGE up to   $300", POLICY)
    assert not quote_found("We pledge up to $500", POLICY)
    assert not quote_found(None, POLICY)


def test_build_proposal_keeps_unstated_and_flags_changes():
    current = {"states": ["AZ", "NM", "TX"], "income_max_fpl_pct": 300, "gest_min_weeks": None,
               "gest_max_weeks": None, "requires_travel": False, "max_age": None,
               "pledge_kind": "fixed", "pledge_value": 250, "pledge_cap": None}
    ex = ExtractedCriteria.model_validate(FAKE)
    proposed, ev = build_proposal(current, ex, POLICY)
    assert proposed["states"] == ["AZ", "CO", "NM", "TX"]
    assert ev["states"]["status"] == "changed" and ev["states"]["quote_verified"]
    assert proposed["income_max_fpl_pct"] == 250
    assert proposed["gest_max_weeks"] == 22
    assert ev["max_age"]["status"] == "not_stated" and proposed["max_age"] is None
    assert proposed["pledge_value"] == 300 and ev["pledge_kind"]["status"] == "same"
    assert ev["_other"]["items"] == ["Must call the hotline"]


def test_made_up_quote_is_flagged():
    bad = {**FAKE, "max_age": {"stated": True, "value": 19, "quote": "We serve youth 19 and under."}}
    _, ev = build_proposal({}, ExtractedCriteria.model_validate(bad), POLICY)
    assert ev["max_age"]["quote_verified"] is False


def test_dollar_income_needs_manual():
    odd = {**FAKE, "income_max_fpl_pct": {"stated": True, "value": None, "quote": "household income"}}
    proposed, ev = build_proposal({"income_max_fpl_pct": 300}, ExtractedCriteria.model_validate(odd), POLICY)
    assert ev["income_max_fpl_pct"]["status"] == "needs_manual"
    assert proposed["income_max_fpl_pct"] == 300  # kept until a person decides


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setenv("CALMA_DB", str(db))
    conn = connect(db)
    seed(conn)
    conn.close()
    clock.freeze(datetime(2026, 11, 22, 15, tzinfo=timezone.utc))
    from backend import main
    monkeypatch.setattr(main, "model_for_extraction", lambda: TestModel(custom_output_args=FAKE))
    yield TestClient(main.app)
    clock.freeze(None)


def login(client, uid):
    return {"Authorization": "Bearer " + client.post("/api/auth/login", json=demo_credentials(uid)).json()["token"]}


def test_extract_review_approve_changes_matching(client):
    admin = login(client, 8)
    assert client.post("/api/admin/funds/3/extract", headers=login(client, 1), json={"text": POLICY}).status_code == 403

    r = client.post("/api/admin/funds/3/extract", headers=admin, json={"text": POLICY, "source_url": "https://example.org/eligibility"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["version"] == 2 and p["proposed"]["states"] == ["AZ", "CO", "NM", "TX"]
    assert p["current"]["states"] == ["AZ", "NM", "TX"]

    # Proposal is not live yet: a CO patient doesn't match Desert Bloom.
    rosa = login(client, 1)
    def screen_co():
        c = client.post("/api/clinic/cases", headers=rosa, json={"appointment_date": "2026-11-30", "procedure_cost": 900, "contact_method": "text"}).json()
        tok = c["patient_path"].split("/")[-1]
        v = client.post(f"/api/p/{tok}/screening", json={"state": "CO", "household_size": 2, "monthly_income": 1500, "gestational_weeks": 8, "needs_travel": False}).json()
        return {x["fund_name"] for x in v["pledges"]}
    assert "Desert Bloom Fund" not in screen_co()

    # Admin edits one value (pledge $275) and approves.
    vals = {**p["proposed"], "pledge_value": 275}
    assert client.post(f"/api/admin/proposals/{p['id']}/approve", headers=admin, json=vals).status_code == 200
    assert client.get("/api/admin/proposals", headers=admin).json() == []
    assert "Desert Bloom Fund" in screen_co()
    row = next(f for f in client.get("/api/admin/funds", headers=admin).json() if f["id"] == 3)
    assert row["version"] == 2 and row["pledge_value"] == 275 and row["verified_by"] == "Admin (Calma)"
    log = client.get("/api/admin/audit", headers=admin).json()
    approved = next(e for e in log if e["action"] == "rules_approved")
    assert "pledge_value" in approved["detail"]


def test_reject_leaves_rules_alone(client):
    admin = login(client, 8)
    p = client.post("/api/admin/funds/3/extract", headers=admin, json={"text": POLICY}).json()
    assert client.post(f"/api/admin/proposals/{p['id']}/reject", headers=admin).status_code == 200
    row = next(f for f in client.get("/api/admin/funds", headers=admin).json() if f["id"] == 3)
    assert row["version"] == 1 and sorted(row["states"]) == ["AZ", "NM", "TX"]


def test_extractor_accepts_either_state_basis():
    ex = ExtractedCriteria.model_validate({**FAKE, "state_basis": {"stated": True, "value": "either",
        "quote": "helps people who live in Texas, New Mexico, Arizona, or Colorado"}})
    proposed, ev = build_proposal({"state_basis": "residence"}, ex, POLICY)
    assert proposed["state_basis"] == "either" and ev["state_basis"]["status"] == "changed"
