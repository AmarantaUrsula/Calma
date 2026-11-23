# Calma — Design Recommendations (draft, 2026-11-22; formerly "Ataraxia")

Based on the product description and flowchart (`design-flowchart.webp`).

## Decisions made (2026-11-22)

1. **Screening order:** clinic funds first, then *all* other eligible funds at once. Partner-fund order doesn't matter, because patients usually qualify for only a few (based on location, travel needs, sometimes gestational age). **Gestational age is a screening field.**
2. **Procedure cost:** entered by the clinic. Pledges will never cover the full cost, so the app always shows a remaining balance and doesn't need cap/overflow logic beyond "pledges ≤ cost."
3. **Fund budgets:** the app does **not** enforce budgets automatically. When a patient matches, each eligible fund gets a notification ("eligible patient, suggested amount $X"). A person at the fund checks the budget and approves or declines manually.
4. **Status page:** the one-time link becomes a reusable status page after the form is submitted, and expires after the appointment.
5. **Privacy:** the goal is **HIPAA compliance** and strong safeguarding of patient data (see section B).
6. **Funds vs. clinics:** independent abortion funds pledge to *multiple* clinics. Each clinic's own fund is a block grant with a **monthly limit**, which the app tracks. **Every pledge is approved manually, on both the clinic and fund side, for now.** No auto-approval.
7. **Languages:** English and Spanish from v1. Every patient-facing string is translated, and the patient picks a language on the first screen.
8. **Stack: FastAPI + React (Vite) + SQLite** (decided 2026-11-22). Version 1 built; see README.md.
9. **Name: Calma** (decided 2026-11-22).

10. **Intake questions (2026-11-23):** questions are configurable. Core questions are always asked. Optional ones (age, travel miles, nights away, meals, dependent care, insurance, unhoused, judicial bypass, contact details) are asked when a matching fund's rules need them or when the clinic or a fund turns them on. Every optional question can be skipped, and answers to questions that weren't asked are dropped on the server.
    - **Asked for the first day of the last period** (weeks are computed at the appointment date, and only weeks are stored), with a weeks fallback.
    - **Age instead of date of birth,** and **state of care taken from the clinic** rather than asked. Both reduce what we store. *Confirmed by the product owner on 2026-11-23: keep it this way.*
    - **Contact details are clinic-only:** never shown to funds, never sent to AI, deleted when the case closes.
11. **Fund types (2026-11-23):** eligibility can be by **state of residence, state of care, or either one** (added 2026-11-23 after the real Carolina page). Help can be **procedure** money (stacks toward the clinic bill, capped at its cost) or **practical support** (rates × the patient's travel answers, capped; paid to the patient, not part of reimbursement). Funds can also require **no insurance coverage**.

12. **Partnerships (2026-11-23):** a fund requests a partnership with a clinic and the clinic accepts (two-sided, since the clinic is the hub). Only accepted partnerships drive matching, question plans and fund visibility. Ending a partnership declines that fund's pending pledges at the clinic but keeps approved ones payable.

13. **Visual style (2026-11-23):** replaced the default black-and-pink theme (from the course's Semester Project Rules) at the product owner's request. Hot pink on near-black felt like "a teacher's correcting pen" to a nervous patient. New calm palette on a warm linen background: muted slate blue for buttons and links, sage green for the Calma name and "approved", warm brown for section headings, ochre for "waiting", terracotta instead of alarm red for problems. Every text color passes WCAG AA contrast (4.5:1 or better). Colors live as variables at the top of `frontend/src/styles.css`.

14. **Staff accounts (2026-11-23):** a real create-account and log-in flow for clinic staff, fund staff and admins (patients keep using their private link).
    - **Approval:** new accounts wait for a Calma admin's approval, including admin accounts, so nobody can grant themselves access.
    - **Password storage:** salted scrypt hashes with the settings stored in each hash, plus an optional pepper kept outside the database. Comparisons are constant-time. The password and hash never appear in responses or logs.
    - **Login protection:** one generic error message, and a 15-minute lockout after 5 misses. Session tokens are kept only as hashes.
    - **Not built yet:** password reset, email verification and two-factor login.

15. **Real funds as reference (2026-11-23):** four real funds (Carolina Abortion Fund, West Fund, Faith Roots Abortion Fund, Mariposa Fund) are tracked for their public eligibility pages only (`funds.reference_only = 1`): no partnerships, no accounts, never matched with demo patients. The first live run showed the AI reads real pages well (all quotes verified). It also revealed gaps in the rules model:
    - "lives in **or** gets care in" a state (Carolina). *Added 2026-11-23 as a third state-basis option, "either".*
    - identity-based eligibility (Mariposa: people affected by the immigration system)
    - funds that only pay at specific clinics

    These are candidates for future rule options.

16. **Demo readiness (2026-11-23):**
    - **Separate demo password:** the deployed site uses its own demo password, set in Render (`CALMA_DEMO_PASSWORD`, required there), because the repo and its README are public.
    - **Demo notice:** patient screens (English/Spanish) and the login pages say not to enter real information.
    - **Colleague guide:** `DEMO_GUIDE.md` walks colleagues through three 5-minute scenarios and asks for feedback.

## Guiding principle: the AI never decides who gets money

Eligibility and pledge amounts must be **deterministic, auditable rules**, not LLM output. These decisions move real money for a vulnerable population. Every result must be explainable ("matched because: lives in TX, income ≤ 200% FPL"), and the same input must always give the same answer. So the **matching engine is plain Python code, not an agent**. Agents go where language is the hard part: turning messy fund policies into rules, explaining things in plain words, and summarizing cases for staff.

## Recommended agents

| # | Agent | What it does | Who uses it | Build when |
|---|-------|--------------|-------------|-----------|
| 1 | **Fund Rules Extractor** | Takes a fund's policy text (pasted, or later fetched from its website about once a month) and outputs structured criteria (states, income limit as % FPL, household rules, identity, travel support, max pledge, copay %). Shows a **diff against the current rules for a human to approve**. Never writes to the live rules on its own. | Admin / fund staff | Week 1–2. This is the AI answer to "storing fund rules" and replaces Salesforce's manual entry. |
| 2 | **Case Summary Agent** | For the clinic/fund portal: a 3–4 line summary of a case, why each fund matched or didn't (read from the engine's output), and flags (missing info, income looks inconsistent with household size). Read-only. It cannot approve anything. | Clinic & fund staff | Week 2 |
| 3 | **Plain-Language Helper** | On the patient form: answers "what does household mean?" and similar questions at a 4th–5th grade reading level, and handles Spanish (and other languages). Strictly scoped: it can't promise funding or give medical or legal advice, and it always points to the clinic phone number. | Patients | Week 2–3, optional |
| 4 | *(later)* **Notification Writer** | Drafts plain-language text/email messages for status changes. Templates may be enough, so this one is optional. | System | Later |

**Not agents:** the matching engine, pledge approval, budget tracking, reimbursement. Those are plain code and database work.

Stack per course rules: PydanticAI (`pydantic-ai-slim[openai]`) with structured outputs. Model from `OPENAI_MODEL` (default `gpt-5.6-luna`). OpenAI directly for now, since the Portkey key is expired; switch to Portkey when renewed.

## Do we need an MCP server?

**Not for the core app.** The agents can call the database through ordinary PydanticAI tool functions inside the backend. Adding MCP inside a single app is extra moving parts with no user benefit.

**When MCP *would* make sense:**
- A **Fund Rules MCP server** (`list_funds`, `get_fund_criteria`, `check_eligibility(profile)`, `propose_rule_update`) so that staff, or Women's Emergency Network's shared Florida form, could query fund rules from Claude or another tool. This is the natural MCP boundary if the course requires one, or for the multi-org "shared form" future.
- **Recommendation:** build the fund-rules logic as a clean service module (`fund_rules.py`) now. Wrapping it in FastMCP later (as you did in hw5) is about 30 lines. Decide based on whether the semester project requires an MCP component.
- The Epic integration would **not** be MCP. That's HL7/FHIR, which is a different problem and should stay out of scope.

## Other decision points

### A. Architecture / stack
- **Recommendation:** FastAPI backend + React/Vite frontend + SQLite, the same as hw5. Three portals = three route groups in one React app, with role-based login.
- Alternative: Dash multi-page. Simpler, but awkward for three role-separated portals and the one-time link flow.

### B. Patient privacy (the biggest real-world risk)
Abortion data is legally sensitive (subpoenas, state laws) and covered by HIPAA at a clinic.
- **Data minimization:** collect only what matching needs. Use an income band rather than pay stubs. Don't store a name if the clinic's appointment ID is enough.
- **What goes to the LLM:** send no patient-identifying info to OpenAI. The Case Summary Agent gets de-identified fields only. A real deployment would need a BAA and zero data retention with the AI provider.
- **Retention:** auto-delete or archive screening data after the case closes.
- **This week:** fake data only. Still, design the schema so that minimization is the default.
- **HIPAA-ready design choices to build in from the start:** role-based access (patient / clinic staff / fund staff / admin) with least privilege; an audit log of who viewed or changed each case; encryption in transit (HTTPS) and at rest; session timeouts; status-page links that expire; no patient data in URLs, logs or LLM prompts; data retention and deletion rules; BAAs with every vendor that touches patient data (hosting, SMS/email, AI). Funds see only the fields they need: case ID, eligibility reason, suggested amount, clinic. Not the full form.
- **Neutral naming in messages:** text/email notifications should not mention abortion. The sender name and message preview can be seen by others on a phone's lock screen.

### C. Fund rules data model (resolves "Salesforce vs. mock vs. agent")
**Plan (2026-11-22): our own database, three ways to keep it current, and a person always approves.**

1. **Where the rules live:** a `fund_criteria` table in Calma's own database (SQLite now, Postgres when hosted). Each fund has structured fields: states/counties served, income limit (% of federal poverty level), household rules, gestational age limits, identity criteria, travel support, typical pledge amount, plus `source_url`, `last_verified_at`, `verified_by`. Rules are **versioned**: a new version is added with an effective date and the old one is kept for the audit trail. The matching engine reads only the *approved current* version.
2. **Source #1: funds edit their own criteria (primary).** Funds already have a login to the fund portal, so give them a "My eligibility rules" page. This is the most accurate source, and it's legally clean. Every ~60 days the app nudges funds to confirm "still accurate?" with one click.
3. **Source #2: website check every ~2 months (backup/staleness alarm).** A scheduled job fetches each fund's eligibility page and compares it with the last saved copy. If **nothing changed**, it just updates `last_checked_at`. If the page **changed**, the **Rules Extractor** (AI) reads the new page and proposes updated structured rules, quoting the source sentence for each field. An admin sees a side-by-side diff and approves, edits, or rejects. Nothing is ever applied automatically.
4. **Source #3: manual admin entry**, with the Rules Extractor helping turn pasted text into structured fields.

**Is this an agent?** Mostly no, and that's on purpose:
- The **scheduler + fetch + change detection** is a plain scheduled job (cron / APScheduler). No AI needed.
- The **Rules Extractor** is one AI step with a strict output schema (PydanticAI structured output): "read this page → fill in these fields → quote your source → say 'not stated' if missing." It's an AI *extractor*, not an autonomous agent.
- It becomes a true **agent** only if we let it *find* the right page itself, with tools like `fetch_page(url)` and `list_links(url)` that it uses to navigate from a fund's homepage to its eligibility/FAQ page. That's useful for onboarding a new fund (you give it the homepage, it finds the rules). Recommendation: start with the extractor, and add the "page finder" agent as a stretch goal.

**Realities of scraping fund websites:**
- Many funds **don't publish full criteria** on purpose ("call our hotline"), so the extractor must be allowed to say "not stated" rather than guess. This is the main reason fund self-editing is the primary source.
- Some sites load content with JavaScript, which may need a headless browser (Playwright).
- Be a good citizen: check every ~2 months, respect robots.txt, identify the bot honestly, and ideally tell partner funds we do this.
- The **National Network of Abortion Funds** directory (abortionfunds.org) is a good starting list of funds and their websites.

**Status (2026-11-22):** ~7 made-up funds seeded. **Rules Extractor on pasted text is built** (admin screen: paste text → AI suggestion with quotes → a person edits, approves or rejects → versioned rules). **Scheduled website check is built** (every 60 days; unchanged pages skip the AI; changed pages feed the same review screen; respects robots.txt; refuses private addresses). **Fund self-edit page is built** (fund portal → My eligibility rules: edits go live as a new version, replace any pending AI suggestion, and are audit-logged; a reminder appears after 60 days with a one-click "still accurate"). **Clinic self-edit is built** (clinic portal → Our fund's rules: monthly limit + eligibility rules, same editor and reminder). **Next:** PDF policy support; a headless browser for pages that need JavaScript to load; email reminders to funds.

### D. Pledge stacking logic (resolved — see Decisions made #1–3)
- Clinic funds first (e.g. cover up to 50% copay), then partner funds. **How do partner funds stack?** Fixed priority order per clinic? Each fund pledges a fixed amount or a % up to its cap?
- Total pledges must not exceed the procedure cost. Who enters the cost? Proposed: the clinic, at booking.
- What if a fund's monthly budget is used up? Skip it, or show it as "pending"?

### E. Case & pledge status lifecycle
Proposed state machine: per pledge: `matched → pending approval → approved | declined → paid (completed)`. Per case: `screening → matched → awaiting approvals → ready → appointment done → reimbursed/closed`.
- Define exactly what the patient sees for each status, in plain words, with the clinic phone number always visible.

### F. "One-time link" vs. returning to see status (resolved — option 1)
The flowchart has the patient come back later to check status, but the link is "one-time." Options: (1) the link becomes a reusable status page after the form is submitted (expires after the appointment), or (2) send a second link by text/email when status changes. **Recommend (1)** with a short code tied to the appointment.

### G. Visibility rules (clinic as hub)
- A `clinic_fund_partnership` table drives everything: a fund only sees cases from its partner clinics, and only the fields it needs (not the full form).
- How many fake clinics? Proposed: 2 clinics, overlapping partner funds, to demonstrate the visibility rules.

### H. Block grants (resolved — see Decisions made #6)
Model each fund's money as a **budget per clinic per month**. A block grant is a budget the clinic can approve against directly without pinging the fund. This costs little to add to the data model now and avoids a redesign later. The UI can come later.

### I. Notifications
- **This week:** no real SMS/email. Show the "sent" link in the clinic portal or a dev panel. Twilio/SendGrid later.

### J. Reading level & language
- Write all patient copy at a 4th–5th grade level (we can check it with a readability score). **Spanish in v1 (decided).** Keep strings in translation files (`en.json`, `es.json`) rather than hard-coded. Spanish should be reviewed by a native speaker before any real use, not just machine-translated.

### K. Name (resolved — Calma)
"Ataraxia" (calm, freedom from distress) is nice but hard to spell and say for a 4th-grade-reading-level audience. The name should be short, easy to say in English **and** Spanish, and **neutral**: it shows up in text messages, so it shouldn't reveal what the app is for.

Candidates (2026-11-22):
- **Calma**: "calm" in Spanish, obvious in English. Top pick.
- **Alivio**: "relief" in Spanish. Warm, but less obvious to English speakers.
- **Respiro**: "a breather / relief" in Spanish (and Italian). Suggests "you can breathe now."
- **Sereno**: "calm, serene" in Spanish. Sounds like "serene" in English.
- **Ease**: English only. Very simple, but doesn't carry over to Spanish.

## Proposed scope for this week
1. Seed DB: 2 clinics, ~6 fake funds, partnerships, budgets.
2. Patient portal: link → plain-language form → results page with per-fund status + clinic phone.
3. Deterministic matching engine with "why matched" explanations + unit tests.
4. Clinic portal: case list, approve/decline internal fund pledges, see partner pledge status.
5. Fund portal: notifications ("pings") list, approve/decline, pledges owed.
6. Reimbursement view (simple table of pledges owed per clinic/fund).
7. Agent #1 (Fund Rules Extractor) if time allows.
