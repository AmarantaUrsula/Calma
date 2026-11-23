"""Reports: scope by organization, grouping math, Excel export, and the Report Builder agent."""

import io
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pydantic_ai.models.test import TestModel

from backend import clock
from backend.db import connect
from backend.report_agent import ReportSpec, clean_spec
from backend.seed import add_history, demo_credentials, seed

RANGE = {"start": "2026-01-01", "end": "2026-11-22"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "r.db"
    monkeypatch.setenv("CALMA_DB", str(db))
    clock.freeze(datetime(2026, 11, 22, 15, tzinfo=timezone.utc))
    conn = connect(db)
    seed(conn)
    add_history(conn, n=60)
    conn.close()
    from backend import main
    yield TestClient(main.app), main, db
    clock.freeze(None)


def h(c, uid):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json=demo_credentials(uid)).json()["token"]}


def run(c, headers, **kw):
    r = c.post("/api/reports/run", headers=headers, json={**RANGE, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_totals_add_up_and_scope_is_per_organization(client):
    c, _, db = client
    admin, rosa, dana, sam = h(c, 8), h(c, 1), h(c, 2), h(c, 3)
    everything = run(c, admin, group_by=["clinic"])
    by_clinic = {g["keys"][0]: g["amount"] for g in everything["groups"]}
    assert sum(by_clinic.values()) == everything["total_amount"] > 0
    assert run(c, rosa)["total_amount"] == by_clinic["Mesa Women's Health (demo)"]
    assert run(c, dana)["total_amount"] == by_clinic["Prairie Family Clinic (demo)"]
    # a fund sees only its own pledges
    sam_rep = run(c, sam, group_by=["clinic"])
    by_fund = {g["keys"][0]: g["amount"] for g in run(c, admin, group_by=["fund"])["groups"]}
    assert sam_rep["total_amount"] == by_fund["Desert Bloom Fund"]
    import sqlite3
    direct = sqlite3.connect(db).execute(
        "SELECT SUM(approved_amount) FROM pledges WHERE status='paid' AND fund_id=3 AND substr(paid_at,1,10) BETWEEN ? AND ?",
        (RANGE["start"], RANGE["end"])).fetchone()[0]
    assert sam_rep["total_amount"] == direct


def test_measures_dates_and_three_criteria(client):
    c, _, _ = client
    admin = h(c, 8)
    paid = run(c, admin)["total_amount"]
    pledged = run(c, admin, measure="pledged", date_basis="approved")["total_amount"]
    assert pledged >= paid  # pledged includes approved-but-not-paid
    narrow = run(c, admin, start="2026-11-01", end="2026-11-22")["total_amount"]
    assert 0 <= narrow < paid
    three = run(c, admin, group_by=["month", "help_type", "home_state"])
    assert all(len(g["keys"]) == 3 for g in three["groups"]) and three["labels"][1] == "Type of help"
    months = [g["keys"][0] for g in three["groups"]]
    assert months == sorted(months)  # time comes out in order
    assert sum(g["amount"] for g in three["groups"]) == paid
    assert any(g["small"] for g in three["groups"])  # tiny groups are flagged


def test_role_limits_and_bad_requests(client):
    c, _, _ = client
    sam = h(c, 3)
    assert c.post("/api/reports/run", headers=sam, json={**RANGE, "group_by": ["age_band"]}).status_code == 422
    assert c.post("/api/reports/run", headers=sam, json={**RANGE, "group_by": ["month", "month"]}).status_code == 422
    assert c.post("/api/reports/run", headers=sam, json={"start": "2026-05-01", "end": "2026-01-01"}).status_code == 422
    assert c.post("/api/reports/run", json=RANGE).status_code == 401
    dims = {d["id"] for d in c.get("/api/reports/options", headers=sam).json()["dimensions"]}
    assert "age_band" not in dims and "clinic" in dims and "fund" not in dims


def test_excel_export_has_report_and_deidentified_data(client):
    c, _, _ = client
    sam, admin = h(c, 3), h(c, 8)
    r = c.post("/api/reports/export", headers=sam, json={**RANGE, "group_by": ["month"]})
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Report", "Data"]
    headers = [cell.value for cell in wb["Data"][1]]
    assert "Case" in headers and "Amount ($)" in headers and "Age" not in headers  # funds don't get age
    text = " ".join(str(v) for row in wb["Data"].iter_rows(values_only=True) for v in row if v)
    assert "@" not in text and "income" not in text.lower().replace("income (% of poverty line)", "")
    log = c.get("/api/admin/audit", headers=admin).json()
    assert any(e["action"] == "report_downloaded" for e in log)


def test_clean_spec_enforces_rules():
    spec = ReportSpec(measure="disbursed", date_basis="paid", start=date(2026, 6, 1), end=date(2026, 1, 1),
                      group_by=["age_band", "month", "clinic", "help_type", "month"], view="pie", title="x")
    s, notes = clean_spec(spec, "fund")
    assert s.group_by == ["month", "clinic", "help_type"] and s.view == "table"
    assert s.start < s.end and any("not available" in n for n in notes)


def test_report_builder_turns_words_into_a_report(client, monkeypatch):
    c, main, _ = client
    fake = {"measure": "disbursed", "date_basis": "paid", "start": "2026-01-01", "end": "2026-11-22",
            "group_by": ["fund"], "view": "pie", "chart_value": "amount", "title": "Paid out by fund this year", "note": ""}
    monkeypatch.setattr(main, "model_for_reports", lambda: TestModel(custom_output_args=fake))
    admin = h(c, 8)
    r = c.post("/api/reports/ask", headers=admin, json={"request": "pie chart of money paid out by fund this year"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["spec"]["view"] == "pie" and d["spec"]["group_by"] == ["fund"]
    assert d["result"]["total_amount"] == run(c, admin, group_by=["fund"])["total_amount"]  # same engine, same numbers
    # a fund asking for something it can't see gets it dropped, with a note
    fake2 = {**fake, "group_by": ["age_band"], "view": "bar"}
    monkeypatch.setattr(main, "model_for_reports", lambda: TestModel(custom_output_args=fake2))
    d = c.post("/api/reports/ask", headers=h(c, 3), json={"request": "paid out by age"}).json()
    assert d["spec"]["group_by"] == [] and d["spec"]["view"] == "table" and d["notes"]
