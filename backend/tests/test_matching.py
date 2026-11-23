from backend.matching import FundRule, Screening, fpl_annual, income_fpl_pct, match


def rule(fund_id, kind="independent", **kw):
    base = dict(fund_id=fund_id, fund_name=f"Fund {fund_id}", kind=kind, criteria_id=fund_id,
                states=("*",), income_max_fpl_pct=None, gest_min_weeks=None, gest_max_weeks=None,
                requires_travel=False, max_age=None, pledge_kind="fixed", pledge_value=100, pledge_cap=None)
    base.update(kw)
    return FundRule(**base)


S = Screening(state="TX", household_size=3, monthly_income=2000, gestational_weeks=16, needs_travel=True, age=19)


def test_fpl():
    assert fpl_annual(1) == 15_650
    assert fpl_annual(3) == 26_650
    assert income_fpl_pct(2000, 3) == 90


def test_clinic_fund_first_and_percent_cap():
    rules = [rule(9), rule(1, kind="clinic", pledge_kind="percent", pledge_value=50, pledge_cap=300)]
    r = match(S, 800, rules)
    assert [m.fund_id for m in r.matches] == [1, 9]
    assert r.matches[0].suggested_amount == 300  # 50% of 800 = 400, capped at 300


def test_state_income_gestation_travel_age():
    rules = [
        rule(1, states=("KS",)),
        rule(2, income_max_fpl_pct=80),
        rule(3, gest_min_weeks=14, gest_max_weeks=24),
        rule(4, gest_max_weeks=12),
        rule(5, requires_travel=True),
        rule(6, max_age=17),
        rule(7, max_age=19),
    ]
    r = match(S, 5000, rules)
    assert {m.fund_id for m in r.matches} == {3, 5, 7}
    assert {k.fund_id for k in r.skipped} == {1, 2, 4, 6}


def test_unknown_gestation_skips_gestation_funds():
    s = Screening("TX", 1, 1000, None, False)
    r = match(s, 1000, [rule(1, gest_min_weeks=14)])
    assert not r.matches


def test_total_never_exceeds_cost():
    rules = [rule(i, pledge_value=300) for i in range(1, 6)]
    r = match(S, 700, rules)
    assert r.total_suggested == 700
    assert r.matches[-1].suggested_amount == 100


def test_reasons_present():
    r = match(S, 1000, [rule(1, states=("TX",), income_max_fpl_pct=200)])
    assert any("TX" in x for x in r.matches[0].reasons)
    assert any("poverty line" in x for x in r.matches[0].reasons)
