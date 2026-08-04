# 🎯 Job Hunter Pro — Auto Apply Tool

A Python tool that automatically searches jobs across keyless job APIs, company ATS boards,
and scraped boards, finds HR email addresses, sends your resume, and follows up automatically.

### Where jobs come from

Enabled by default in `config.PLATFORMS` — no keys, no login:

| Source | How | Notes |
|---|---|---|
| RemoteOK, Remotive | public JSON API | global remote |
| We Work Remotely, Himalayas | RSS | global remote |
| **Arbeitnow** | public JSON API | Europe-heavy, many visa-sponsor roles |
| **Jobicy** | public JSON API | remote-only; `geo` filter per `TARGET_COUNTRIES` |
| **Greenhouse, Lever, Ashby** | public ATS API | direct-to-company — see below |
| **HN "Who is hiring?"** | Algolia API | monthly thread; small companies, founder emails |
| LinkedIn | HTML scrape | per country; most productive but most fragile |
| Shine | HTML scrape | India only |
| Japan Dev | HTML scrape | Japan |
| Indeed | HTML + Playwright | needs `USE_BROWSER_FETCH = True`, else Cloudflare-blocked |

Implemented but off by default — add to `PLATFORMS` to enable: `naukri`, `glassdoor`,
`bayt`, `tokyodev`, `skipthedrive`, `freelancer`, `justremote`, `wellfound` (Playwright),
`upwork` (OAuth token).

#### Greenhouse / Lever / Ashby board tokens

These three are the boards Google for Jobs indexes. Their APIs are keyless and never
bot-blocked, but there is **no cross-company search** — each company has its own board
token, so coverage equals your token list:

```bash
python3 main.py --harvest-ats        # scan collected URLs for new company boards
python3 main.py --harvest-ats --dry-run
```

Seed lists live in `config.py` (`GREENHOUSE_BOARDS` / `LEVER_BOARDS` / `ASHBY_BOARDS`).
Harvested tokens are appended to `ats_tokens.json` (gitignored), so coverage compounds
every run. HN and LinkedIn results frequently link straight at an ATS board, which is
what makes the harvest pay off.

To add one by hand, take the token out of the board URL:

```
job-boards.greenhouse.io/vercel/jobs/123  → "vercel"
jobs.lever.co/shieldai/<uuid>             → "shieldai"
jobs.ashbyhq.com/ramp/<uuid>              → "ramp"
```

---

## 📦 What's Inside

```
JobHunterPro/
├── main.py           ← Entry point — run this
├── config.py         ← ⭐ YOUR SETTINGS (edit this first!)
├── scrapers.py       ← Aggregates every source; LinkedIn/Indeed/Glassdoor/Naukri/Shine
├── remote_boards.py  ← RemoteOK, Remotive, WWR, Himalayas, Arbeitnow, Jobicy
├── ats_boards.py     ← Greenhouse, Lever, Ashby + board-token harvesting
├── community_boards.py ← HN "Ask HN: Who is hiring?"
├── regional_boards.py← TokyoDev, Japan Dev, Bayt
├── marketplace_boards.py ← Freelancer, Upwork
├── email_finder.py   ← Finds HR email addresses via Hunter.io
├── email_sender.py   ← Sends emails via Gmail
├── templates.py      ← Application & follow-up email templates
├── database.py       ← SQLite database for tracking applications
├── requirements.txt  ← Python packages needed
└── resume.pdf        ← ⭐ PUT YOUR RESUME HERE
```

---

## 🚀 Setup (5 minutes)

### Step 1 — Install Python
Download from https://python.org (version 3.8 or later)

### Step 2 — Install dependencies
Open a terminal/command prompt in the JobHunterPro folder and run:
```bash
pip install -r requirements.txt
```

### Step 3 — Set up Gmail App Password
Your Gmail account needs an "App Password" (a special 16-character password just for this tool).

1. Go to: https://myaccount.google.com/security
2. Make sure **2-Step Verification** is turned ON
3. Search for "App Passwords" in the security page
4. Click "App passwords" → Select app: **Mail** → Select device: **Windows Computer**
5. Click **Generate** — copy the 16-character password shown

### Step 4 — Get a free Hunter.io API key (for finding HR emails)
1. Go to: https://hunter.io/users/sign_up
2. Sign up for a free account (no credit card needed)
3. Go to your dashboard → **API** → copy your API key
4. Free plan gives you 25 email searches per month

### Step 5 — Edit config.py
Open `config.py` in any text editor (Notepad, VS Code, etc.) and fill in:

```python
GMAIL_EMAIL    = "youremail@gmail.com"
GMAIL_PASSWORD = "xxxx xxxx xxxx xxxx"   # The 16-char App Password from Step 3

HUNTER_API_KEY = "your_hunter_api_key"   # From Step 4

YOUR_NAME       = "Sharad Wankhade"
YOUR_PHONE      = "+91-9999999999"
YOUR_LINKEDIN   = "https://linkedin.com/in/yourprofile"
YOUR_LOCATION   = "Pune, India"
YOUR_EXPERIENCE = "3"
```

### Step 6 — Add your resume
Place your resume PDF in the `JobHunterPro` folder and name it `resume.pdf`
(or update `RESUME_PATH` in config.py with the actual filename)

---

## ▶️ How to Use

### Interactive mode (recommended for beginners)
```bash
python main.py
```
You'll see a menu — just pick an option!

### Direct commands
```bash
# Search jobs and send applications
python main.py --job "Python Developer"
python main.py --job "React"
python main.py --job "Data Analyst"

# Send follow-up emails (run this 3+ days after applying)
python main.py --followup

# See your application stats
python main.py --status

# List all applications
python main.py --list

# Test without actually sending emails
python main.py --job "Python Developer" --dry-run
```

---

## 🔄 Typical Workflow

**Day 1 — Search and Apply:**
```bash
python main.py --job "Python Developer"
```
→ Searches all platforms → Finds HR emails → Sends applications with your resume

**Day 4+ — Follow up:**
```bash
python main.py --followup
```
→ Automatically sends polite follow-up emails to companies who haven't replied

**Anytime — Check status:**
```bash
python main.py --status
```

---

## ✏️ Customizing Email Templates

Open `templates.py` to edit:
- **application_email()** — the initial email sent with your resume
- **followup_email()** — the follow-up email sent after 3 days

---

## ⚙️ Settings You Can Change in config.py

| Setting | Default | Description |
|---|---|---|
| `FOLLOW_UP_DAYS` | 2 | Days before follow-up is sent |
| `MAX_JOB_POSTING_AGE_DAYS` | 10 | Only jobs posted within this many days (use 7–10 for a tighter window) |
| `MAX_RESULTS_PER_PLATFORM` | 100 | Max jobs fetched per platform, per country |
| `JOB_LOCATION` | "India" | Location used only when `REMOTE_ONLY = False` |
| `TARGET_COUNTRIES` | India, Germany, Dubai | One regional search each for LinkedIn/Indeed/Glassdoor/Bayt |
| `PLATFORMS` | see table above | Which sources to search |
| `DEDUPE_BY_COMPANY_NAME` | True | Keeps only the **first listing per company** — biggest throughput lever |
| `USE_BROWSER_FETCH` | False | Playwright for Indeed/Glassdoor/Wellfound/Bayt; required for Indeed |
| `GREENHOUSE_BOARDS` etc. | seed list | ATS board tokens; grow with `--harvest-ats` |
| `ATS_MAX_PER_BOARD` | 25 | Cap per ATS board so one 800-job board can't crowd out the rest |
| `ATS_FETCH_WORKERS` | 6 | Parallel ATS board fetches |
| `ARBEITNOW_MAX_PAGES` | 3 | Arbeitnow pages to walk (~100 jobs/page) |
| `HN_MAX_THREAD_AGE_DAYS` | 40 | HN threads are monthly, so they get their own freshness window |

---

## ❓ Troubleshooting

**"Gmail authentication failed"**
→ Make sure you're using the App Password (16 chars), NOT your real Gmail password

**"Resume file not found"**
→ Make sure `resume.pdf` is in the same folder as `main.py`

**"No jobs found"**
→ The keyless APIs (RemoteOK, Remotive, Arbeitnow, Jobicy, Greenhouse, Ashby, HN) don't get
   blocked, so if those return zero the filters are the cause, not the network. Try widening
   `MAX_JOB_POSTING_AGE_DAYS`, adding `TARGET_COUNTRIES`, or setting
   `DEDUPE_BY_COMPANY_NAME = False`.

**"Greenhouse/Lever/Ashby: skipped — no board tokens"**
→ Those APIs have no cross-company search. Add tokens to `config.py` or run
   `python3 main.py --harvest-ats`.

**"HN: newest thread is Nd old"**
→ Raise `HN_MAX_THREAD_AGE_DAYS`. Threads post on the 1st of each month.

**"Indeed: Blocked (HTTP 403)"**
→ Set `USE_BROWSER_FETCH = True` and install Playwright (see INTEGRATIONS.md).

**"No HR emails found"**
→ Set up your Hunter.io API key. Without it, the tool guesses `hr@company.com` patterns.
   You can also manually add emails with: `python main.py --add-email`

---

## 📋 Tips for Better Results

1. **Be specific** — "Python Django Developer" gets better results than just "Python"
2. **Hunter.io free tier** — 25 searches/month. Use wisely for top companies.
3. **Customize templates** — Personalize `templates.py` with your actual skills & achievements
4. **Run follow-ups daily** — Add `python main.py --followup` to your daily routine
5. **Add emails manually** — For companies without found emails, use `--add-email` to add them yourself

---

## 🗃️ Database

All applications are stored in `job_hunter.db` (SQLite). You can open this file with:
- **DB Browser for SQLite** (free): https://sqlitebrowser.org
- Or any SQLite viewer

---

*Built with Python • Searches LinkedIn, Indeed, Glassdoor, Naukri, Shine • Gmail SMTP • Hunter.io*


Commands for next time
python3 main.py --clear-db --all --yes
# Delete only unsent / pending jobs (keeps sent history)
python3 main.py --clear-db --pending --yes
# Delete jobs older than 30 days
python3 main.py --clear-db --older-than 30 --yes
# Delete jobs for one search title only
python3 main.py --clear-db --job "React Developer" --yes



Single command
python3 main.py --run --job "React Developer"


Follow-ups (separate, later)
python3 main.py --followup
The old step-by-step flow (--job only, manual confirm) still works if you need it; for daily use, prefer --run.