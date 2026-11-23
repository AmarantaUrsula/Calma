# Try Calma — a guide for colleagues

Thanks for testing! **Calma** helps abortion patients get funding support. A patient fills out **one short form** on their phone (English or Spanish). Calma checks it against the clinic's own fund and every partner abortion fund at once, and shows the patient what help is coming. Clinics and funds approve every pledge themselves, and every organization can run its own reports on the money pledged and paid out.

> **This is a demo.** All clinics, funds, patients and accounts are made up (the four "real fund" entries only read those funds' public web pages). **Please don't enter real personal or patient information.**

## Before you start

- **Link:** `https://________________.onrender.com` *(filled in by the person who sent you this)*
- **Password:** every demo account below uses the same password, which the person who sent you this guide will share with you directly. (It's not the password in the project's README; that one only works on a developer's own computer.)
- **First visit is slow:** the demo runs on a free server that sleeps when no one is using it, so the first page can take about a minute to load.
- **Data resets:** anything you create may reset when the server restarts. That's expected.
- **Use two browser windows** (or one private window) to be two people at once, for example a clinic and a fund.

## Demo accounts

| Log in as | Email | What you'll see |
|---|---|---|
| Rosa — Mesa Women's Health (NM) | `rosa@mesa.example.org` | Clinic portal |
| Dana — Prairie Family Clinic (KS) | `dana@prairie.example.org` | Clinic portal |
| Sam — Desert Bloom Fund | `sam@desertbloom.example.org` | Fund portal (TX/NM/AZ residents) |
| Jordan — Heartland Access Fund | `jordan@heartland.example.org` | Fund portal (KS/MO/OK residents) |
| Alex — Open Road Travel Fund | `alex@openroad.example.org` | Fund portal (travel, lodging, meals, childcare) |
| Kai — Later Care Fund | `kai@latercare.example.org` | Fund portal (14–24 weeks) |
| Lu — Enchanted Circle Care Fund | `lu@enchantedcircle.example.org` | Fund portal (anyone getting care in NM) |
| Mia — Youth Access Fund | `mia@youthaccess.example.org` | Fund portal (age 19 and under) |
| Admin | `admin@calma.example.org` | Accounts, fund rules, AI suggestions, reports for all organizations, audit log |

You can also **create your own account** ("Create an account" on the login page). It waits until the admin approves it, which you can do yourself as Admin.

## Things to try (about 20 minutes)

### 1. A patient's experience (5 min) — the heart of Calma
1. Log in as **Rosa** (clinic). Under **New appointment**, click **Create link**, then **Open patient link** (or copy it to your phone).
2. As the patient: choose **English or Español** and answer the questions. Only the questions the clinic's funds need are asked, one per screen. Try:
   - **State:** Texas
   - **Household:** 3 people
   - **Income:** $30,000 a year
   - **Last period:** about 8 weeks before the visit
   - **Age:** 17
   - **Travel:** yes, 300 miles, 2 nights, 2 days of meals, 1 day of childcare
   - **Insurance:** no
3. See the results: each fund with its amount and "Waiting for an answer", what the visit costs, what the patient may still owe, and travel help in its own section. The clinic's phone number is always at the bottom. This page is the patient's status page; it updates as funds decide.

### 2. Funds and clinics decide (5 min)
1. As **Rosa**, click the new case. You'll see every answer, each matched fund with the reasons it matched, and funds that didn't match and why. **Approve** the Mesa Justice Fund pledge and watch the monthly budget go down.
2. In another window, log in as **Sam** (Desert Bloom). The patient is under **Needs decision**, showing only what this fund needs to know. **Approve** it, or change the amount.
3. Reload the patient's page: the status changes to **Approved**, and "you may need to pay" goes down.
4. Back as Rosa, **Mark visit done**. Sam then sees **Owed to clinic** and clicks **Mark paid**. Check **Reimbursement** on the clinic side.

### 3. Keeping fund rules up to date (5 min)
1. As **Admin**, look at **Fund website checks**. Calma re-reads each fund's eligibility page every couple of months. Four **real** funds are included, reference only (never matched with the made-up patients).
2. Click **Check now** on a real fund, for example Carolina Abortion Fund. The AI reads the page and suggests rules at the top of the page, **quoting the exact sentence** behind each one. Nothing goes live until a person approves it. (The pledge amount has to be entered by hand, since these funds don't publish one.)
3. As a fund (for example **Kai**), open **My eligibility rules** and change something. You'll see a "You're changing" summary before you save. Also look at **Partner clinics**, where funds request to partner and clinics accept.
4. As **Rosa**, open **Intake questions** to see which questions patients are asked and why, and turn on optional ones.

### 4. Reports: how much went where (5 min)
The demo includes six months of made-up past cases, so there's real-looking data to explore. Every portal has a **Reports** tab, and each organization only sees its own numbers: a clinic sees its patients, a fund sees its own pledges, and the admin sees everything.
1. Log in as **Admin** and open **Reports (all organizations)**. In **Describe the report you want**, type a request in your own words and click **Build report**, for example:
   - *"bar chart of money paid out each month since June, split by travel help vs procedure"*
   - *"pie chart of how much each fund paid out this year"*
   - *"how many patients did we help by home state in the last 3 months"*

   An AI picks the settings (dates, what to measure, how to group, which chart). It never sees patient information, and every number is calculated by Calma itself, so the AI can't make up amounts. The settings it chose appear in the controls, and you can change any of them.
2. Now try the controls yourself: pick a **period**, choose **disbursed** (paid out) or **pledged** (approved), and **group by** up to three things (for example fund, then month, then type of help). Switch between **Table**, **Bar** and **Pie**, and between **Dollars** and **Patients**. Hover over a bar or slice for details.
3. Click **Download Excel**. The file has a **Report** sheet (your filters and totals) and a **Data** sheet with one row per pledge for your own pivot tables or charts. It's de-identified: case numbers instead of names, and ranges instead of exact income, age or weeks.
4. Log in as a fund (for example **Sam**) and open **Reports**. You'll see only Desert Bloom's own pledges, with fewer grouping options, because a fund only gets what it already sees about patients.

Groups with fewer than 5 patients are marked with *, because small numbers can point to a specific person. Every Excel download is recorded in the audit log.

## Questions we'd love your feedback on

1. Would a patient understand every question? Is anything confusing, missing, or uncomfortable to answer?
2. Does the patient's results page feel clear and reassuring?
3. For clinic staff: does the case view give you what you need to approve quickly?
4. For fund staff: is it clear why each patient matched? Is there anything you'd need to see before approving a pledge?
5. Are there eligibility rules your fund uses that Calma can't express? (Known gaps: identity-based eligibility, and funds that only pay specific clinics.)
6. Do the reports answer the questions your board, funders or grant reports ask? Is there a measure, grouping or chart you'd need that's missing? Did the "describe the report" box understand what you asked for?
7. Anything that would stop your organization from using a tool like this?

## What's not built yet

- **Messages and accounts:** no real text messages or emails (the clinic copies the patient link by hand), no password reset, and no two-factor login.
- **Data:** demo data only. Real patient data would need HIPAA agreements with every service involved, and more security work.
- **Language and pages:** the Spanish hasn't been reviewed by a native speaker yet, and fund pages that are PDFs or need JavaScript to load can't be read yet.

## How decisions are made (in case you're wondering)

**Who qualifies for which fund is decided by plain, written rules, not AI**, so every result can be explained and is the same every time. AI is used in only two places, and neither decides who gets money:

- **Reading fund websites** to *suggest* rule updates, which a person reviews and approves.
- **The report box**, which turns your request into report settings. The numbers are calculated by Calma, not the AI.

AI never sees patient answers.
