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
