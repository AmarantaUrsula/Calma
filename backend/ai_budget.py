"""AI spending guard: every AI call is checked against limits first and recorded afterwards.

Limits (environment settings, with safe defaults):
  * CALMA_AI_DAILY_CALL_LIMIT   — AI calls per day for the whole site (default 300)
  * CALMA_AI_USER_HOURLY_LIMIT  — AI calls per person per hour (default 30)
Each call is also capped inside the agent (a few model requests at most, and limited input size),
so one call can't loop or balloon.

Every call is written to the ai_calls table with its real token counts and cost, so the admin can
see spending and the numbers in the project report come from real runs.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import timedelta
from typing import Any

from . import clock

# OpenAI list prices for gpt-5.6-luna, USD per million tokens (OpenAI model page, after the July 30, 2026 cut).
PRICES = {"gpt-5.6-luna": (0.20, 0.02, 1.20)}  # (input, cached input, output)


class BudgetExceeded(Exception):
    pass


def _limits() -> tuple[int, int]:
    return (int(os.environ.get("CALMA_AI_DAILY_CALL_LIMIT", "300")),
            int(os.environ.get("CALMA_AI_USER_HOURLY_LIMIT", "30")))


def ensure_table(db: sqlite3.Connection) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS ai_calls (
               id INTEGER PRIMARY KEY, at TEXT NOT NULL, user_id INTEGER, kind TEXT NOT NULL, model TEXT,
               requests INTEGER, input_tokens INTEGER, cached_tokens INTEGER, output_tokens INTEGER,
               cost_usd REAL, ok INTEGER NOT NULL DEFAULT 1)"""
    )


def check(db: sqlite3.Connection, user_id: int | None) -> None:
    """Raise BudgetExceeded before an AI call if the site or this person is over the limit."""
    ensure_table(db)
    daily, hourly = _limits()
    today = clock.today().isoformat()
    n_day = db.execute("SELECT COUNT(*) FROM ai_calls WHERE substr(at, 1, 10) = ?", (today,)).fetchone()[0]
    if n_day >= daily:
        raise BudgetExceeded(f"The daily limit of {daily} AI requests for this site has been reached. Try again tomorrow, "
                             "or use the manual controls.")
    if user_id is not None:
        since = (clock.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        n_hour = db.execute("SELECT COUNT(*) FROM ai_calls WHERE user_id = ? AND at >= ?", (user_id, since)).fetchone()[0]
        if n_hour >= hourly:
            raise BudgetExceeded(f"You've made {hourly} AI requests in the last hour, the limit per person. "
                                 "Please wait a bit, or use the manual controls.")


def cost_of(model: str, input_tokens: int, cached: int, output: int) -> float:
    p_in, p_cached, p_out = PRICES.get(model, PRICES["gpt-5.6-luna"])
    return ((input_tokens - cached) * p_in + cached * p_cached + output * p_out) / 1_000_000


def record(db: sqlite3.Connection, user_id: int | None, kind: str, model: str, usage: Any, ok: bool = True) -> None:
    ensure_table(db)
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    cached = int(getattr(usage, "cache_read_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    reqs = int(getattr(usage, "requests", 0) or 0)
    db.execute(
        """INSERT INTO ai_calls (at, user_id, kind, model, requests, input_tokens, cached_tokens, output_tokens, cost_usd, ok)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (clock.now_iso(), user_id, kind, model, reqs, inp, cached, out, cost_of(model, inp, cached, out), int(ok)),
    )


def summary(db: sqlite3.Connection) -> dict:
    ensure_table(db)
    def agg(where: str, params: tuple) -> dict:
        r = db.execute(
            f"""SELECT COUNT(*), COALESCE(SUM(input_tokens),0), COALESCE(SUM(cached_tokens),0),
                       COALESCE(SUM(output_tokens),0), COALESCE(SUM(cost_usd),0) FROM ai_calls WHERE {where}""", params
        ).fetchone()
        return {"calls": r[0], "input_tokens": r[1], "cached_tokens": r[2], "output_tokens": r[3], "cost_usd": round(r[4], 4)}
    today = clock.today().isoformat()
    by_kind = [dict(zip(("kind", "calls", "avg_input", "avg_cached", "avg_output", "avg_cost"), r)) for r in db.execute(
        """SELECT kind, COUNT(*), ROUND(AVG(input_tokens)), ROUND(AVG(cached_tokens)), ROUND(AVG(output_tokens)),
                  AVG(cost_usd) FROM ai_calls GROUP BY kind ORDER BY kind""").fetchall()]
    daily, hourly = _limits()
    return {"today": agg("substr(at, 1, 10) = ?", (today,)), "month": agg("substr(at, 1, 7) = ?", (today[:7],)),
            "all_time": agg("1 = 1", ()), "by_kind": by_kind,
            "limits": {"daily_calls": daily, "per_user_hourly": hourly}}
