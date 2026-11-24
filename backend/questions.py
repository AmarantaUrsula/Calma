"""Intake question catalog: which questions a patient sees, and why.

Core questions are always asked. Optional questions are asked when:
  * a fund the patient could match needs the answer for its rules (derived automatically), or
  * the clinic or one of its partner funds turned the question on ("also ask").

Every optional question can be skipped by the patient. State of care is never asked:
it is the clinic's state, which Calma already knows.
"""

from __future__ import annotations

import json
import sqlite3

from .matching import FundRule

# id -> (group, staff-facing label)
CATALOG: dict[str, tuple[str, str]] = {
    "state": ("core", "State where you live"),
    "household": ("core", "Household size"),
    "income": ("core", "Household income (monthly or yearly)"),
    "pregnancy": ("core", "First day of last period (or weeks pregnant)"),
    "travel": ("core", "Need to travel far for care?"),
    "age": ("optional", "Age"),
    "travel_miles": ("optional", "Travel miles (one way)"),
    "nights_away": ("optional", "Nights away from home"),
    "meal_days": ("optional", "Days needing meals while traveling"),
    "childcare_days": ("optional", "Days needing dependent care while traveling"),
    "insurance": ("optional", "Medicaid or other insurance that covers abortion?"),
    "medicaid": ("optional", "Has Medicaid?"),
    "unhoused": ("optional", "Currently unhoused?"),
    "judicial_bypass": ("optional", "Minor seeking a judicial bypass?"),
    "contact": ("optional", "Contact details: name, phone, email, how to reach you"),
}
ORDER = list(CATALOG)
CORE = [q for q, (g, _) in CATALOG.items() if g == "core"]
OPTIONAL = [q for q, (g, _) in CATALOG.items() if g == "optional"]
# Funds can ask any optional question except contact details (clinic-only, never shared with funds).
FUND_ASKABLE = [q for q in OPTIONAL if q != "contact"]
TRAVEL_DETAILS = {"travel_miles", "nights_away", "meal_days", "childcare_days"}


def derived(rule: FundRule) -> set[str]:
    """Questions a fund needs answered for automatic matching."""
    need: set[str] = set()
    if rule.max_age is not None:
        need.add("age")
    if rule.no_insurance_only:
        need.add("insurance")
    if rule.exclude_medicaid_covered:
        need.add("medicaid")
    for cat in rule.income_waiver_categories:  # exceptions to the income limit need their question
        if cat in ("unhoused", "judicial_bypass"):
            need.add(cat)
    if rule.support_type == "practical":
        if rule.rate_per_mile_cents:
            need.add("travel_miles")
        if rule.rate_per_night:
            need.add("nights_away")
        if rule.rate_per_meal_day:
            need.add("meal_days")
        if rule.rate_per_childcare_day:
            need.add("childcare_days")
    return need


def asked_by_fund(rule: FundRule) -> set[str]:
    return derived(rule) | {q for q in rule.extra_questions if q in FUND_ASKABLE}


def clinic_extras(db: sqlite3.Connection, clinic_id: int) -> list[str]:
    r = db.execute("SELECT extra_questions FROM clinics WHERE id = ?", (clinic_id,)).fetchone()
    return [q for q in json.loads(r[0] or "[]") if q in OPTIONAL] if r else []


def plan(db: sqlite3.Connection, clinic_id: int, rules: list[FundRule]) -> tuple[list[str], dict[str, list[str]]]:
    """Return (ordered question ids, {question id: [who asked for it]}) for this clinic's patients."""
    clinic_name = db.execute("SELECT name FROM clinics WHERE id = ?", (clinic_id,)).fetchone()[0]
    why: dict[str, list[str]] = {q: ["Always asked"] for q in CORE}
    for q in clinic_extras(db, clinic_id):
        why.setdefault(q, []).append(f"{clinic_name} (clinic)")
    for r in rules:
        for q in sorted(derived(r)):
            why.setdefault(q, []).append(f"{r.fund_name} (needed for its rules)")
        for q in r.extra_questions:
            if q in FUND_ASKABLE and q not in derived(r):
                why.setdefault(q, []).append(f"{r.fund_name} (asked to see it)")
    return [q for q in ORDER if q in why], why
