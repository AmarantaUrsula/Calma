"""Scheduled website check: text extraction, safety checks, change detection (fake model, no network)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from backend import clock, website_check
from backend.db import connect
from backend.seed import demo_credentials, seed

# What the fake AI "reads" from the demo Desert Bloom page (matches the seeded rules).
SAME = {
    "summary": "Helps TX, NM and AZ residents.",
    "states": {"stated": True, "value": ["TX", "NM", "AZ"], "quote": "helps people who live in Texas, New Mexico, or Arizona"},
    "income_max_fpl_pct": {"stated": True, "value": 300, "quote": "at or below 300% of the federal poverty level"},
    "gest_min_weeks": {"stated": False}, "gest_max_weeks": {"stated": False},
    "requires_travel": {"stated": False}, "max_age": {"stated": False},
    "pledge": {"stated": True, "kind": "fixed", "value": 250, "quote": "We pledge a fixed amount of $250 toward your procedure"},
    "other_requirements": [],
}
CHANGED = {**SAME, "pledge": {"stated": True, "kind": "fixed", "value": 275, "quote": "We pledge a fixed amount of $275 toward your procedure"}}


def test_html_to_text_drops_scripts_and_keeps_structure():
    t = website_check.html_to_text("<html><script>var x=1</script><style>p{}</style><h1>Hi</h1><p>Line &amp; one</p><li>two</li></html>")
    assert t == "Hi\nLine & one\ntwo"


def test_hash_ignores_spacing_and_case():
    assert website_check.content_hash("A  b\nC") == website_check.content_hash("a b c")


@pytest.mark.parametrize("url", ["ftp://x.org/a", "file:///etc/passwd", "javascript:alert(1)", "demo://../x"])
def test_bad_urls_rejected(url):
    with pytest.raises(website_check.CheckError):
        website_check.validate_url(url)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.5", "169.254.169.254"])
def test_private_addresses_refused(host, monkeypatch):
    monkeypatch.delenv("CALMA_ALLOW_PRIVATE_FETCH", raising=False)
    with pytest.raises(website_check.CheckError):
        asyncio.run(website_check.fetch_text(f"http://{host}/rules"))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "w.db"
    monkeypatch.setenv("CALMA_DB", str(db))
    monkeypatch.setattr(website_check, "DEMO_DIR", tmp_path)
    page = tmp_path / "desert-bloom.html"
    page.write_text((website_check.Path(__file__).resolve().parents[2] / "data/demo_pages/desert-bloom.html").read_text())
    conn = connect(db)
    seed(conn)
    clock.freeze(datetime(2026, 11, 22, 15, tzinfo=timezone.utc))
    yield conn, page
    conn.close()
    clock.freeze(None)


def run_one(conn, fake, fund_id=3):
    return asyncio.run(website_check.check_fund(conn, fund_id, TestModel(custom_output_args=fake)))


def test_first_check_matching_rules_is_quiet(env):
    conn, _ = env
    r = run_one(conn, SAME)
    assert r.status == "rules_same"
    assert conn.execute("SELECT COUNT(*) FROM fund_criteria WHERE status='proposed'").fetchone()[0] == 0


def test_unchanged_page_skips_ai(env):
    conn, _ = env
    run_one(conn, SAME)

    class Boom(TestModel):
        async def request(self, *a, **k):
            raise AssertionError("AI should not be called for an unchanged page")
    r = asyncio.run(website_check.check_fund(conn, 3, Boom()))
    assert r.status == "unchanged"


def test_changed_page_creates_proposal_then_waits(env):
    conn, page = env
    run_one(conn, SAME)
    page.write_text(page.read_text().replace("$250", "$275"))
    r = run_one(conn, CHANGED)
    assert r.status == "proposal_created" and "pledge_value" in r.note
    row = conn.execute("SELECT status, pledge_value, source_url FROM fund_criteria WHERE id = ?", (r.criteria_id,)).fetchone()
    assert tuple(row) == ("proposed", 275, "demo://desert-bloom")
    # live rules untouched
    assert conn.execute("SELECT pledge_value FROM fund_criteria WHERE fund_id=3 AND status='approved'").fetchone()[0] == 250
    # page changes again while the suggestion waits: don't overwrite it
    page.write_text(page.read_text().replace("$275", "$300"))
    assert run_one(conn, CHANGED).status == "skipped_pending_review"


def test_ai_failure_is_recorded_and_retried(env):
    conn, _ = env

    class Fail(TestModel):
        async def request(self, *a, **k):
            raise RuntimeError("model down")
    r = asyncio.run(website_check.check_fund(conn, 3, Fail()))
    assert r.status == "error" and "retry" in r.note
    assert run_one(conn, SAME).status == "rules_same"  # no baseline was saved, so it tries again


def test_due_funds_respect_interval(env):
    conn, _ = env
    assert website_check.due_fund_ids(conn) == [3, 4, 5, 6, 7, 8, 10, 11, 12, 13]  # incl. real reference funds
    run_one(conn, SAME)
    assert 3 not in website_check.due_fund_ids(conn)
    clock.freeze(datetime(2026, 11, 22, 15, tzinfo=timezone.utc) + timedelta(days=61))
    assert 3 in website_check.due_fund_ids(conn)


def test_admin_routes(env, monkeypatch):
    conn, _ = env
    from backend import main
    monkeypatch.setattr(main, "model_for_extraction", lambda: TestModel(custom_output_args=SAME))
    c = TestClient(main.app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json=demo_credentials(8)).json()["token"]}
    assert c.post("/api/admin/funds/3/check-now", headers=c.headers | {"Authorization": "Bearer " + c.post("/api/auth/login", json=demo_credentials(1)).json()["token"]}).status_code == 403
    r = c.post("/api/admin/funds/3/check-now", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "rules_same"
    assert c.put("/api/admin/funds/3/policy-url", headers=h, json={"policy_url": "file:///etc/passwd"}).status_code == 422
    assert c.put("/api/admin/funds/3/policy-url", headers=h, json={"policy_url": "https://example.org/help"}).status_code == 200
    data = c.get("/api/admin/website-checks", headers=h).json()
    assert data["interval_days"] == 60 and data["checks"][0]["status"] == "rules_same"
    assert next(f for f in data["funds"] if f["id"] == 3)["policy_url"] == "https://example.org/help"


def test_real_reference_funds_are_tracked_but_never_matched(env, monkeypatch):
    conn, _ = env
    from backend import main
    c = TestClient(main.app)
    admin = {"Authorization": "Bearer " + c.post("/api/auth/login", json=demo_credentials(8)).json()["token"]}
    funds = {f["id"]: f for f in c.get("/api/admin/funds", headers=admin).json()}
    assert funds[10]["name"] == "Carolina Abortion Fund" and funds[10]["reference_only"] and funds[10]["version"] is None
    checks = {f["id"]: f for f in c.get("/api/admin/website-checks", headers=admin).json()["funds"]}
    assert checks[10]["policy_url"].startswith("https://www.carolinaabortionfund.org/")
    # not offered at sign-up, not matched with demo patients
    orgs = c.get("/api/auth/organizations").json()
    assert all(f["id"] < 10 for f in orgs["funds"])
    assert c.post("/api/auth/signup", json={"first_name": "A", "last_name": "B", "email": "a@example.org",
                  "password": "long enough phrase", "confirm_password": "long enough phrase",
                  "role": "fund", "org_id": 10}).status_code == 422
    # first check of a real page (fake model here): the suggestion goes to review, nothing goes live
    real = {"summary": "NC/SC", "states": {"stated": True, "value": ["NC", "SC"], "quote": "North and South Carolina"},
            "income_max_fpl_pct": {"stated": True, "no_limit": True, "quote": "no income requirements"},
            "gest_min_weeks": {"stated": False}, "gest_max_weeks": {"stated": False}, "requires_travel": {"stated": False},
            "max_age": {"stated": False}, "pledge": {"stated": False}, "other_requirements": []}

    async def fake_fetch(url):
        return "We fund callers in North and South Carolina. We have no income requirements. " * 5
    monkeypatch.setattr(website_check, "fetch_text", fake_fetch)
    r = asyncio.run(website_check.check_fund(conn, 10, TestModel(custom_output_args=real)))
    assert r.status == "proposal_created", r.note
    assert conn.execute("SELECT COUNT(*) FROM fund_criteria WHERE fund_id = 10 AND status = 'approved'").fetchone()[0] == 0
