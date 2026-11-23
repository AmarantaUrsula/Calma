"""Deterministic matching engine.

The AI never decides who gets money. This module is plain rules: the same
answers always give the same result, and every match carries the reasons it
matched so staff can check it.

Two kinds of help:
  * procedure  — money toward the clinic bill. The clinic's own funds go first,
                 then every eligible partner fund. Together they never exceed the
                 procedure cost.
  * practical  — travel, gas, lodging, meals, childcare. Paid to or arranged for the
                 patient, separate from the clinic bill, computed from the fund's rates.

Eligibility can depend on where the patient lives (residence) or where the abortion
happens (care = the clinic's state). These are *suggestions*: a person at the clinic or
fund approves each one manually.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 2025 HHS poverty guidelines, 48 contiguous states + DC (annual dollars).
# Alaska and Hawaii have higher guidelines; not modelled in the demo.
FPL_BASE = 15_650
FPL_PER_EXTRA_PERSON = 5_500


def fpl_annual(household_size: int) -> int:
    n = max(1, household_size)
    return FPL_BASE + FPL_PER_EXTRA_PERSON * (n - 1)


def income_fpl_pct(monthly_income: int, household_size: int) -> int:
    return round(monthly_income * 12 * 100 / fpl_annual(household_size))


@dataclass(frozen=True)
class Screening:
    state: str
    household_size: int
    monthly_income: int
    gestational_weeks: int | None  # None = patient not sure
    needs_travel: bool
    age: int | None = None
    care_state: str | None = None          # the clinic's state
    travel_miles: int | None = None        # one way
    nights_away: int | None = None
    meal_days: int | None = None
    childcare_days: int | None = None
    insurance_coverage: str | None = None  # 'yes' | 'no' | 'unsure' | None (not asked)
    unhoused: bool | None = None
    judicial_bypass: bool | None = None


@dataclass(frozen=True)
class FundRule:
    fund_id: int
    fund_name: str
    kind: str  # 'clinic' | 'independent'
    criteria_id: int
    states: tuple[str, ...]
    income_max_fpl_pct: int | None
    gest_min_weeks: int | None
    gest_max_weeks: int | None
    requires_travel: bool
    max_age: int | None
    pledge_kind: str  # 'fixed' | 'percent' (procedure funds)
    pledge_value: int  # procedure: dollars or percent; practical: flat dollars added to the rates (may be 0)
    pledge_cap: int | None
    state_basis: str = "residence"  # 'residence' | 'care'
    support_type: str = "procedure"  # 'procedure' | 'practical'
    rate_per_mile_cents: int | None = None
    rate_per_night: int | None = None
    rate_per_meal_day: int | None = None
    rate_per_childcare_day: int | None = None
    no_insurance_only: bool = False
    extra_questions: tuple[str, ...] = ()


@dataclass
class Match:
    fund_id: int
    fund_name: str
    kind: str
    criteria_id: int
    suggested_amount: int
    reasons: list[str] = field(default_factory=list)
    category: str = "procedure"


@dataclass
class Skip:
    fund_id: int
    fund_name: str
    reasons: list[str]


@dataclass
class MatchResult:
    income_fpl_pct: int
    matches: list[Match]
    skipped: list[Skip]

    @property
    def total_suggested(self) -> int:
        return sum(m.suggested_amount for m in self.matches if m.category == "procedure")

    @property
    def practical_suggested(self) -> int:
        return sum(m.suggested_amount for m in self.matches if m.category == "practical")


def check_rule(s: Screening, r: FundRule, pct: int) -> tuple[bool, list[str]]:
    """Return (eligible, reasons). Reasons explain a match, or why it failed."""
    ok: list[str] = []
    fail: list[str] = []

    if r.state_basis == "care":
        where, verb = s.care_state, "Getting care in"
        served = "care in"
    else:
        where, verb = s.state, "Lives in"
        served = "residents of"
    if "*" in r.states:
        ok.append("Serves patients from any state" if r.state_basis == "residence" else "Covers care in any state")
    elif where and where in r.states:
        ok.append(f"{verb} {where} (fund covers {served} {', '.join(r.states)})")
    else:
        fail.append(f"{verb} {where or 'unknown state'}; fund covers only {served} {', '.join(r.states)}")

    if r.income_max_fpl_pct is not None:
        if pct <= r.income_max_fpl_pct:
            ok.append(f"Income is {pct}% of poverty line (limit {r.income_max_fpl_pct}%)")
        else:
            fail.append(f"Income is {pct}% of poverty line; limit is {r.income_max_fpl_pct}%")

    if r.gest_min_weeks is not None or r.gest_max_weeks is not None:
        lo, hi = r.gest_min_weeks, r.gest_max_weeks
        rng = f"{lo or 0}–{hi if hi is not None else 'any'} weeks"
        if s.gestational_weeks is None:
            fail.append(f"Weeks of pregnancy not known; fund covers {rng}")
        elif (lo is None or s.gestational_weeks >= lo) and (hi is None or s.gestational_weeks <= hi):
            ok.append(f"{s.gestational_weeks} weeks pregnant at the visit (fund covers {rng})")
        else:
            fail.append(f"{s.gestational_weeks} weeks pregnant at the visit; fund covers {rng}")

    if r.requires_travel or r.support_type == "practical":
        if s.needs_travel:
            ok.append("Needs to travel for care")
        else:
            fail.append("Fund helps patients who must travel; patient does not")

    if r.max_age is not None:
        if s.age is not None and s.age <= r.max_age:
            ok.append(f"Age {s.age} (fund serves age {r.max_age} and under)")
        else:
            fail.append(f"Fund serves age {r.max_age} and under")

    if r.no_insurance_only:
        if s.insurance_coverage == "yes":
            fail.append("Has insurance that covers abortion; fund helps only people without coverage")
        elif s.insurance_coverage == "no":
            ok.append("No insurance that covers abortion")
        else:
            ok.append("Not sure about insurance coverage (fund helps people without coverage — check before approving)")

    return (not fail, ok if not fail else fail)


def pledge_amount(r: FundRule, procedure_cost: int) -> int:
    if r.pledge_kind == "fixed":
        amount = r.pledge_value
    else:
        amount = procedure_cost * r.pledge_value // 100
        if r.pledge_cap is not None:
            amount = min(amount, r.pledge_cap)
    return max(0, amount)


def practical_amount(r: FundRule, s: Screening) -> tuple[int, str]:
    """Flat amount plus the fund's rates for the patient's travel needs, up to the cap."""
    parts: list[str] = []
    total = 0
    if r.pledge_value:
        total += r.pledge_value
        parts.append(f"${r.pledge_value} flat")
    if r.rate_per_mile_cents and s.travel_miles:
        miles = s.travel_miles * 2
        amt = round(miles * r.rate_per_mile_cents / 100)
        total += amt
        parts.append(f"{miles} round-trip miles × ${r.rate_per_mile_cents / 100:.2f} = ${amt}")
    for qty, rate, label in (
        (s.nights_away, r.rate_per_night, "night"),
        (s.meal_days, r.rate_per_meal_day, "day of meals"),
        (s.childcare_days, r.rate_per_childcare_day, "day of dependent care"),
    ):
        if rate and qty:
            total += qty * rate
            parts.append(f"{qty} {label}{'s' if qty > 1 and label == 'night' else ''} × ${rate} = ${qty * rate}")
    capped = min(total, r.pledge_cap) if r.pledge_cap is not None else total
    note = "; ".join(parts) or "no travel costs reported"
    if r.pledge_cap is not None and total > r.pledge_cap:
        note += f" (capped at ${r.pledge_cap})"
    return capped, note


def match(screening: Screening, procedure_cost: int, rules: list[FundRule]) -> MatchResult:
    pct = income_fpl_pct(screening.monthly_income, screening.household_size)
    matches: list[Match] = []
    skipped: list[Skip] = []
    remaining = procedure_cost

    # Procedure help: clinic funds first, then partner funds (stable by fund id). Practical help last.
    ordered = sorted(rules, key=lambda r: (r.support_type == "practical", r.kind != "clinic", r.fund_id))
    for r in ordered:
        eligible, reasons = check_rule(screening, r, pct)
        if not eligible:
            skipped.append(Skip(r.fund_id, r.fund_name, reasons))
            continue
        if r.support_type == "practical":
            amount, note = practical_amount(r, screening)
            if amount <= 0:
                skipped.append(Skip(r.fund_id, r.fund_name, ["Eligible, but no travel, lodging, meal or childcare costs were reported"]))
                continue
            reasons.append(f"Suggested travel/practical help: {note}")
            matches.append(Match(r.fund_id, r.fund_name, r.kind, r.criteria_id, amount, reasons, "practical"))
            continue
        amount = min(pledge_amount(r, procedure_cost), remaining)
        if amount <= 0:
            skipped.append(Skip(r.fund_id, r.fund_name, ["Procedure cost already covered by other pledges"]))
            continue
        if r.pledge_kind == "percent":
            cap = f", up to ${r.pledge_cap}" if r.pledge_cap is not None else ""
            reasons.append(f"Suggested: {r.pledge_value}% of ${procedure_cost}{cap}")
        else:
            reasons.append(f"Suggested: fixed pledge of ${r.pledge_value}")
        matches.append(Match(r.fund_id, r.fund_name, r.kind, r.criteria_id, amount, reasons, "procedure"))
        remaining -= amount

    return MatchResult(pct, matches, skipped)
