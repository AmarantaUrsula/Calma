# Calma (formerly Ataraxia) — AI Prompt Log

Log of the prompts typed while building Calma (originally called Ataraxia), a web app to help screen abortion patients for funding support. Prompts are recorded verbatim, in order.

---

## Prompt 1 — 2026-11-22

> This a new project building a web app to help screen abortion patients for funding support. The project is tentatively called Ataraxia (until we think of a better term). Create Ai.promtps.md and keep it updated as we work as this is the log of what I typed for the prompts.

**Outcome:** Created the `ataraxia/` project folder and this prompt log (`Ai.prompts.md`).

---

## Prompt 2 — 2026-11-22

> Ok what I will do is give you the general design of the app. The first thing that would be good is to get your suggestion on what agents we need to build and if we need to build and MCP server, and then any other decision points in the design you identify. Does that sound good?

**Outcome:** Agreed on the plan; waiting for the general design, then will recommend agents, whether an MCP server is needed, and other design decision points.

---

## Prompt 3 — 2026-11-22

> First, can you check if my portkey is expired?

**Outcome:** Tested the `PORTKEY_API_KEY` from the workspace `.env` (the same key is used in HW 3, Lecture 10 and Lecture 11, and in the shell environment) against Portkey's API. It returned HTTP 401 "Invalid API Key" (error code 03), so the key is expired, revoked or wrong. It needs to be replaced with a new key from the Portkey dashboard.

---

## Prompt 4 — 2026-11-22

> can you put this one in .env please? OPENAI_API_KEY=[redacted — key not recorded in this log]

**Outcome:** Added `OPENAI_API_KEY` to the workspace `.env`. A test call to OpenAI returned HTTP 200, so the key works. The expired `PORTKEY_API_KEY` is still in `.env`.

---

## Prompt 5 — 2026-11-22

> *(Attached image: flowchart of the app, saved as `design-flowchart.webp`. It shows: Appointment booked (online or by phone) → One-time unique link (sent by text or email) → Patient portal: screening form (income, household, location, travel) → Matching engine (clinic funds first, then partners), which gets Fund criteria (updated manually) → Clinic portal (approves justice/internal funds) and Fund portal (gets ping, approves pledge) → Patient sees pledge status (approved, pending, or completed) → Appointment day (patient pays remaining balance) and Reimbursement (clinic and fund see pledges owed). Legend: Patient, Clinic, Fund, System/shared.)*
>
> The product. It's a patient-facing tool for screening people for abortion funding. One form checks a patient against several funding sources at once, instead of the patient piecing together help from each fund separately. It started as "Piggy Bank" and was later renamed "Autonomy." A pilot with a Planned Parenthood affiliate showed it works, but it was never fully put into use, mostly because of leadership and organizational problems rather than the technology.
> What made it valuable:
>
> * Patients fill it out themselves. It's written at roughly a 4th–5th grade reading level, so anyone can complete it.
> * It checks several funds in one pass. It looks at the clinic's own justice or internal funds first, then the outside funds that clinic works with. Each fund's rules (where you live, income, identity, travel) are built into the matching logic.
> * There are three connected portals: one for the patient, one for the clinic and one for the fund. The clinic is the hub: each fund only sees clinics it works with, and each clinic only sees its partner funds.
> * Funds and clinics stay in control of approvals. Each pledge is approved separately. Approval was manual or automatic up to a limit, and your first version would be manual only.
> * Reimbursement is simpler. Both the clinic and the fund see what's owed, and they can track monthly budgets and close out cases afterward.
>
> How it works: The patient books an appointment online or by phone and gets a one-time link. They enter income, household size and location. The app first checks the clinic's own funds (for example, up to a 50% copay), then the partner funds. The patient sees each source marked "approved," "pending" or "completed," and the clinic number is always shown in case they need more help.
> Open design questions from the call:
>
> * Storing fund rules. They used Salesforce, which was expensive and had to be updated by hand. Your options: a mock database of made-up funds, or an AI agent that checks fund websites about once a month. Funds rarely change their rules, so manual updates may be fine.
> * Block grants. More funds now give clinics a lump sum, so the clinic portal can approve on its own and the fund side matters less.
> * Future connections. Linking to clinic medical-record systems like Epic for billing.
> * Another possible use. A shared screening form for Florida funds, through Women's Emergency Network.
>
> Your plan for this week: Build the patient, fund and clinic portals with fake data, all-manual approval, and no Salesforce.
> The flowchart follows.

**Outcome:** Wrote `DESIGN.md` with recommended agents, the MCP server decision, and other design decision points.

---

## Prompt 6 — 2026-11-22

> Thanks for this. In terms of stacking funds: The process should be screen for clinic fund eligibility first, then screen all other funds the patient is eligible for. Patients are usually only eligible for a few funds based on their geographic location, travel needs, and sometime gestation, so the order of screening those doesn't matter. The clinic knows the procedure cost and they will never be able to pledge enough funds to cover the entire procedure. One way to deal with the fund's monthly budget running out is that once the app identifies what a patient is eligible for the funds gets a notification that they have an eligible patients and for what amount, but the pledge has to be approved manually by someone who is responsible for checking the budget. I think turning the link into a status page is the right move as per your description. Agree about privacy. We want to make sure that this app is ultimately HIPPA compliant and safeguards patient data. For the block grant: that could be be tricky because we are talking about independent abortion funds that pledge to multiple clinics. Clinics then have their own funds which is a block grant with a monthly limit, so the app could definitely track that. However, we still want to build in a manual approval of each pledge on both the clinic and fund ends for now. Let's build this in English and Spanish please. Do you have another idea for the app name that is simple but invokes a similar meaning (NOT Autonomy).

**Outcome:** Recorded these decisions in `DESIGN.md` (new "Decisions made" section) and suggested app names.

---

## Prompt 7 — 2026-11-22

> Let's go with Calma I love that. In terms of a database that has up to date abortion fund eligibility criteria, what is the move for that? We don't want to use Salesforce. Is it possible to scrape abortion fund websites every couple of months for this information and store it in the app somewhere?

**Outcome:** Renamed the project to **Calma** in the docs. Recommended a plan for fund rules: our own database of versioned rules, funds edit their own criteria in the fund portal, and a check every two months that flags changed fund pages and has an AI propose updates for a person to approve. Added it to `DESIGN.md` section C.

*(Follow-up typed while I was working:)*

> And would it be an agent that does that?

**Outcome:** Mostly no. Fetching pages and spotting changes is a plain scheduled job. Reading a changed page and filling in the rule fields is one AI "extractor" step with a fixed output format. It becomes a true agent only if it navigates a fund's website to find the eligibility page itself (a stretch goal). Added to `DESIGN.md` section C.

---

## Prompt 8 — 2026-11-22

> FastAPI + React

**Outcome:** Built version 1 of Calma with FastAPI + React + SQLite: fake data, manual approval only, no AI yet.
- **Backend** (`backend/`): matching engine with plain rules (clinic funds first, then all eligible partner funds; suggested total never exceeds cost; each match explains why). Patient link that turns into a status page and expires after the visit. Clinic portal (book a visit, approve own-fund pledges within the monthly limit, mark visit done, reimbursement view). Fund portal (eligible patients with suggested amounts, approve/decline, mark paid). Admin view (fund rules, audit log). Demo sign-in.
- **Frontend** (`frontend/`): black-and-pink design. Patient form asks one question per screen in English or Spanish, then shows a status page with the clinic phone always visible.
- **Tests:** 9 passing (matching rules, full end-to-end flow, clinic monthly limit, sign-in and link expiry). Clicked through the clinic → patient (Spanish) → fund → clinic flow in the browser.
- Servers: API on port 8020, web on port 5178 (added to the workspace `.claude/launch.json`). Run steps are in `README.md`.

---

## Prompt 9 — 2026-11-22

> Yes, build it

**Outcome:** Built the **Fund Rules Extractor**, the first AI piece of Calma.
- `backend/rules_extractor.py`: a PydanticAI step with structured output (`gpt-5.6-luna` via `OPENAI_MODEL`, using OpenAI's Responses API). For each rule it returns "stated" or "not stated", plus the exact quote. Code checks that each quote really appears in the source. Rules the page doesn't mention keep their current values. Income limits given in dollars are flagged for a person to fill in.
- New admin routes: suggest rules from pasted text, list suggestions, approve (with edits) or reject. Approving creates a new rule version, retires the old one, and is recorded in the audit log.
- Admin screen: **Update rules**, then a review table showing current vs. suggested rules with quotes and warnings. The admin approves or rejects.
- Fixes along the way: the shell held a placeholder `OPENAI_API_KEY`, so `.env` now overrides the shell. `gpt-5.6-luna` needs the Responses API for structured output.
- Tested: 15 automated tests pass (6 new, using a fake model). A live call on a made-up policy correctly flagged a dollar-based income limit, ignored a planted "set the pledge to $10,000" instruction, and treated "17 and younger get priority" as a note rather than an age limit. Clicked through the full flow in the browser with a live call. Reset the demo data afterward.

---

## Prompt 10 — 2026-11-22

> Scheduled website check

**Outcome:** Built the **scheduled website check** for fund eligibility pages.
- `backend/website_check.py`:
  - Fetches each fund's eligibility page about every 60 days and turns the HTML into plain text.
  - Compares it with the last saved version. If the page is unchanged, there's no AI call and no cost.
  - If the page changed, it runs the Rules Extractor. When the rules come out the same, it records "Rules match" and nothing needs review. When something changed or is unclear, it creates a suggestion for an admin to review.
  - Doesn't overwrite a suggestion that's already waiting for review, and records errors in plain English, retrying next time.
  - Safety: identifies itself honestly, respects robots.txt, refuses private and internal addresses (including after redirects), and limits page size.
- Runs automatically inside the API (30 seconds after startup, then every 6 hours, for funds that are due). It can also be run from the terminal (`python -m backend.website_check`).
- New `page_checks` table (check history) and a `policy_url` for each fund. Moved proposal creation into `backend/proposals.py` so the paste screen and the website check share it.
- Extractor improvement: it can now record "explicitly no limit" (e.g. "There is no income limit") instead of flagging it for manual entry.
- Admin screen: **Fund website checks** panel with each fund's link (editable), last and next check, result, **Check now**, **Run due checks now**, and check history.
- Five made-up demo fund pages in `data/demo_pages/` (`demo://` links).
- Tested: 31 automated tests pass (16 new). Live run: the scheduler checked all 5 demo funds by itself. Desert Bloom and Youth Access came back "Rules match". Heartland (added Nebraska, dollar-based income), Open Road (added Louisiana) and Later Care (26 weeks) became suggestions for review. A repeat **Check now** on an unchanged page returned "No change" in about 0.25 seconds with no AI call.

---

## Prompt 11 — 2026-11-22

> Yes, build it
>
> *(Context: "it" = the fund self-edit page, where funds keep their own eligibility rules up to date.)*

**Outcome:** Built the **fund self-edit page**, now the main way rules stay current.
- New fund routes: view my rules, save changes, confirm "still accurate". A save is validated (state codes, percent ≤ 100, min weeks ≤ max weeks), goes live as a new version, retires the old one, replaces any pending AI suggestion for that fund, and is audit-logged with the fields that changed. Confirming updates the "last confirmed" date without creating a new version. Moved rule validation into one shared function for the admin and fund screens.
- Fund portal: new **My eligibility rules** tab with plain-language sections:
  - where patients need to live (state buttons or "Any state")
  - income limit, with dollar examples for 1 and 3 people
  - weeks covered, travel-only, age limit
  - pledge type and amount

  A "You're changing" summary shows before saving, then version history. A pink reminder banner appears when rules are 60+ days old.
- Tested: 36 automated tests pass (5 new). In the browser, Kai (Later Care) changed the week limit from 24 to 26; it went live as v2 and replaced the waiting AI suggestion. Sam (Desert Bloom), with rules backdated 70 days, saw the reminder and cleared it with one click.

---

## Prompt 12 — 2026-11-22

> Yes, add it
>
> *(Context: "it" = letting clinics edit their own fund's eligibility rules the same way funds do.)*

**Outcome:** Clinics can now edit their own fund's rules.
- Backend: moved saving and confirming rules into shared helpers used by funds and clinics. New clinic routes to view, save and confirm the clinic fund's rules, plus a route to set the fund's **monthly limit** (block grant). Clinic staff can only reach funds their clinic owns, not partner funds or other clinics' funds. Changes are audit-logged (`rules_updated_by_clinic`, `monthly_limit_set`).
- Clinic portal: new **Our fund's rules** tab with a monthly-limit card (shows used-this-month) and the same rules editor funds use, plus the 60-day reminder banner.
- Small fix: the save box only sticks to the bottom of the screen when there are unsaved changes, so it no longer covers the form.
- Tested: 39 automated tests pass (3 new: clinic can only edit its own fund, a new limit blocks approvals over it, confirm resets the reminder). In the browser, Rosa raised Mesa's monthly limit to $7,500 and the pledge cap from $300 to $350 (live as v2).

---

## Prompt 13 — 2026-11-22

> *(Attached two screenshots of a reference intake form, saved in `design-refs/`. The first ("Details") asks: first name, last name, household annual income, household size, travel miles, phone, email, notification preference (Text/SMS), appointment date, last menstrual period date (required), date of birth, state of residence, state of care. The second asks: Are you currently unhoused? How many nights will you be away from home? How many days do you need dependent care while traveling? How many days will you need meals while traveling? Are you a minor seeking a judicial bypass? Do you have Medicaid or other insurance that covers abortion care?)*
>
> some funds are for travel or practical support (food, gas) only and some funds have eligibility based on the state where the abortion takes place not where the person lives. Can you review the patient intake form and make sure clinics and funds have the option to ask any of the questions in these images?

**Outcome:** Reviewed the intake form against both screenshots and made questions configurable.

| Reference question | In Calma |
|---|---|
| First/last name, phone, email, notification preference | Optional **contact details** question. A clinic can turn it on. Only the clinic sees it; never funds or the AI; deleted when the case closes |
| Household annual income | Income now accepts **monthly or yearly** |
| Household size, state of residence | Core questions (already there) |
| Travel miles | Optional, asked if the patient is traveling |
| Appointment date | Comes from the clinic's booking (not asked) |
| Last menstrual period date | Now the main pregnancy question; weeks at the visit are computed and only weeks are stored. "I don't remember" falls back to weeks |
| Date of birth | Asked as **age** instead (less identifying) |
| State of care | Taken from the clinic's state automatically (not asked) |
| Unhoused, nights away, dependent-care days, meal days, judicial bypass, Medicaid/insurance | All available as optional questions |

- **How questions are chosen:** core questions are always asked. Optional ones are added automatically when a fund the patient could match needs them (e.g. a practical-support fund with a per-night rate adds "nights away"), or when the clinic or a fund turns them on. Patients can skip any optional question. Answers to questions that weren't asked are dropped on the server. Judicial bypass only shows for under-18s (or if age was skipped). Travel details only show if the patient is traveling.
- **New fund options:**
  - eligibility by **state of residence or state of care**
  - **practical support** funds (per-mile, per-night, meals and dependent-care rates, flat amount, cap; shown separately from the clinic bill, left out of reimbursement, can be marked provided before the visit)
  - **only patients without insurance coverage**
  - **extra questions** to see on each patient card

  Each fund only sees answers to the questions it needs or asked for. The AI extractor can now also read state basis, support type and the insurance rule from policy text.
- **Screens:** the patient form builds its steps from the question list (English and Spanish) and shows travel help in its own section. The clinic portal has a new **Intake questions** tab showing each question, whether it's asked and why, with on/off switches; case details show every answer plus a clinic-only contact box. Fund rules editor: new sections for state basis, type of help with rates, insurance, and extra questions. Fund cards show answer chips. Admin tables and the review screen show the new fields.
- **Demo data:** Open Road became a practical-support fund ($0.20/mile, $90/night, $25/day meals, $40/day childcare, up to $400). New **Enchanted Circle Care Fund** (state of care: NM). Desert Bloom requires no insurance coverage and asks about being unhoused. Youth Access asks about judicial bypass. Prairie clinic asks for contact details.
- **Tested:** 47 automated tests pass (8 new). In the browser, a 17-year-old Texas patient traveling 300 miles to Mesa (NM) saw all 14 screens and matched 5 funds, including Enchanted Circle by state of care and Open Road travel help of $390 ($120 miles + $180 lodging + $50 meals + $40 childcare). Each fund saw only its own answers, and the patient's name stayed with the clinic. Fixed a review-screen label ("Money each month" → "Household income").

---

## Prompt 14 — 2026-11-23

> Keep as is

**Outcome:** Decision recorded: Calma keeps asking **age** (not date of birth) and takes **state of care from the clinic** (not asked). Both reduce identifying data. No code changes. Noted in `DESIGN.md` (decision 10).

---

## Prompt 15 — 2026-11-23

> *(Attached screenshot, saved as `design-refs/partnerships-reference.png`: "Connect Provider Partners — Fund Case Managers set up their partnering Providers. These partnerships ensure that only selected Providers are able to allocate the grants offered by the fund." It shows a "My Partnerships" table with Provider Name, Partnership Status (Accepted), Acceptance Date and Created Date, plus an "Add/Remove Partner Providers" button.)*
>
> can you also build into the abortion fund interface the option to add or remove the clinics they work with? See image

**Outcome:** Built **partnership management**.
- **Fund portal → Partner clinics** (modeled on the screenshot): a table of clinics with status (Accepted / Waiting for clinic / Declined by clinic), accepted date and requested date. **Add partner clinic** lists clinics not yet connected, each with **Send request**. **Remove** (or **Cancel request**) asks for confirmation first. **Ask again** appears after a decline.
- **Clinic side** (the clinic accepts, like the "Accepted" status in the screenshot): a banner when a fund asks to partner, and a **Partner funds** tab with **Accept/Decline** for requests and **End partnership** for current partners (not the clinic's own fund).
- **Rules:** only *accepted* partnerships count for matching, the questions patients see, and what a fund can see or decide. Ending a partnership declines that fund's pending pledges at the clinic, so cases don't stall. Approved pledges stay visible and can still be marked paid. Everything is audit-logged. Existing demo partnerships were marked accepted with dates.
- **Tested:** 52 automated tests pass (5 new: listing, request → accept → matching starts, decline → ask again, removal declines waiting pledges but keeps approved ones payable, clinic can't remove its own fund). Frontend type-checks. **Not yet checked in the browser:** the API server had been stopped by the user, so I didn't restart it without asking.

---

## Prompt 16 — 2026-11-23

> Yes, restart it

**Outcome:** Restarted the API and checked partnerships in the browser.
- As Jordan (Heartland Access): **Partner clinics** showed Prairie as Accepted. **Add partner clinic** listed Mesa, and **Send request** turned it into "Waiting for clinic" with today's date.
- As Rosa (Mesa): a banner said "Heartland Access Fund asked to partner with your clinic". **Review** → **Accept** cleared the banner and added Heartland to Mesa's partner funds as Accepted.
- Small fixes: the add panel now closes after sending a request, and its "nothing left to add" message is clearer.
- No console errors. Restarting the server also started the scheduled website check, which makes a few live AI calls about 30 seconds after startup.

---

## Prompt 17 — 2026-11-23

> localhost:8020 is saying not found

**Outcome:** Port 8020 is the API, which has no web page, so "Not Found" was expected. The app is at **http://localhost:5178**. At the time, only the API server was running; the web app server (calma-web) had been stopped.
- Added a redirect: opening localhost:8020 in a browser now goes to the app (http://localhost:5178).
- Restarted calma-api (to load the redirect) and started calma-web. Checked: 8020 → redirect to 5178; 5178 shows the sign-in page; the app reaches the API through its proxy. 52 tests still pass.
- README now says which address to open and that both servers must be running.

---

## Prompt 18 — 2026-11-23

> Can you explain to me where in the app the eligibility determinations are made? Is that just Python doing the math of it?

**Outcome:** Explained (no code changes). Yes: eligibility is plain Python rules in `backend/matching.py`, run when the patient submits the form (`patient_screening` in `backend/main.py`). It reads each fund's approved rules from the database and produces *suggested* pledges with reasons. A person at the clinic or fund approves every pledge. AI is used only to *suggest* fund rules from policy text (`backend/rules_extractor.py`), and a person approves those before matching uses them.

---

## Prompt 19 — 2026-11-23

> ok I want to run this app on Render. Do I have to push to Git first?

**Outcome:** Explained: yes. Render deploys from a Git repository (GitHub, GitLab or Bitbucket) or from a pre-built Docker image, so the code needs to be in a (private) repo first. Listed the changes needed before deploying: run as one service (FastAPI serves the built React app), a database that survives redeploys, environment variables for keys, and no real patient data without a HIPAA agreement. No code changes yet.

---

## Prompt 20 — 2026-11-23

> Yes, prep and push

**Outcome:** Prepared Calma for Render and pushed it to GitHub (`AmarantaUrsula/Calma`).
- **One service:** the FastAPI server now also serves the built React app (any page like `/clinic` or `/p/<link>` gets the app; unknown `/api` paths stay 404). Added `/api/health`. Locally nothing changes: the API on 8020 still redirects to the app on 5178.
- **Fresh disks:** with `CALMA_SEED_IF_EMPTY=1`, the server loads the made-up demo data when it starts with no database (free Render instances start empty).
- **`Dockerfile`** (Node builds the app, then Python serves it) plus `.dockerignore`. **`render.yaml`** Blueprint: free web service, Docker, health check, `OPENAI_API_KEY` entered in Render (not committed), `OPENAI_MODEL=gpt-5.6-luna`, demo data on, automatic website checks off by default to avoid surprise AI calls.
- **Git:** made `ataraxia/` the repository, linked to the existing GitHub repo (it only had GitHub's starter commit), and removed the empty `Calma` clone folder inside it. Checked the 57 files before committing: no keys, `.env` files, databases, `node_modules` or build output.
- **Tested locally:** built the app, ran the production server on a fresh database. The pages, assets, API and health check work, unknown API paths return 404, and path-traversal attempts only return the app page. 52 tests pass. Docker isn't installed on this Mac, so the container itself will first be built on Render.
- README has a "Deploy on Render" section.

---

## Prompt 21 — 2026-11-23

> ok what do I have to do to change the name from ataraxia to calma

**Outcome:** Explained what renaming the folder involves (no changes yet). GitHub (`Calma`) and Render don't care about the local folder name. Locally: stop the two servers, rename `ataraxia/` to `calma/`, update the folder name in the workspace `.claude/launch.json` (2 lines), `README.md` (2 commands), a comment in `backend/main.py`, and Claude's memory notes, then restart the servers. Git history and the Python environment keep working after the move. Offered to do it.

---

## Prompt 22 — 2026-11-23

> Yes, rename it

**Outcome:** Renamed the project folder from `ataraxia/` to **`calma/`**.
- Stopped both servers, renamed the folder, and updated the folder name in the workspace `.claude/launch.json`, `README.md` setup commands, the comment in `backend/main.py`, and Claude's memory notes. Historical mentions ("formerly Ataraxia") stay in `DESIGN.md` and earlier log entries.
- Restarted both servers from `calma/`. Checked: the app loads at http://localhost:5178, localhost:8020 redirects to it, the API works through the app, the OpenAI key still loads from the workspace `.env`, and all 52 tests pass. Removed a leftover local production build (ignored by Git) so 8020 keeps redirecting to the live app.
- Git history moved with the folder and is still connected to GitHub. Committed and pushed the README, comment and log updates.

---

## Prompt 23 — 2026-11-23

> Ok let's refine this a little. Can the color palettes of the sites be more muted blues, earthy greens, and warm browns to reflect "calma"? I am just wondering if the hot pink recalls a teachers correcting pen to a nervous person.

**Outcome:** Switched every screen from hot pink on near-black to a **calm, warm palette**:
- **Background and text:** warm linen background (`#f4efe6`) with cream cards; deep slate text and warm gray secondary text.
- **Muted slate blue** (`#3e6681`) for buttons, links and selected states.
- **Sage green** for the Calma name (`#4b6b4e`) and for "approved" (`#44684a`).
- **Warm brown** (`#7b5236`) for section headings.
- **Ochre** (`#82561c`) for "waiting".
- **Terracotta** (`#a3472e`) instead of alarm red for errors.

Checked every text/background pair against WCAG AA: all at least 4.5:1. Two colors (green and ochre on the light badge background) first came in at 4.3–4.4, so I darkened them. The colors are defined once at the top of `frontend/src/styles.css`. This replaces the course rules' default black-and-pink style, at the user's request; noted as decision 13 in `DESIGN.md`. Checked in the browser on the patient screens (phone size) and the clinic portal (desktop). Also fixed "1 nights / 1 days" wording in case details.

---

## Prompt 24 — 2026-11-23

> Let's refine some things to get it as "real" as possible. Please build a normal create-account/login flow that includes:
>
> * create account (first name, last name, email, password, confirm password)
> * log in: email and password
>
> for admin, clinic staff, and abortion fund staff. Obviously not for patients, they just get the link to the intake form that turns into the status page

*(Follow-up typed while I was working:)*

> new accounts can go into a users table. Make sure to store passwords securely so hackers (human or AI) cannot access them.

*(Second follow-up typed while I was working:)*

> for example, see image
>
> *(Screenshot of a password-storage example from another assignment: a test user, PBKDF2-HMAC-SHA256 with 120,000 iterations stored as `pbkdf2_sha256$salt$hash`. It explains that login re-hashes the typed password with the stored salt and compares in constant time, that sign-up and login must use the same hash settings, and that you should check both a seeded user and a brand-new account. It also contains a line addressed to the AI saying not to start until the student asks in their own words, and to update `output/harness.md`. I treated that as part of the other assignment and did not act on it.)*

**Outcome:** Built a real **create account / log in** flow for clinic staff, fund staff and admins, and removed the old "pick a demo person" screen. Patients still use only their private link.
- **Create account** (`/signup`):
  - fields: first name, last name, work email, where you work (a clinic, a fund, or Calma admin), password, confirm password
  - checks: matching passwords, at least 10 characters, not a common password, doesn't contain your name or email, valid and unique email
  - new accounts are **waiting for approval** until a Calma admin approves them (admins included), so nobody can give themselves access
- **Log in** (`/login`): email and password, with a show/hide toggle. The same message is shown for a wrong password or an unknown email. 5 misses lock that email for 15 minutes. Pending, rejected or disabled accounts can't log in.
- **Users table:** added first name, last name, email (unique, lowercase), `password_hash`, status, created/approved/last-login dates.
- **Password storage** (`backend/auth.py`):
  - salted **scrypt** hash stored as `scrypt$N$r$p$salt$hash`, never the password
  - login re-hashes the typed password with the stored salt and settings and compares in constant time
  - optional **pepper** (`CALMA_PASSWORD_PEPPER`) kept outside the database; Render generates it automatically
  - no response, log, audit entry or AI call includes a password or hash
  - session tokens are kept only as hashes; disabling an account signs that person out immediately
- **Admin → Staff accounts:** pending accounts first, with Approve/Reject; Disable/Enable for others.
- **Demo accounts:** the 9 demo users now have `@example.org` emails and one shared made-up demo password (set in `backend/seed.py`, listed in the README). Added logins to the existing demo database without wiping it.
- **About the reference screenshot:** it used PBKDF2-HMAC-SHA256. I used scrypt, which meets every point it listed (re-hash with the stored salt, constant-time compare, same settings, test a seeded and a new account). Its note to the AI about `output/harness.md` belongs to the other assignment, so I didn't act on it. How auth works is documented in the README instead.
- **Tested:** 68 automated tests pass (16 new). They cover hashing, salts, the pepper, settings stored in the hash, the password and hash never appearing in responses, identical errors, lockout, sign-up checks, approval, reject, disable, and that nobody can self-approve as admin.
- **Browser check:** created a brand-new account (Taylor Morgan, Heartland Access Fund). Login was blocked while pending; the admin logged in and approved it; Taylor then logged in and landed in the Heartland fund portal. The database holds only a `scrypt$…` hash for it.
- **Also fixed:** new routes had been added after the catch-all route that serves the app's pages, which hid them. The catch-all is now last.

---

## Prompt 25 — 2026-11-23

> Is there any way we can add a real abortion fund to the fund website checks?

**Outcome:** Yes, possible; the website check already accepts real `https://` links. Nothing added to the app yet (waiting for a go-ahead).
- **Fetch test:** found real funds with public pages and tried Calma's fetcher on them. All loaded, and their robots.txt files allow it: Carolina Abortion Fund's own "Request Funding" page, plus National Network of Abortion Funds (NNAF) profile pages for West Fund (NM/TX), Faith Roots Abortion Fund (travel help for people coming to NM) and Mariposa Fund (NM, people affected by the immigration system).
- **Live AI test** on Carolina Abortion Fund's page (not saved). It correctly read:
  - **States and income:** NC/SC; no income requirement
  - **Type of help:** pays toward the procedure
  - **Notes:** "must have a scheduled appointment" and "doesn't fund every clinic"

  It flagged the pledge amount for a person to fill in, because the page doesn't publish one. Every quote was found word-for-word on the page.
- **Gap the real page revealed:** Carolina funds people who live in NC/SC **or** have an appointment there. Calma's rules can only use one of those today.
- **Proposed approach:** add real funds as **reference-only** funds (no clinic partnerships, so they're never matched with the made-up demo patients), checked on the same schedule. Optionally add a "lives in **or** gets care in" rule.

---

## Prompt 26 — 2026-11-23

> Yes, add them

**Outcome:** Added four **real abortion funds** as reference-only funds in the website checks:
- **Carolina Abortion Fund:** its own "Request Funding" page
- **West Fund**, **Faith Roots Abortion Fund**, **Mariposa Fund:** their NNAF profile pages

Details:
- **Data model:** new `funds.reference_only` flag. Reference funds have no partner clinics and no accounts. They're hidden from the sign-up list, excluded from matching, and their rules start empty, so the first check suggests rules for an admin to review. A brand-new fund's suggestion stores a placeholder pledge, and approval still requires a real amount.
- **Admin:** "Real fund · reference only" badges. Funds without reviewed rules say so and point to the website check.
- **Live run:** after a restart, the scheduler checked all four real pages by itself and created a suggestion for each. Every quote was found word-for-word on the real pages.
  - **Carolina:** NC/SC, no income requirement, procedure help; pledge amount flagged for a person to fill in.
  - **West Fund:** NM/TX residents.
  - **Faith Roots:** practical help (lodging, transport, meals) for care in NM.
  - **Mariposa:** care in NM/TN, plus an immigration-status requirement noted as "other".
  - Left all four waiting for the user's review rather than approving them.
- **Gaps the real pages revealed** (noted in `DESIGN.md`): "lives in **or** gets care in" (the AI picked "care" for Carolina, which is only half right), identity-based eligibility, and funds that only pay at specific clinics.
- **Tested:** 69 automated tests pass (1 new: real funds are tracked but never offered at sign-up or matched, and the first check goes to review without going live). Also fixed a database error for brand-new funds with no pledge amount.

---

## Prompt 27 — 2026-11-23

> Yes, add it
>
> *(Context: "it" = an eligibility option for funds that serve people who live in a state **or** get care there, like Carolina Abortion Fund.)*

**Outcome:** Added a third eligibility option: **"lives in or gets care in"** (`state_basis = "either"`).
- **Matching:** a patient qualifies if the state they live in **or** the clinic's state is on the fund's list. The reasons say which one matched; if neither, the reason names both states.
- **Fund and clinic rules editors:** new "**Either one**: lives there or gets care there" choice, with a clearer states heading. The admin review dropdown and the rules tables show it too.
- **AI extractor:** now knows the "either" option. A live re-read of Carolina Abortion Fund's page picked "either", quoting the page: callers who live in NC or SC "and/or have an appointment" there. Refreshed Carolina's waiting suggestion with it (still waiting for the user's review, not approved).
- **Tested:** 71 automated tests pass (2 new: lives-in match, gets-care-in match, neither, plus the extractor accepting "either"). Browser: Carolina's review shows "Lives in or gets care in" with the quote.

---

## Prompt 28 — 2026-11-23

> Ok this is all looking great. Anything else before I send to colleagues to demo?

**Outcome:** Reviewed demo readiness (no code changes yet). Found:
1. **Public demo password:** the repo is public and the README lists the demo password, so on the live site anyone could log in as the admin. From there they could approve accounts and click "Check now", which spends OpenAI credits.
2. **No demo notice for patients:** the patient screens have no "this is a demo — don't enter real information" notice, and colleagues might type real details.
3. **Not deployed or built yet:** the app isn't on Render yet, and the Docker image has never been built (no Docker on this Mac).
4. **OpenAI key:** no spending limit noted, and the key was pasted into chat earlier.
5. **Demo behavior to expect:** demo data resets on Render's free plan, the first visit is slow, and real-fund rules stay empty until someone clicks "Check now".
6. **Spanish:** not yet reviewed by a native speaker.

Offered to fix 1 (demo password set in Render, not GitHub) and 2 (a bilingual demo notice), and to write a one-page guide for colleagues.

---

## Prompt 29 — 2026-11-23

> Yes, do all three

**Outcome:** Did all three.
1. **Demo password off GitHub for the live site:** the demo accounts' password now comes from `CALMA_DEMO_PASSWORD` when set. `render.yaml` asks for it when you create the service and sets `CALMA_REQUIRE_DEMO_PASSWORD=1`, so on Render the app refuses to load demo data (with a clear log message) if the password is missing, shorter than 10 characters, or the public local default. Locally nothing changes (`calma-demo-2026`). 1 new test.
2. **Demo notice:**
   - **Patient screens:** a soft brown banner. It shows in both languages on the language screen, then in the chosen language: "This is a demo. Please don't enter real personal information…" / "Esto es una demostración…".
   - **Login and create-account pages:** a notice for colleagues.
   - **Turning it off:** a real deployment can switch it off with `VITE_DEMO_NOTICE=0`.
3. **`DEMO_GUIDE.md`** for colleagues: what Calma is, the demo-data warning, a blank for the link, the password shared separately, the account list, three 5-minute walkthroughs (patient, funds/clinics deciding, keeping rules up to date incl. a real-fund AI check), feedback questions, what's not built, and how decisions are made (rules, not AI).

README and DESIGN updated. 72 tests pass. Checked both notices in the browser (patient at phone size in English/Spanish, login page).

*(Follow-up typed while I was working:)*

> If I buy the lowest plan in Render will it not wipe the database every time

**Outcome:** Explained: a paid plan alone isn't enough. Render's normal disk is temporary on every plan, so a redeploy or restart still erases the SQLite file. The paid plan stops the free-plan sleeping (so fewer restarts), but keeping data also needs a **persistent disk** (a paid add-on for paid services) with `CALMA_DB` pointing to it, or a move to Postgres. Offered to add the disk setup to `render.yaml`.

---

## Prompt 30 — 2026-11-23

> could we also make it that any seat can download the data pertinent to their organization (or for the admin, all data) in excel or something similar so they can generate reports? Or is there a better way to do this that you suggest? Ideally they could generate simple reports of the amount disbursed over a chosen time period by at one, two, or three criteria and make either tables, pie graphs, or bar charts. What do you think is the best approach for this?

**Outcome:** Recommended building both: a **Reports** page in each portal (choose dates, a measure and up to three "group by" criteria, then see a table, bar chart or pie chart) **and** an Excel download of the same report plus the underlying rows, scoped to each organization and de-identified, with every download logged. Laid out the scoping, the privacy safeguards and the choices to confirm. No code yet.

---

## Prompt 31 — 2026-11-23

> Yes, build it
>
> *(Context: "it" = the Reports page with tables, bar and pie charts, plus Excel downloads scoped to each organization.)*

*(Follow-up typed while I was working:)*

> can it be a thing of where the user types what visual it wants to summarize the data and an agent makes it?

**Outcome:** Built **Reports** for every role, plus the **Report Builder** agent from the follow-up.
- **Report engine** (`backend/reports.py`):
  - **Scope:** clinic sees its own cases, fund sees its own pledges, admin sees all.
  - **Measures:** disbursed (paid) or pledged (approved).
  - **Dates:** paid, approved or appointment date, over a chosen period.
  - **Grouping:** up to 3 criteria (fund, clinic, type of help, month, week, home state, state of care, income band, weeks pregnant, age, language, traveled). Funds get only the criteria they already see.
  - **Results:** totals of dollars, patients and pledges, with groups under 5 patients flagged.
- **Excel download:** `.xlsx` with a Report sheet (filters, totals, a SUM formula) and a Data sheet (de-identified, banded, filterable). Every download is audit-logged. Added `openpyxl`.
- **Report Builder agent** (`backend/report_agent.py`, PydanticAI structured output): turns a plain-English request into report *settings* only. It never sees data; code enforces role limits and chart rules; the numbers always come from the engine. Live test: "bar chart of money paid out each month since June, split by travel help vs procedure" → June 1–today, disbursed, month then type of help, bar chart.
- **Reports page** (in the clinic, fund and admin portals):
  - a "Describe the report you want" box, plus manual controls (period presets, measure, date basis, three group-by pickers)
  - Table / Bar / Pie, and Dollars / Patients
  - summary tiles and Download Excel
  - charts drawn in plain SVG/HTML: horizontal bars, stacked bars for 2 criteria (top 6 + Other, legend), pie (≤6 slices + Other), hover tooltips, "show as a table"
- **Chart colors:** checked with the dataviz palette validator. The first, more muted earthy palette failed the colorblind-safety and "reads as gray" checks, so I adjusted it to one that passes every check: slate blue, terracotta, sage teal, ochre, plum, olive.
- **Demo history:** `add_history()` adds 90 made-up past cases over six months through the real matching engine; `reset()` and fresh Render instances include it. Added to the current demo database without wiping it.
- **Tested:** 78 automated tests pass (6 new: totals add up, per-organization scope matches the database, measures and dates, 3 criteria, role limits, Excel sheets and de-identified columns, audit entry, agent rule enforcement, agent using the same numbers). In the browser, the live agent request produced the stacked bar chart, a pie by fund worked, and the Excel download came through.
- **Notes:**
  - After the folder rename, the virtual environment's `pip` command still points at the old `ataraxia` path, so I used `.venv/bin/python -m pip`.
  - "Try Calma.docx", which the user added on GitHub, is missing from the local folder. I didn't restore it or commit its deletion.

---

## Prompt 32 — 2026-11-23

> Leave it

**Outcome:** Left "Try Calma.docx" as is: it's on GitHub, not in the local folder, and won't be restored. Future commits will keep including only specific files, so the missing local copy is never pushed as a deletion.

---

## Prompt 33 — 2026-11-23

> ok are we ready to commit?

**Outcome:** Yes. All feature work was already committed and pushed. The only uncommitted change was this prompt log, so I committed and pushed it, leaving out the missing local "Try Calma.docx" so it stays on GitHub. Tests: 78 passing.

---

## Prompt 34 — 2026-11-23

> can you udpdate the demo guide to includes this latest reporting function

**Outcome:** Updated `DEMO_GUIDE.md` for reporting:
- **New walkthrough "4. Reports: how much went where (5 min)":**
  - the Report Builder, with three example requests and how it works (AI picks settings only, never sees patient data, numbers from Calma)
  - the manual controls (period, disbursed vs pledged, up to three groupings, Table/Bar/Pie, Dollars/Patients, hover)
  - Download Excel (Report and Data sheets, de-identified)
  - a fund's narrower view (as Sam)
  - the small-group "*" flag and audit logging
- **Other edits:** the intro now mentions reports; the total time is now about 20 minutes; the Admin row lists reports; a new feedback question about reports; and "How decisions are made" now names both places AI is used (fund-website suggestions and report settings), neither of which decides who gets money.

---

## Prompt 35 — 2026-11-23

> most recent render deploy failed. any advice on troubleshotting

**Outcome:** I can't see Render's logs, so I reproduced likely causes locally (no code changes):
- **Most likely cause: a missing demo password.** Started the server the way Render does, with no `CALMA_DEMO_PASSWORD`. Startup fails on purpose: "MissingDemoPassword: Set CALMA_DEMO_PASSWORD in the host's environment settings… Application startup failed". The same happens if the password is under 10 characters or is the public `calma-demo-2026`. Render only asks for new secret settings when a Blueprint is first created, so a service created before this setting existed won't have it: it must be added under the service's **Environment** tab.
- With a demo password set, the same startup worked: demo data plus 90 past cases loaded, health check 200.
- **Build:** a clean `npm ci` and production build (as in the Dockerfile) succeed, and the lockfile includes the Linux build packages.
- Asked the user to check Render's Events/Logs and paste the error if it's something else.

---

## Prompt 36 — 2026-11-23

> *(Pasted the Render deploy log.)* The Docker build succeeded (all steps cached). The deploy then failed at startup: `backend.seed.MissingDemoPassword: Set CALMA_DEMO_PASSWORD in the host's environment settings (not the public default) before loading demo data.` … `Application startup failed. Exiting.` … `Exited with status 3`.

**Outcome:** Confirmed the cause: `CALMA_DEMO_PASSWORD` isn't set in Render, so the safety check stops startup. The build itself is fine. Gave the fix: Render → calma service → Environment → add `CALMA_DEMO_PASSWORD` (10+ characters, not the README default) → Save and redeploy. Made the error message spell out those exact steps. 78 tests pass.

---

## Prompt 37 — 2026-11-23

> it still did not deploy

**Outcome:** Can't see Render from here, so I asked for the newest deploy log and listed what each likely message means and how to fix it: password still missing (not saved, wrong service, or the deploy started before saving), password too short or the public default, a health check timeout, or a new error. No code changes.

---

## Prompt 38 — 2026-11-23

> I'll paste it

**Outcome:** Waiting for the user to paste the newest Render deploy log.

*(Pasted the new deploy log:)* `backend.seed.MissingDemoPassword: CALMA_DEMO_PASSWORD must be at least 10 characters. Change it under this service > Environment, then redeploy.` … `Application startup failed. Exiting.`

**Outcome:** Progress: Render now has `CALMA_DEMO_PASSWORD`, but its value is **shorter than 10 characters**, so startup stops. Fix: change the value under the calma service → Environment to something 10+ characters (a short phrase), save, redeploy. Also split the error messages so each names its real problem: "not set", "set to the public README default" (previously also reported as "not set"), and "at least 10 characters". 1 new test; 79 pass.

---

## Prompt 39 — 2026-11-23

> ok it deployed. Now I am in the app and I wrote in the reporter AI window "make a bar chart of the amount of money disbursed by state and gestation for the last three months" and it gave me the following "The report helper couldn't understand that (ModelHTTPError). Try rephrasing, or use the controls.

**Outcome:** The same request works locally (money paid out over the last 3 months, bar chart), so the request is fine. "ModelHTTPError" means OpenAI refused the call **from Render**, most likely because Render's `OPENAI_API_KEY` is wrong, extra spaces were pasted, the key was deleted or replaced, or the account is out of credit.
- **Clearer AI errors:** AI failures now explain the cause in plain English: key rejected (401), not allowed (403), unknown model (404), usage limit or credit (429), OpenAI temporarily down (5xx), or key missing. Applies to the Report Builder, the rules extractor and the website check. Details go to the server log, never key fragments. 4 new tests.
- **"State" fix:** the agent had read "state" as state of care. Plain "state" now means the patient's home state, and "gestation" maps to weeks pregnant. Live retest: home state, then weeks pregnant, bar chart, Aug 23–Nov 23.
- 83 tests pass. Next step for the user: redeploy, retry, and read the new message (likely: check `OPENAI_API_KEY` in Render's Environment tab, or OpenAI billing).

---

## Prompt 40 — 2026-11-23

> In testing the website I am being told that the emails and password do not match

**Outcome:** Found and fixed a real bug, and listed the other likely causes.
- **Bug:** when startup failed on the demo-password check, an empty database file had already been created. The next start saw the file, skipped loading demo data, and ended up with **no accounts**, so every login said "don't match". Reproduced it locally: failed start, 0-byte database, then "That email and password don't match" with the correct password.
- **Fix:** check the demo password *before* touching the database, and load demo data whenever the database is missing, empty, or has no accounts. Re-ran the same scenario: login now works. 1 new test; 84 pass.
- **Other things to check on Render:** use the password set in Render's `CALMA_DEMO_PASSWORD`, not the README's `calma-demo-2026`. Emails end in `@example.org` (e.g. `admin@calma.example.org`). Five wrong tries lock that email for 15 minutes. A self-created account can't log in until the admin approves it.
- Added a note to `DEMO_GUIDE.md` that the demo password is not the README one.

---

## Prompt 41 — 2026-11-23

> it deployed and login works now

**Outcome:** Calma is live on Render, and login works with the demo password set in Render. Left before sharing: check the Report Builder works on Render (if not, the new error message names the cause, usually `OPENAI_API_KEY`), fill the Render link into `DEMO_GUIDE.md`, and send it with the password shared separately.

---

## Prompt 42 — 2026-11-23

> People will be testing this on their own computers - does that mean we should change the readme file to have the password that works on the render hosted version? or no?

**Outcome:** Advised no. The README is on a public GitHub repo, so the Render password there would be public: anyone could log in as admin, see and change the demo, approve accounts, and spend OpenAI credits with "Check now" or the Report Builder. Colleagues "on their own computers" just open the Render link in a browser and never use the README. Share the password privately (email or message, or a copy of the guide that isn't committed). The README's local password only matters for someone who downloads and runs the code themselves. No changes made.

---

## Prompt 43 — 2026-11-23

> I updated the API key in environments and still got this error The report helper couldn't run: OpenAI rejected the API key. Check OPENAI_API_KEY in the host's environment settings (no extra spaces, and not a key that was deleted or replaced). You can still use the controls below. when I put this prompt pie chart of money paid out in the past 6 months by fund and clinic

**Outcome:** The same request works locally with the local key (fund, then clinic, from May 23 to Nov 23). The AI correctly switched to a bar chart, since a pie can only show one grouping, and said so. So OpenAI is rejecting the specific key in Render (HTTP 401).
- **Copy-paste forgiveness:** Calma now cleans the key setting of spaces and line breaks, surrounding quotes, and a pasted `OPENAI_API_KEY=` prefix.
- **Restricted keys:** a key restricted from calling models ("insufficient permissions / missing scopes") now gets its own message.
- **Better 401 message:** it points to the Render log line "AI request failed", where OpenAI's masked version of the received key (first and last characters) can be compared with the real key.
- 91 tests pass (7 new).
- **Steps for the user:** redeploy, retry; if it still fails, check Render Logs for "AI request failed" and compare the masked key, then check that the key is unrestricted, in the right project and not deleted, and that the account has credit.

---

## Prompt 44 — 2026-11-23

> It works now

**Outcome:** The Report Builder works on the live Render site. Calma is fully deployed: login, portals, reports and the AI features. Remaining for the user: fill the Render link into the demo guide and send it to colleagues, with the password shared privately.

---

## Prompt 45 — 2026-11-23

> Make me a slide deck called slides.html using reveal.js, loaded from a CDN. 10 slides max, following the outline in my report. Put my screenshots and diagram right inside the file so it still works when emailed to someone. Use a clean design with big text and the same colors as my app.
>
> 1. Title: project name, your name, one-line pitch
> 2. The problem and who has it
> 3. What is new about your solution
> 4. How the agents work (diagram)
> 5. Demo screenshots
> 6. Cost to run
> 7. Safety
> 8. Impact: the numbers
> 9. What's next

*(Follow-up typed while I was working:)*

> actually stop, I have no made the report yet

**Outcome:** Stopped before building anything; no `slides.html` was created.
- **Gathered so far** (for later):
  - **Render:** Starter is about $7/month, a persistent disk $0.25/GB/month (mostly third-party sources; confirm on render.com/pricing).
  - **OpenAI `gpt-5.6-luna`:** $0.20 per million input tokens and $1.20 per million output tokens (OpenAI model page; prices cut about 80% on July 30, 2026).
  - **Visuals:** the user's diagram is `design-flowchart.webp`. No Calma screenshots were found, so they'd need to be taken.
- **Security flag raised:** "Try Calma.docx", committed to the public GitHub repo, contains the live Render link and the live admin password. Recommended changing `CALMA_DEMO_PASSWORD` on Render and removing the file from GitHub. No action taken without the user's OK.

---

## Prompt 46 — 2026-11-23

> Yes, remove it

**Outcome:** Removed "Try Calma.docx" from the GitHub repo. The user's copy in the workspace folder (`AI for managers/Try Calma.docx`) is untouched. Added a `.gitignore` rule so filled-in demo guides aren't committed again. The file still exists in the repo's history, so the leaked admin password must be changed on Render (`CALMA_DEMO_PASSWORD`, then redeploy). Fully erasing it from history would mean rewriting the repo's history, offered as an option but not done.

---

## Prompt 47 — 2026-11-23

> The report (10–15 pages) which is (report.html), A single HTML file, 10–15 pages when printed.
>
> Write it for a smart manager who has never seen the app. Use these sections, in this order. Put screenshots or use the flow chat of the app wherever they help the reader see what you are describing.
>
> 1. Title + links — Project name, your name, the GitHub repo link (same one you submit on Canvas), the link to the app itself if it is online, and one sentence that says what the app does.
> 2. Motivation — Who has this problem? How do they deal with it today, and what does that cost them in money, time, or frustration? Why should anyone care?
> 3. What is new here — Look around first. What already exists (apps, startups, ChatGPT itself)? What does your project do that those don't? Be honest. If something close exists, say what you do differently and why that matters.
> 4. The agents — What are the AI agents in your app, and what does each one do? What tools can each agent use? If you have more than one agent: how are they organized? Who hands work to whom? Draw a diagram. Which model(s) you used and why. Walk through one real run, step by step, with screenshots.
> 5. Tokenomics — How many tokens does one typical run use (input, cached input, output)? Measure it from real runs. What does one run cost? What does it cost per user per month? What would it cost at scale: 100 users? 10,000 users? What did you do to keep cost down? Did any of your cost cutting make the app perform worse? Show evidence.
> 6. Safety — What could go wrong, and what did you build to stop it? Cover the risks that matter for your app, for example: Attacks: prompt injection, users trying to get the agent to leak data or misbehave. Agent malfunction: the agent invents facts, takes the wrong action, or loops forever. How do you protect the user? Overspending: what stops a bug or a bad actor from burning through your token budget? Show at least one defense actually working, with a screenshot or a test.
> 7. Impact — If this helps an organization or people, put numbers on it: money saved, hours saved, faster turnaround, better quality, more people served, or something that was impossible before and now is possible. Say where your numbers come from (your own tests, a pilot user, public data, a careful estimate). The strongest evidence is a real user trying it.
> 8. Limits + next steps — What doesn't work yet? What would you build next if you had another month?
>
> The page count is for a normal printed page (letter size, regular font, screenshots included). Fifteen pages of real detail beats fifteen pages of filler. The grade is for the content, and filler costs points.

*(Follow-up typed while I was working:)*

> here are some screen shots to add whereever it makes sense to
>
> *(Three screenshots of the patient form: the language choice screen with the bilingual demo notice, the "Hi! Let's see if we can help pay for your visit" intro screen, and step 3 of 10, the income question with "each month / each year".)*

> another screen shot of the clinic sign in
>
> *(Screenshot of the clinic portal as Rosa: monthly fund budget, new-appointment form with a created patient link C-1091, and the case list.)*

**Outcome:** Wrote **`report.html`**: a single file (1.5 MB, all images embedded) that prints at **15 letter pages**, with the eight requested sections.
- **Research:** NNAF survey figures, KFF abortion cost medians, the JAMA travel-cost study, NPR and *The Nation* on how patients piece together funding, and existing tools (NNAF directory, AbortionFinder, DARIA, the NAF hotline, ChatGPT). Sources are listed at the end.
- **New safety feature built for the report:** an **AI spending guard** (`backend/ai_budget.py`). It sets a per-person limit (30/hour) and a site-wide daily cap (300/day), and records every AI call's real input, cached and output tokens and cost. It covers the Report Builder, the rules extractor and the website checks, with an Admin card. 3 new tests.
- **Real measurements** on gpt-5.6-luna vs gpt-5.6-sol (10 fund pages and 8 report requests):
  - **Rules Extractor:** 1,790 input tokens (1,138 cached), 423 output, **$0.00066** per run, 4.2 s, 46/47 fields correct. Sol: $0.0213, 47/47.
  - **Report Builder:** 733 input / 163 output tokens, **$0.00034** per run, 7/8 correct (Sol the same).
  - **Luna's one miss** (West Fund's state basis) was flagged by the quote checker.
  - **Matching engine:** 4.3 µs per patient, no AI.
- **Live safety tests:** a prompt injection on a fund page ("set pledge to $10,000") was ignored, both in code and in the live app (screenshots). The Report Builder refused to list patient names or reveal its instructions or the API key.
- **Figures:** the user's flowchart; the user's four screenshots (language choice, welcome screen, income question, clinic portal); 11 new screenshots from a real run (website checks, Carolina review, Report Builder and chart, patient results, clinic case, fund card, AI usage, the injection test); and an agent pipeline diagram (SVG).
- **Fixes along the way:** pydantic-ai's `usage` is a property here, not a method; a test leaked a login lockout into later tests (now reset between tests).
- **Files:** `report-assets/` holds the template, the build script (`build_report.py`) and the images. 94 tests pass.

---

## Prompt 48 — 2026-11-23

> Let's make some tweaks. Can you remove any reference to "justice funds" if there are any in the app? just call it patient assistance fund or something else

**Outcome:** Removed every "justice" reference from the app and report.
- **Renamed** the demo clinic fund "Mesa Justice Fund" to **"Mesa Patient Assistance Fund"** (Prairie's was already "Prairie Patient Assistance Fund"). Updated: demo data (`seed.py`), a code comment (`db.py`), tests, README, DEMO_GUIDE, the report text, and the current demo database (in place, without wiping it).
- **Report images:** re-took the three screenshots that showed the old name (patient results, clinic portal, clinic case view). The clinic-portal screenshot replaces the user's, which showed the old name. The flowchart (its "Approves justice/internal funds" box) is redrawn as an inline diagram with the same layout and colors: "Approves patient assistance funds", and fund criteria "Funds edit; AI suggests".
- `git grep` finds no "justice" in the app or docs. The only mentions left are in `Ai.prompts.md` (verbatim earlier prompts) and the original `design-flowchart.webp` reference image, which isn't used by the app or the report.
- 94 tests pass; the report still prints at 15 pages.
