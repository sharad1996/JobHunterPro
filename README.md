# 🎯 Job Hunter Pro — Auto Apply Tool

A Python tool that automatically searches jobs across **LinkedIn, Indeed, Glassdoor, Naukri, and Shine**, finds HR email addresses, sends your resume, and follows up automatically after 3 days.

---

## 📦 What's Inside

```
JobHunterPro/
├── main.py           ← Entry point — run this
├── config.py         ← ⭐ YOUR SETTINGS (edit this first!)
├── scrapers.py       ← Scrapes job listings from all platforms
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
| `FOLLOW_UP_DAYS` | 3 | Days before follow-up is sent |
| `MAX_RESULTS_PER_PLATFORM` | 15 | Max jobs fetched per platform |
| `JOB_LOCATION` | "India" | Location for job search |
| `PLATFORMS` | all 5 | Which platforms to search |

---

## ❓ Troubleshooting

**"Gmail authentication failed"**
→ Make sure you're using the App Password (16 chars), NOT your real Gmail password

**"Resume file not found"**
→ Make sure `resume.pdf` is in the same folder as `main.py`

**"No jobs found"**
→ Check your internet connection. LinkedIn may block scrapers — try Indeed or Naukri first.

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
