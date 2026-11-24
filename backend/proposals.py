"""Fund rule versions: reading, writing, and AI-proposed updates.

Shared by the admin "paste text" screen, the scheduled website check, the fund and clinic
rule editors, and the seed script, so the list of rule columns lives in one place.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import llm, rules_extractor
from .db import audit
from .rules_extractor import RULE_DEFAULTS, RULE_FIELDS

_JSON = {"states", "extra_questions", "income_waiver_categories"}
_BOOL = {"requires_travel", "no_insurance_only", "exclude_medicaid_covered"}


def row_to_rules(r: sqlite3.Row | dict) -> dict:
    d = dict(r)
    out = {}
    for k in RULE_FIELDS:
        v = d.get(k, RULE_DEFAULTS.get(k))
        if k in _JSON:
            v = json.loads(v) if isinstance(v, str) else (v or [])
            if k == "states":
                v = sorted(v)
        elif k in _BOOL:
            v = bool(v)
        out[k] = v
    return out


# Columns that can't be empty in the database. A suggestion for a brand-new fund may not know
# these yet (e.g. a real fund that doesn't publish a pledge amount): store a placeholder. The
# admin still has to enter a real pledge amount before approving (approval requires $1 or more).
_PLACEHOLDERS = {"pledge_kind": "fixed", "pledge_value": 0, "state_basis": "residence", "support_type": "procedure"}


def _db_values(values: dict) -> list:
    out = []
    for k in RULE_FIELDS:
        v = values.get(k, RULE_DEFAULTS.get(k))
        if v is None and k in _PLACEHOLDERS:
            v = _PLACEHOLDERS[k]
        if k in _JSON:
            v = json.dumps(v or [])
        elif k in _BOOL:
            v = int(bool(v))
        out.append(v)
    return out


def insert_rule(db: sqlite3.Connection, fund_id: int, version: int, status: str, values: dict, **meta: Any) -> int:
    """meta: source_url, last_verified_at, verified_by, evidence (dict), proposed_by."""
    if "evidence" in meta and meta["evidence"] is not None:
        meta["evidence"] = json.dumps(meta["evidence"])
    cols = ["fund_id", "version", "status", *RULE_FIELDS, *meta.keys()]
    vals = [fund_id, version, status, *_db_values(values), *meta.values()]
    cur = db.execute(
        f"INSERT INTO fund_criteria ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals
    )
    return cur.lastrowid


def update_rule(db: sqlite3.Connection, criteria_id: int, values: dict, **meta: Any) -> None:
    cols = [*RULE_FIELDS, *meta.keys()]
    db.execute(
        f"UPDATE fund_criteria SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?",
        [*_db_values(values), *meta.values(), criteria_id],
    )


def next_version(db: sqlite3.Connection, fund_id: int) -> int:
    return db.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM fund_criteria WHERE fund_id = ?", (fund_id,)).fetchone()[0]


def current_rule_dict(db: sqlite3.Connection, fund_id: int) -> dict:
    r = db.execute(
        """SELECT * FROM fund_criteria WHERE fund_id = ? AND status = 'approved'
           ORDER BY version DESC LIMIT 1""",
        (fund_id,),
    ).fetchone()
    if not r:
        return {k: RULE_DEFAULTS.get(k) for k in RULE_FIELDS}
    return {**row_to_rules(r), "id": r["id"], "version": r["version"], "last_verified_at": r["last_verified_at"],
            "verified_by": r["verified_by"]}


async def create_proposal(db: sqlite3.Connection, fund_id: int, text: str, source_url: str | None,
                          actor: str, model: Any, user_id: int | None = None) -> int:
    """Run the extractor and store a 'proposed' rule version. Returns its id.

    Raises whatever the model raises; the caller decides how to report it.
    Nothing here touches the live (approved) rules.
    """
    from . import ai_budget

    ai_budget.check(db, user_id)  # spending limits before any AI call
    ex = await rules_extractor.extract(
        text, model, on_usage=lambda u: ai_budget.record(db, user_id, "rules_extractor", llm.model_name(), u))
    current = current_rule_dict(db, fund_id)
    proposed, evidence = rules_extractor.build_proposal(current, ex, text)
    # One open proposal per fund: a new one replaces the old.
    db.execute("DELETE FROM fund_criteria WHERE fund_id = ? AND status = 'proposed'", (fund_id,))
    criteria_id = insert_rule(db, fund_id, next_version(db, fund_id), "proposed", proposed,
                              source_url=source_url, evidence=evidence,
                              proposed_by=f"AI ({llm.model_name()}) for {actor}")
    audit(db, actor, "rules_proposed", detail={"fund_id": fund_id, "criteria_id": criteria_id})
    return criteria_id
