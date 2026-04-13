"""
╔══════════════════════════════════════════════════════════════╗
║              JOB HUNTER PRO - Configuration File            ║
║  Edit the values below with your personal details.          ║
╚══════════════════════════════════════════════════════════════╝

SETUP STEPS:
  1. Fill in your Gmail credentials (see README for App Password guide)
  2. Get a free Hunter.io API key at: https://hunter.io/users/sign_up
  3. Fill in your personal details for email personalization
  4. Put your resume PDF in the same folder as this script
  5. Run: python3 main.py
"""

import os

# ─────────────────────────────────────────────
# 📧 GMAIL SETTINGS
# ─────────────────────────────────────────────
GMAIL_EMAIL    = "sharadkumarw23@gmail.com"        # Your Gmail address
GMAIL_PASSWORD = "xokz ockp mqqq oasw"          # 16-char App Password (NOT your real password)
                                                 # Get it at: myaccount.google.com > Security > App Passwords

# ─────────────────────────────────────────────
# 🔍 HUNTER.IO API (Email Finder)
# ─────────────────────────────────────────────
HUNTER_API_KEY = "fcae5c359d6266b5282990b87345bbffa4f7544b"     # Free key: https://hunter.io (25 searches/month free)

# When domain-search returns nothing, try Hunter “email finder” for common role names (uses extra credits)
HUNTER_EMAIL_FINDER_FALLBACK = True

# If DuckDuckGo instant API has no answer, scrape lightweight HTML results (helps for many companies)
USE_DDG_HTML_DOMAIN_LOOKUP = True

# ─────────────────────────────────────────────
# 👤 YOUR PERSONAL DETAILS
# ─────────────────────────────────────────────
YOUR_NAME       = "Sharad Kumar"
YOUR_PHONE      = "+91-8109618802"
YOUR_EMAIL      = "sharadkumarw23@gmail.com"                    # Email to show in signature
YOUR_LINKEDIN   = "https://linkedin.com/in/sharad-kumar-dev"
YOUR_LOCATION   = "Indore, India"
YOUR_EXPERIENCE = "7"                            # Years of experience (used in email body)

# ─────────────────────────────────────────────
# 📄 RESUME FILE
# ─────────────────────────────────────────────
RESUME_PATH = "resume.pdf"                       # Place your PDF resume in the same folder

# ─────────────────────────────────────────────
# ⏰ FOLLOW-UP SETTINGS
# ─────────────────────────────────────────────
FOLLOW_UP_DAYS = 2                               # Days to wait before sending follow-up

# ─────────────────────────────────────────────
# 🌐 JOB SEARCH SETTINGS
# ─────────────────────────────────────────────
MAX_RESULTS_PER_PLATFORM = 100                   # Max jobs per platform *per country* (remote mode)

# Legacy single location when REMOTE_ONLY is False (on-site / hybrid searches)
JOB_LOCATION = "India"

# Remote-only: search keywords + filters favour “remote / work from home” roles
REMOTE_ONLY = True

# At least 5 countries recommended — each entry is one regional search (LinkedIn/Indeed/Glassdoor).
# Naukri & Shine run only when one of these names matches India (see README).
TARGET_COUNTRIES = [
    "United States",
    "United Kingdom",
    "Germany",
    "Canada",
    "India",
]

# Order matters: global boards (API/RSS) run first, then per-country scrapers.
# Default list = sources that work without paywall, OAuth, or anti-bot failures.
# Use the INCLUDE_* flags below to add optional sources.
PLATFORMS = [
    "remoteok",
    "remotive",
    "weworkremotely",
    "justremote",
    "skipthedrive",
    "freelancer",   # public Freelancer.com read API (no token)
    "linkedin",
    "naukri",
    "shine",
]

# Append stub / paywall boards (Himalayas only does something when USE_BROWSER_FETCH is True).
INCLUDE_STUB_PLATFORMS = False

# Append Upwork (requires UPWORK_ACCESS_TOKEN from OAuth — see INTEGRATIONS.md).
INCLUDE_MARKETPLACE_PLATFORMS = False

# Append Indeed + Glassdoor (often HTTP 403; use USE_BROWSER_FETCH + Playwright to improve odds).
INCLUDE_INDEED_GLASSDOOR = False

# Use Playwright Chromium for bot-prone or JS-heavy pages (Indeed, Glassdoor, Wellfound, Himalayas).
USE_BROWSER_FETCH = False

# Optional full list for copy-paste into PLATFORMS when you want everything enabled manually:
# remoteok, remotive, weworkremotely, justremote, skipthedrive, freelancer, upwork,
# himalayas, flexjobs, wellfound, indeed, linkedin, glassdoor, naukri, shine

# ─────────────────────────────────────────────
# 🏢 COMPANY FILTERS (small employers, skip megacorps)
# ─────────────────────────────────────────────
FILTER_OUT_BIG_TECH = True
# Matched as whole words inside the company name (case-insensitive). Edit freely.
BIG_TECH_BLOCKLIST = [
    "amazon", "google", "alphabet", "microsoft", "meta", "facebook", "apple",
    "netflix", "oracle", "salesforce", "ibm", "accenture", "deloitte", "pwc",
    "infosys", "wipro", "cognizant", "capgemini", "tcs", "jpmorgan", "goldman",
    "morgan stanley", "tesla", "nvidia", "intel", "cisco", "adobe", "uber",
    "airbnb", "spotify", "twitter", "linkedin", "snap", "palantir", "stripe",
    "shopify", "snowflake", "databricks", "servicenow", "vmware", "broadcom",
]

# When a job dict includes employee_count_min / employee_count_max (rare from scrapers),
# keep only roles whose band overlaps this range. Most listings have no size data.
TARGET_EMPLOYEE_MIN = 1
TARGET_EMPLOYEE_MAX = 500
# If True, drops every job without employee_count_* (very aggressive — usually leave False).
SKIP_JOBS_WITHOUT_HEADCOUNT_DATA = False

# After all platforms: keep only the first listing per company name.
DEDUPE_BY_COMPANY_NAME = True

# ─────────────────────────────────────────────
# 📑 EXCEL TRACKING (skip already-applied / already-emailed URLs)
# ─────────────────────────────────────────────
JOB_TRACKING_XLSX = "job_tracking.xlsx"

# ─────────────────────────────────────────────
# 🗃️ DATABASE
# ─────────────────────────────────────────────
DB_PATH = "job_hunter.db"                        # SQLite database file path

# ─────────────────────────────────────────────
# Validation (don't edit below this line)
# ─────────────────────────────────────────────
def validate_config():
    errors = []
    if "your_email" in GMAIL_EMAIL:
        errors.append("❌ Gmail email not set in config.py")
    if "xxxx" in GMAIL_PASSWORD:
        errors.append("❌ Gmail App Password not set in config.py")
    if not os.path.exists(RESUME_PATH):
        errors.append(f"❌ Resume file not found: '{RESUME_PATH}' — place your resume PDF in the same folder")
    if "Your Full Name" in YOUR_NAME:
        errors.append("❌ YOUR_NAME not set in config.py")
    if REMOTE_ONLY:
        if not TARGET_COUNTRIES or len(TARGET_COUNTRIES) < 1:
            errors.append("❌ REMOTE_ONLY is True but TARGET_COUNTRIES is empty — add countries in config.py")
    return errors
