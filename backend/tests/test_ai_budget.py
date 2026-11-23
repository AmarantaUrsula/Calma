"""AI spending guard: per-person hourly limit, site-wide daily cap, and real token records."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from backend import clock
from backend.db import connect
from backend.seed import demo_credentials, seed

SPEC = {"measure": "disbursed", "date_basis": "paid", "start": "2026-01-01", "end": "2026-11-22",
        "group_by": ["fund"], "view": "bar", "chart_value": "amount", "title": "t", "note": ""}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CALMA_DB", str(tmp_path / "b.db"))
    clock.freeze(datetime(2026, 11, 22, 15, tzinfo=timezone.utc))
    conn = connect(tmp_path / "b.db")
    seed(conn)
    conn.close()
    from backend import main
    monkeypatch.setattr(main, "model_for_reports", lambda: TestModel(custom_output_args=SPEC))
    yield TestClient(main.app)
    clock.freeze(None)


def h(c, uid):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json=demo_credentials(uid)).json()["token"]}


def ask(c, headers):
    return c.post("/api/reports/ask", headers=headers, json={"request": "paid out by fund"})


def test_per_person_hourly_limit(client, monkeypatch):
    monkeypatch.setenv("CALMA_AI_USER_HOURLY_LIMIT", "3")
    rosa, dana = h(client, 1), h(client, 2)
    assert [ask(client, rosa).status_code for _ in range(4)] == [200, 200, 200, 429]
    assert "limit per person" in ask(client, rosa).json()["detail"]
    assert ask(client, dana).status_code == 200  # other people aren't affected
    clock.freeze(datetime(2026, 11, 22, 16, 5, tzinfo=timezone.utc))  # an hour later
    rosa = h(client, 1)
    assert ask(client, rosa).status_code == 200


def test_site_wide_daily_cap(client, monkeypatch):
    monkeypatch.setenv("CALMA_AI_DAILY_CALL_LIMIT", "2")
    rosa, dana = h(client, 1), h(client, 2)
    assert ask(client, rosa).status_code == 200 and ask(client, dana).status_code == 200
    r = ask(client, h(client, 8))
    assert r.status_code == 429 and "daily limit" in r.json()["detail"]


def test_every_call_is_recorded_with_tokens_and_cost(client):
    admin = h(client, 8)
    ask(client, admin)
    u = client.get("/api/admin/ai-usage", headers=admin).json()
    assert u["today"]["calls"] == 1 and u["today"]["input_tokens"] > 0 and u["today"]["output_tokens"] > 0
    assert u["by_kind"][0]["kind"] == "report_builder" and u["today"]["cost_usd"] >= 0
    assert client.get("/api/admin/ai-usage", headers=h(client, 1)).status_code == 403
