# Calma

A web app that screens abortion patients for funding support. One short form checks the patient against the clinic's own fund first, then every partner abortion fund they qualify for. Clinics and funds approve each pledge by hand, and everyone sees what is owed.

**This is version 1:** fake data, manual approval only, no Salesforce. One AI helper, the **Fund Rules Extractor**, suggests rule updates for an admin to approve. See [DESIGN.md](DESIGN.md) for the design decisions and [Ai.prompts.md](Ai.prompts.md) for the prompt log.

## Run it

Pause OneDrive syncing while installing (see `../Semester Project Rules.md`).

```bash
cd calma
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m backend.seed                    # (re)create demo data in data/calma.db
.venv/bin/python -m uvicorn backend.main:app --port 8020
```

In a second terminal:

```bash
cd calma/frontend && npm install && npm run dev  # http://localhost:5178
```

Tests: `.venv/bin/python -m pytest -q backend/tests`

> **Which address?** Open the app at **http://localhost:5178**. Port 8020 is the API behind it; opening localhost:8020 in a browser just sends you to the app. Both servers need to be running: `calma-api` and `calma-web` in the Browser pane, or the two commands above.

## Deploy on Render

The repo includes a `Dockerfile` (builds the React app, then serves it from the FastAPI server as one service) and a `render.yaml` Blueprint.

1. In Render: **New → Blueprint**, connect GitHub, and pick the **Calma** repo. Render reads `render.yaml`.
2. When asked, paste your **OPENAI_API_KEY** (it's stored in Render, never in the repo). Other settings come from `render.yaml`:
   - `OPENAI_MODEL=gpt-5.6-luna`
   - `CALMA_SEED_IF_EMPTY=1`: load the made-up demo data on start
   - `CALMA_SCHEDULER=0`: automatic website checks off, to avoid unplanned AI calls. **Admin → Check now** still works.
3. Deploy. The app is at the `https://calma-….onrender.com` address Render shows. The health check is `/api/health`.

What to know:
- **Data resets:** the free plan's disk is temporary, so the demo data resets whenever the service restarts or redeploys. Keeping data needs a Render persistent disk or Postgres.
- **Sleep:** free services sleep when unused. The first visit after a while takes about a minute.
- **Demo data only:** real patient data still needs two-factor login, password reset and HIPAA business associate agreements with Render and OpenAI.

## Demo accounts

Every demo account uses the made-up password **`calma-demo-2026`** (it's set in `backend/seed.py`). The emails use the reserved `example.org` domain.

| Who | Email | Portal |
|---|---|---|
| Rosa, Mesa front desk | `rosa@mesa.example.org` | Clinic (NM) |
| Dana, Prairie front desk | `dana@prairie.example.org` | Clinic (KS) |
| Sam | `sam@desertbloom.example.org` | Desert Bloom Fund |
| Jordan | `jordan@heartland.example.org` | Heartland Access Fund |
| Alex | `alex@openroad.example.org` | Open Road Travel Fund |
| Kai | `kai@latercare.example.org` | Later Care Fund |
| Mia | `mia@youthaccess.example.org` | Youth Access Fund |
| Lu | `lu@enchantedcircle.example.org` | Enchanted Circle Care Fund |
| Admin | `admin@calma.example.org` | Admin |

## Accounts and passwords

- **Who logs in:** clinic staff, fund staff and Calma admins. **Patients never log in.** They use the private link their clinic sends, which becomes their status page.
- **Create an account** (`/signup`): first name, last name, work email, where you work (a clinic, a fund, or Calma admin), password and confirm password. New accounts start as **waiting for approval**. A Calma admin approves or rejects them under **Admin → Staff accounts**, so nobody can give themselves access to patients' information, or make themselves an admin, just by signing up. Admins can also disable an account, which signs that person out right away.
- **Log in** (`/login`): email and password. A wrong password and an unknown email get the same message. After 5 misses, that email is locked for 15 minutes.
- **What's stored for each user** (`users` table): name, email (lowercase, unique), role, clinic or fund, status, and dates (created, approved, last login). Plus `password_hash`. **The password itself is never stored.**
- **How passwords are protected** (`backend/auth.py`):
  - **scrypt hash:** each password is run through scrypt, a slow, memory-hard, one-way function, with a unique random salt. It's stored as `scrypt$N$r$p$salt$hash`. A copy of the database can't be turned back into passwords, and the same password gives a different hash for each user.
  - **Login re-hashes:** login re-hashes what was typed, using the salt and settings stored in that user's hash, then compares in constant time. Sign-up and login can't drift out of sync, because the settings travel with each hash.
  - **Pepper:** an optional server secret, `CALMA_PASSWORD_PEPPER`, is mixed in. It's kept in Render's settings, not the database, so a stolen database alone isn't enough to even start guessing. On Render it's generated automatically. Don't change it later, or every password stops working.
  - **Never sent out:** no API response, log, audit entry or AI call ever includes a password or its hash. Sessions are random tokens, kept on the server only as a hash, and expire after 30 idle minutes.
- **Not built yet:** password reset and email verification (both need email sending), and two-factor login.

## Demo walkthrough

1. Open http://localhost:5178 and **log in** as Rosa (`rosa@mesa.example.org`; demo password below).
2. Under **New appointment**, click **Create link**, then **Open patient link**.
3. As the patient: pick English or Español and answer the 6 questions. Try Texas, 3 people, $2,000/month, 16 weeks, needs travel, age 22.
4. The results page shows each fund as *Waiting for an answer*, plus the amount the patient may owe and the clinic's phone number.
5. Back as Rosa: click the case and approve the **Mesa Justice Fund** pledge. Watch the monthly limit go down.
6. Log out, then log in as Sam (`sam@desertbloom.example.org`). The patient shows up under *Needs decision*; approve it.
7. The patient's page now shows *Approved* for both. Mark the visit done as Rosa. Sam then sees *Owed to clinic* and clicks **Mark paid**.
8. **Admin** shows every fund's rules and the audit log.
9. **AI rule updates:** as Admin, click **Update rules** next to a fund and paste its policy text. Then click **Suggest rules with AI**. You'll see the current rules next to the suggested ones, with the exact quote each came from. Fix anything wrong, then click **Approve and make live** (or **Reject**). Matching uses the new rules right away, and the audit log records who approved and what they edited.

10. **Scheduled website checks:** Admin → **Fund website checks**. Each partner fund has an eligibility page link; the demo uses `demo://` pages stored in `data/demo_pages/`. About 30 seconds after the API starts, and then every 6 hours, Calma checks any fund not checked in the last 60 days:
    - **Page unchanged:** "No change", with no AI call.
    - **Page changed but the rules are the same:** "Rules match".
    - **Rules may have changed:** a suggestion appears at the top of Admin for you to review.

    To see a change, edit one of the demo HTML files (for example, change `$250` to `$275` in `desert-bloom.html`), then click **Check now**. You can also give a fund a real `https://` link.

    You can run checks from the terminal too: `.venv/bin/python -m backend.website_check` checks the funds that are due. Add `--all` to check every fund, or `--fund 3` to check one.

    Settings: `CALMA_CHECK_INTERVAL_DAYS` (default 60), `CALMA_CHECK_POLL_HOURS` (default 6), `CALMA_SCHEDULER=0` turns the background schedule off.

11. **Funds keep their own rules up to date:** sign in as any fund (for example **Kai (Later Care)**) and open **My eligibility rules**. Fund staff can set:
    - the states they serve (or any state)
    - an income limit, with a live dollar example
    - the weeks of pregnancy they cover, travel-only, and an age limit
    - their usual pledge

    A summary shows exactly what's changing before **Save and make live**. The fund's own edit goes live right away as a new version (the fund is the authority on its rules) and replaces any AI suggestion waiting for an admin. If the rules haven't been confirmed in 60 days, a banner asks **"Are your eligibility rules still right?"**, and one click on **Yes, still accurate** resets the reminder.

12. **Clinics keep their own fund's rules up to date:** as **Rosa (Mesa front desk)**, open **Our fund's rules**. The clinic can set its fund's **monthly limit** (its block grant; Calma blocks approvals past it) and edit the fund's eligibility rules with the same editor funds use. Changes go live as a new version and are audit-logged. The same 60-day reminder appears on the clinic portal. Clinic staff can only edit their own clinic's fund, not partner funds.

13. **Intake questions (configurable):** patients always answer the core questions:
    - state where they live
    - household size
    - income, monthly or yearly
    - first day of last period, or weeks pregnant if they don't know
    - whether they need to travel

    Extra questions are added automatically when a matching fund needs them: age; travel miles, nights away, days of meals and days of dependent care (only if the patient is traveling); insurance/Medicaid; unhoused; judicial bypass (only for under-18 or age skipped); and contact details. The patient can skip any of them.
    - **Clinics:** **Intake questions** tab. See every question, whether it's asked and why, and turn on extras (including contact details, which only the clinic ever sees and which are deleted when the case closes).
    - **Funds:** **My eligibility rules** → **Extra questions to ask patients**. Answers show on each patient card. A fund only sees answers to questions it needs or asked for.
14. **State of care & practical support:**
    - **State of care:** a fund can base eligibility on where the abortion happens (the clinic's state) instead of where the patient lives. In the demo, Enchanted Circle covers anyone getting care in New Mexico.
    - **Practical support:** a fund can give travel help instead of procedure money: per-mile, per-night, meals and dependent-care rates, a flat amount and a cap. In the demo, this is Open Road. That help is shown separately from the clinic bill, isn't part of reimbursement, and can be marked provided before the visit.
    - **Insurance:** a fund can limit help to patients whose insurance doesn't cover abortion.

15. **Partnerships:** funds choose which clinics they work with. As a fund (for example **Jordan (Heartland Access)**), open **Partner clinics**. It shows each clinic, the status (Accepted / Waiting for clinic / Declined by clinic), and the accepted and requested dates.
    - **Add partner clinic** sends a request. The clinic sees it under **Partner funds** (with a banner) and can **Accept** or **Decline**. Only accepted partnerships count: until then, the fund isn't matched with that clinic's patients and can't see its cases.
    - **Remove** ends a partnership. Patients still waiting on that fund at that clinic are declined so their cases don't stall; already-approved pledges stay and can still be marked paid.
    - Clinics can end a partnership too, but not with their own fund. Everything is audit-logged.

## AI setup

- The model comes from `OPENAI_MODEL` (default `gpt-5.6-luna`), through OpenAI's Responses API.
- Keys come from the workspace `.env`, which overrides any keys already set in your shell. It uses `OPENAI_API_KEY` by default. Set `CALMA_USE_PORTKEY=1` to route through Portkey once that key is renewed.
- Only fund policy text is sent to the model, never patient data.
- How the extractor avoids made-up rules:
  - The model must answer "not stated" rather than guess.
  - Code checks that every quote really appears in the pasted text.
  - Income limits given in dollars are flagged for a person to fill in.
  - Nothing goes live without a person approving it.

## Layout

| Path | What |
|------|------|
| `backend/matching.py` | Matching engine: plain rules, no AI. Clinic funds first, then partner funds. Each match lists the reasons it matched. |
| `backend/main.py` | FastAPI routes for the patient (link token), clinic, fund and admin portals |
| `backend/db.py` | SQLite schema: clinics, funds, partnerships, versioned fund rules, cases, pledges, audit log |
| `backend/seed.py` | Made-up clinics, funds and staff |
| `backend/rules_extractor.py` | Fund Rules Extractor (PydanticAI, structured output) and the code that compares a proposal with the current rules |
| `Dockerfile`, `render.yaml` | Production build (one service) and Render Blueprint |
| `backend/auth.py` | Password hashing (scrypt + salt + optional pepper), password rules, login lockout |
| `backend/llm.py` | Model and key setup (OpenAI direct or Portkey) |
| `backend/questions.py` | Intake question catalog and which questions each clinic's patients see (and why) |
| `backend/website_check.py` | Scheduled website check: safe fetching, robots.txt, change detection, command-line runner |
| `backend/proposals.py` | Turns policy text into a proposed rule version (shared by the paste screen and the website check) |
| `data/demo_pages/` | Made-up fund eligibility pages for the demo |
| `backend/tests/` | Matching, end-to-end, Rules Extractor, website-check, fund-rules, intake-question, partnership and account tests (fake model, no network, no API cost) |
| `frontend/src/pages/` | `Patient.tsx` (English/Spanish), `Clinic.tsx`, `Fund.tsx`, `FundRules.tsx` (rules editor shared by funds and clinics), `Partnerships.tsx` (fund requests, clinic accepts), `Admin.tsx`, `Staff.tsx` (sign-in) |
| `frontend/src/i18n.ts` | All patient text in English and Spanish |

## Not production-ready

Real sign-in is built (see above). Before real patient data, it still needs password reset, two-factor login, HTTPS, encryption at rest, hosting under a HIPAA business associate agreement, real SMS/email delivery, and a native-speaker review of the Spanish. See DESIGN.md section B.
