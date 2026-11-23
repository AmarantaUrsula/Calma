"""Staff accounts: create account, log in, admin approval, and password safety."""

import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend import auth, clock
from backend.db import connect
from backend.seed import DEMO_PASSWORD, demo_credentials, seed

NEW = {"first_name": "Jessie", "last_name": "Lewis", "email": "Jessie.Lewis@Example.org",
       "password": "quiet river morning", "confirm_password": "quiet river morning", "role": "fund", "org_id": 3}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "a.db"
    monkeypatch.setenv("CALMA_DB", str(db))
    auth._fails.clear()
    clock.freeze(datetime(2026, 11, 22, 15, tzinfo=timezone.utc))
    conn = connect(db)
    seed(conn)
    conn.close()
    from backend.main import app
    yield TestClient(app), db
    clock.freeze(None)


def login(c, email, password):
    return c.post("/api/auth/login", json={"email": email, "password": password})


def bearer(r):
    return {"Authorization": "Bearer " + r.json()["token"]}


# ---------- password hashing ----------

def test_hash_is_salted_one_way_and_verifies():
    h1, h2 = auth.hash_password("correct horse"), auth.hash_password("correct horse")
    assert h1 != h2 and h1.startswith("scrypt$") and "correct horse" not in h1
    assert auth.verify_password("correct horse", h1) and auth.verify_password("correct horse", h2)
    assert not auth.verify_password("correct horsE", h1)
    assert not auth.verify_password("x", "garbage") and not auth.verify_password("x", None)


def test_settings_travel_with_the_hash(monkeypatch):
    h = auth.hash_password("same settings please")
    monkeypatch.setattr(auth, "_N", 2048)  # even if the default changes later...
    assert auth.verify_password("same settings please", h)  # ...old hashes still verify


def test_pepper_is_required_when_set(monkeypatch):
    monkeypatch.setenv("CALMA_PASSWORD_PEPPER", "server-secret")
    h = auth.hash_password("pepper matters")
    assert auth.verify_password("pepper matters", h)
    monkeypatch.delenv("CALMA_PASSWORD_PEPPER")
    assert not auth.verify_password("pepper matters", h)  # a stolen database alone isn't enough


# ---------- log in ----------

def test_seeded_user_logs_in_and_password_never_leaves_server(env):
    c, db = env
    r = login(c, "ROSA@mesa.example.org ", DEMO_PASSWORD)  # email is case/space-insensitive
    assert r.status_code == 200 and r.json()["user"]["role"] == "clinic"
    admin = bearer(login(c, *demo_credentials(8).values()))
    for resp in (r, c.get("/api/me", headers=bearer(r)), c.get("/api/admin/users", headers=admin),
                 c.get("/api/admin/audit", headers=admin)):
        text = resp.text
        assert "password" not in text.lower() and "scrypt$" not in text and DEMO_PASSWORD not in text
    stored = sqlite3.connect(db).execute("SELECT password_hash FROM users WHERE id = 1").fetchone()[0]
    assert stored.startswith("scrypt$") and DEMO_PASSWORD not in stored


def test_wrong_password_and_unknown_email_look_the_same(env):
    c, _ = env
    a = login(c, "rosa@mesa.example.org", "wrong password here")
    b = login(c, "nobody@example.org", "wrong password here")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_lockout_after_five_misses(env):
    c, _ = env
    for _ in range(5):
        login(c, "rosa@mesa.example.org", "nope nope nope")
    assert login(c, "rosa@mesa.example.org", DEMO_PASSWORD).status_code == 429
    assert login(c, "dana@prairie.example.org", DEMO_PASSWORD).status_code == 200  # other accounts unaffected


# ---------- create account ----------

@pytest.mark.parametrize("change,msg", [
    ({"confirm_password": "quiet river evening"}, "don't match"),
    ({"password": "short", "confirm_password": "short"}, "at least 10"),
    ({"password": "password123", "confirm_password": "password123"}, "too easy"),
    ({"password": "jessie-is-great", "confirm_password": "jessie-is-great"}, "name or email"),
    ({"email": "not-an-email"}, "valid email"),
    ({"org_id": None}, "choose your fund"),
    ({"role": "clinic", "org_id": 99}, "choose your clinic"),
])
def test_signup_validation(env, change, msg):
    c, _ = env
    r = c.post("/api/auth/signup", json={**NEW, **change})
    assert r.status_code == 422 and msg in r.json()["detail"]


def test_new_account_needs_admin_approval_then_logs_in(env):
    c, db = env
    assert c.post("/api/auth/signup", json=NEW).status_code == 201
    assert c.post("/api/auth/signup", json={**NEW, "email": "jessie.lewis@example.org"}).status_code == 409  # duplicate
    row = sqlite3.connect(db).execute("SELECT status, password_hash, email FROM users WHERE email = 'jessie.lewis@example.org'").fetchone()
    assert row[0] == "pending" and row[1].startswith("scrypt$") and NEW["password"] not in row[1]

    r = login(c, "jessie.lewis@example.org", NEW["password"])
    assert r.status_code == 403 and "waiting" in r.json()["detail"]

    admin = bearer(login(c, *demo_credentials(8).values()))
    users = c.get("/api/admin/users", headers=admin).json()
    new = next(u for u in users if u["email"] == "jessie.lewis@example.org")
    assert users[0]["status"] == "pending" and new["fund_name"] == "Desert Bloom Fund"
    c.post(f"/api/admin/users/{new['id']}/approve", headers=admin)

    r = login(c, "jessie.lewis@example.org", NEW["password"])  # brand-new account works
    assert r.status_code == 200 and r.json()["user"]["fund_id"] == 3
    assert c.get("/api/fund/summary", headers=bearer(r)).json()["fund"]["name"] == "Desert Bloom Fund"


def test_admin_signup_also_needs_approval_and_reject_blocks(env):
    c, _ = env
    c.post("/api/auth/signup", json={**NEW, "email": "new.admin@example.org", "role": "admin", "org_id": None})
    r = login(c, "new.admin@example.org", NEW["password"])
    assert r.status_code == 403  # nobody can make themselves an admin
    admin = bearer(login(c, *demo_credentials(8).values()))
    uid = next(u["id"] for u in c.get("/api/admin/users", headers=admin).json() if u["email"] == "new.admin@example.org")
    c.post(f"/api/admin/users/{uid}/reject", headers=admin)
    assert login(c, "new.admin@example.org", NEW["password"]).status_code == 403


def test_disabling_signs_out_right_away(env):
    c, _ = env
    rosa = bearer(login(c, *demo_credentials(1).values()))
    admin = bearer(login(c, *demo_credentials(8).values()))
    assert c.get("/api/clinic/summary", headers=rosa).status_code == 200
    c.post("/api/admin/users/1/disable", headers=admin)
    assert c.get("/api/clinic/summary", headers=rosa).status_code == 401
    assert login(c, *demo_credentials(1).values()).status_code == 403
    c.post("/api/admin/users/1/enable", headers=admin)
    assert login(c, *demo_credentials(1).values()).status_code == 200
    assert c.post("/api/admin/users/8/disable", headers=admin).status_code == 422  # not yourself
    assert c.post("/api/admin/users/1/approve", headers=rosa).status_code == 401


def test_deployment_requires_its_own_demo_password(tmp_path, monkeypatch):
    import importlib
    from backend import seed as seed_mod
    monkeypatch.setenv("CALMA_REQUIRE_DEMO_PASSWORD", "1")
    monkeypatch.delenv("CALMA_DEMO_PASSWORD", raising=False)
    with pytest.raises(seed_mod.MissingDemoPassword):
        seed_mod.check_demo_password()
    monkeypatch.setenv("CALMA_DEMO_PASSWORD", seed_mod.LOCAL_DEMO_PASSWORD)  # the public default isn't allowed
    with pytest.raises(seed_mod.MissingDemoPassword):
        seed_mod.check_demo_password()
    monkeypatch.setenv("CALMA_DEMO_PASSWORD", "private river stones")
    mod = importlib.reload(seed_mod)
    try:
        conn = connect(tmp_path / "d.db")
        mod.seed(conn)
        h = conn.execute("SELECT password_hash FROM users WHERE id = 8").fetchone()[0]
        assert auth.verify_password("private river stones", h) and not auth.verify_password(mod.LOCAL_DEMO_PASSWORD, h)
    finally:
        monkeypatch.delenv("CALMA_DEMO_PASSWORD")
        monkeypatch.delenv("CALMA_REQUIRE_DEMO_PASSWORD")
        importlib.reload(seed_mod)
