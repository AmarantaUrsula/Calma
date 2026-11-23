"""Reports: totals of money pledged or disbursed, grouped by up to three criteria.

Scope (who sees what):
  * clinic staff — pledges for their clinic's patients (their own fund and partner funds)
  * fund staff   — only their own fund's pledges
  * admin        — everything

De-identified: no names or contact details, income as a band of the poverty line, age and
weeks pregnant in bands. Groups with fewer than 5 patients are flagged, because tiny groups
can point to a specific person. Every Excel download is written to the audit log.
"""

from __future__ import annotations

import io
import json
import sqlite3
from collections import defaultdict
from datetime import date

from .matching import income_fpl_pct

SMALL_N = 5

# id -> (label, roles allowed). Funds get fewer criteria: only what a fund already sees.
DIMENSIONS: dict[str, tuple[str, set[str]]] = {
    "fund": ("Fund", {"clinic", "admin"}),
    "clinic": ("Clinic", {"fund", "admin"}),
    "help_type": ("Type of help", {"clinic", "fund", "admin"}),
    "month": ("Month", {"clinic", "fund", "admin"}),
    "week": ("Week", {"clinic", "fund", "admin"}),
    "home_state": ("Patient's home state", {"clinic", "fund", "admin"}),
    "care_state": ("State of care", {"clinic", "fund", "admin"}),
    "income_band": ("Income (% of poverty line)", {"clinic", "fund", "admin"}),
    "weeks_band": ("Weeks pregnant", {"clinic", "admin"}),
    "age_band": ("Age", {"clinic", "admin"}),
    "language": ("Language", {"clinic", "admin"}),
    "traveled": ("Traveled for care", {"clinic", "admin"}),
}

MEASURES = {
    "disbursed": ("Disbursed (pledges marked paid)", ("paid",)),
    "pledged": ("Pledged (approved, paid or not)", ("approved", "paid")),
}
DATE_BASES = {"paid": "Date paid", "approved": "Date approved", "appointment": "Appointment date"}


def dims_for(role: str) -> list[dict]:
    return [{"id": d, "label": lab} for d, (lab, roles) in DIMENSIONS.items() if role in roles]


def _band_income(pct: int | None) -> str:
    if pct is None:
        return "Unknown"
    for hi, lab in ((100, "Under 100%"), (200, "100–199%"), (300, "200–299%"), (400, "300–399%")):
        if pct < hi:
            return lab
    return "400% or more"


def _band_weeks(w: int | None) -> str:
    if w is None:
        return "Not sure"
    return "Under 12 weeks" if w < 12 else "12–19 weeks" if w < 20 else "20 weeks or more"


def _band_age(a: int | None) -> str:
    if a is None:
        return "Not given"
    return "17 or under" if a < 18 else "18–24" if a < 25 else "25–34" if a < 35 else "35 or older"


def _week_of(d: str) -> str:
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


def _scope(user_role: str, clinic_id: int | None, fund_id: int | None) -> tuple[str, tuple]:
    if user_role == "clinic":
        return "c.clinic_id = ?", (clinic_id,)
    if user_role == "fund":
        return "p.fund_id = ?", (fund_id,)
    return "1 = 1", ()


def fetch_rows(db: sqlite3.Connection, role: str, clinic_id: int | None, fund_id: int | None,
               measure: str, date_basis: str, start: date, end: date) -> list[dict]:
    """One de-identified row per pledge in scope that matches the measure and the date range."""
    where, params = _scope(role, clinic_id, fund_id)
    statuses = MEASURES[measure][1]
    date_col = {"paid": "p.paid_at", "approved": "p.decided_at", "appointment": "c.appointment_date"}[date_basis]
    q = f"""
        SELECT p.id, p.case_id, p.approved_amount, p.status, p.category, p.decided_at, p.paid_at,
               f.name AS fund_name, f.kind AS fund_kind, cl.name AS clinic_name, c.appointment_date,
               c.state, c.care_state, c.household_size, c.monthly_income, c.gestational_weeks,
               c.age, c.language, c.needs_travel
        FROM pledges p JOIN funds f ON f.id = p.fund_id JOIN cases c ON c.id = p.case_id
        JOIN clinics cl ON cl.id = c.clinic_id
        WHERE {where} AND p.status IN ({','.join('?' * len(statuses))})
          AND {date_col} IS NOT NULL AND substr({date_col}, 1, 10) BETWEEN ? AND ?
        ORDER BY substr({date_col}, 1, 10), p.id
    """
    out = []
    for r in db.execute(q, (*params, *statuses, start.isoformat(), end.isoformat())).fetchall():
        when = {"paid": r["paid_at"], "approved": r["decided_at"], "appointment": r["appointment_date"]}[date_basis][:10]
        pct = income_fpl_pct(r["monthly_income"], r["household_size"]) if r["monthly_income"] is not None else None
        row = {
            "pledge_id": r["id"], "case_ref": f"C-{1000 + r['case_id']}", "case_id": r["case_id"],
            "amount": r["approved_amount"] or 0, "status": "Paid" if r["status"] == "paid" else "Approved",
            "date": when, "approved_on": (r["decided_at"] or "")[:10], "paid_on": (r["paid_at"] or "")[:10],
            "appointment_date": r["appointment_date"],
            "fund": r["fund_name"], "clinic": r["clinic_name"],
            "help_type": "Travel & practical" if r["category"] == "practical" else
                         ("Clinic's own fund" if r["fund_kind"] == "clinic" else "Procedure (partner fund)"),
            "month": when[:7], "week": _week_of(when),
            "home_state": r["state"] or "Unknown", "care_state": r["care_state"] or "Unknown",
            "income_band": _band_income(pct), "weeks_band": _band_weeks(r["gestational_weeks"]),
            "age_band": _band_age(r["age"]), "language": "Spanish" if r["language"] == "es" else "English",
            "traveled": "Yes" if r["needs_travel"] else "No",
        }
        out.append(row)
    return out


def group(rows: list[dict], by: list[str]) -> dict:
    """Totals per combination of the chosen criteria (sorted by amount, largest first)."""
    agg: dict[tuple, dict] = defaultdict(lambda: {"amount": 0, "cases": set(), "pledges": 0})
    for r in rows:
        k = tuple(r[d] for d in by)
        agg[k]["amount"] += r["amount"]
        agg[k]["cases"].add(r["case_id"])
        agg[k]["pledges"] += 1
    time_dims = {"month", "week"}
    def sort_key(item):
        k, v = item
        # time order when the first criterion is time; otherwise biggest first
        return (k[0],) if by and by[0] in time_dims else (-v["amount"], k)
    groups = []
    for k, v in sorted(agg.items(), key=sort_key):
        n = len(v["cases"])
        groups.append({"keys": list(k), "amount": v["amount"], "patients": n, "pledges": v["pledges"],
                       "small": 0 < n < SMALL_N})
    all_cases = {r["case_id"] for r in rows}
    return {"groups": groups, "total_amount": sum(r["amount"] for r in rows), "total_patients": len(all_cases),
            "total_pledges": len(rows)}


DATA_COLUMNS = [
    ("case_ref", "Case"), ("fund", "Fund"), ("clinic", "Clinic"), ("help_type", "Type of help"),
    ("status", "Status"), ("amount", "Amount ($)"), ("approved_on", "Approved on"), ("paid_on", "Paid on"),
    ("appointment_date", "Appointment"), ("home_state", "Home state"), ("care_state", "State of care"),
    ("income_band", "Income (% of poverty line)"), ("weeks_band", "Weeks pregnant"), ("age_band", "Age"),
    ("language", "Language"), ("traveled", "Traveled"),
]


def data_columns_for(role: str) -> list[tuple[str, str]]:
    hidden = {d for d, (_, roles) in DIMENSIONS.items() if role not in roles}
    return [(k, lab) for k, lab in DATA_COLUMNS if k not in hidden]


def to_xlsx(title: str, filters: list[tuple[str, str]], by: list[str], result: dict, rows: list[dict], role: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="3E6681")
    money = '"$"#,##0'

    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    r = 2
    for k, v in filters:
        ws.cell(row=r, column=1, value=k).font = Font(bold=True)
        ws.cell(row=r, column=2, value=v)
        r += 1
    ws.cell(row=r, column=1, value="De-identified. Groups with fewer than 5 patients are marked: they could point to a specific person.").font = Font(italic=True, color="66655C")
    r += 2
    headers = [DIMENSIONS[d][0] for d in by] + ["Amount ($)", "Patients", "Pledges", "Note"]
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.font, cell.fill = head_font, head_fill
    first = r + 1
    for g in result["groups"]:
        r += 1
        for c, k in enumerate(g["keys"], 1):
            ws.cell(row=r, column=c, value=k)
        n = len(by)
        ws.cell(row=r, column=n + 1, value=g["amount"]).number_format = money
        ws.cell(row=r, column=n + 2, value=g["patients"])
        ws.cell(row=r, column=n + 3, value=g["pledges"])
        if g["small"]:
            ws.cell(row=r, column=n + 4, value="Fewer than 5 patients")
    r += 1
    n = len(by)
    ws.cell(row=r, column=1, value="Total").font = Font(bold=True)
    tot = ws.cell(row=r, column=n + 1, value=f"=SUM({get_column_letter(n + 1)}{first}:{get_column_letter(n + 1)}{r - 1})" if result["groups"] else 0)
    tot.number_format, tot.font = money, Font(bold=True)
    ws.cell(row=r, column=n + 2, value=result["total_patients"]).font = Font(bold=True)
    ws.cell(row=r, column=n + 3, value=result["total_pledges"]).font = Font(bold=True)
    for c in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(c)].width = 26 if c <= n else 14
    ws.column_dimensions["A"].width = max(ws.column_dimensions["A"].width, 34)

    ds = wb.create_sheet("Data")
    cols = data_columns_for(role)
    for c, (_, lab) in enumerate(cols, 1):
        cell = ds.cell(row=1, column=c, value=lab)
        cell.font, cell.fill = head_font, head_fill
        cell.alignment = Alignment(wrap_text=True)
        ds.column_dimensions[get_column_letter(c)].width = 18
    for i, row in enumerate(rows, 2):
        for c, (k, _) in enumerate(cols, 1):
            cell = ds.cell(row=i, column=c, value=row[k])
            if k == "amount":
                cell.number_format = money
    ds.freeze_panes = "A2"
    ds.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{max(1, len(rows) + 1)}"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def describe_filters(measure: str, date_basis: str, start: date, end: date, by: list[str], scope_name: str) -> list[tuple[str, str]]:
    return [
        ("Organization", scope_name), ("Measure", MEASURES[measure][0]),
        ("Dates", f"{start.isoformat()} to {end.isoformat()} ({DATE_BASES[date_basis].lower()})"),
        ("Grouped by", ", ".join(DIMENSIONS[d][0] for d in by) or "—"),
    ]


def audit_detail(measure: str, date_basis: str, start: date, end: date, by: list[str], n: int) -> dict:
    return {"measure": measure, "date_basis": date_basis, "start": start.isoformat(), "end": end.isoformat(),
            "group_by": by, "rows": n}


__all__ = ["DIMENSIONS", "MEASURES", "DATE_BASES", "dims_for", "fetch_rows", "group", "to_xlsx",
           "describe_filters", "audit_detail", "data_columns_for", "json"]
