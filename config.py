"""
╔══════════════════════════════════════════════════════════════╗
║              JOB HUNTER PRO - Configuration File            ║
║  Edit the values below with your personal details.          ║
╚══════════════════════════════════════════════════════════════╝

SETUP STEPS:
  1. Fill in your Gmail credentials (see README for App Password guide)
  2. Fill in your personal details for email personalization
  3. Put your resume PDF in the same folder as this script
  4. Run: python3 main.py
"""

import os

# ─────────────────────────────────────────────
# 📧 GMAIL SETTINGS
# ─────────────────────────────────────────────
GMAIL_EMAIL    = "sharadkumarw23@gmail.com"        # Your Gmail address
GMAIL_PASSWORD = "xokz ockp mqqq oasw"          # 16-char App Password (NOT your real password)
                                                 # Get it at: myaccount.google.com > Security > App Passwords

# ─────────────────────────────────────────────
# 📧 CONTACT PAGE EMAIL SCRAPING
# ─────────────────────────────────────────────
# Scrape company websites (contact / contact-us pages) for public email addresses.
CONTACT_PAGE_SCRAPE_ENABLED = True

# Relative paths tried on each candidate domain (https first, then http).
CONTACT_PAGE_PATHS = (
    "/contact",
    "/contact-us",
    "/contactus",
    "/contact_us",
    "/about/contact",
    "/company/contact",
    "/en/contact",
    "/support/contact",
    "/get-in-touch",
    "/reach-us",
)

# Also scan the homepage for mailto: links and “Contact” navigation links.
CONTACT_SCRAPE_HOMEPAGE = True

# Use Playwright for contact pages when plain HTTP fails (falls back to USE_BROWSER_FETCH if None).
CONTACT_SCRAPE_USE_BROWSER = None

# If DuckDuckGo instant API has no answer, scrape lightweight HTML results (helps for many companies)
USE_DDG_HTML_DOMAIN_LOOKUP = True

# When backfilling job_tracking.xlsx (--fill-hr-emails), only write pattern guesses if True.
FILL_XLSX_INCLUDE_GUESSES = False

# If True, Gmail only sends addresses that count as “verified” in the database:
#   • Emails found on the company contact page (automatic), OR
#   • Addresses you add with --add-email / the Excel HR email column.
# If False, guessed hr@… addresses are sent without a contact-page match (more bounces).
SEND_ONLY_VERIFIED_EMAILS = True

# Domains to never use for hr@ / careers@ pattern guessing (consumer sites / wrong DDG hits).
BLOCKED_GUESS_EMAIL_DOMAINS = (
    "sites.google.com",
    "google.com",
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.in",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "linkedin.com",
    "facebook.com",
    "reddit.com",
)

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
# 🎯 CANDIDATE PROFILE  (used to TAILOR each application email to the role)
# ─────────────────────────────────────────────
# One-line headline shown in the email opening. Keep it to your real specialty.
YOUR_HEADLINE  = "Full-Stack Engineer (React · Next.js · Node.js)"

# GitHub / portfolio link shown in the email + signature. Leave "" to hide it.
YOUR_PORTFOLIO = ""   # e.g. "https://github.com/your-handle"

# Skills you can CREDIBLY claim. The email surfaces the ones that match each job title,
# so a React role sees your React skills and a Node role sees your backend skills.
YOUR_SKILLS = [
    "React", "Next.js", "TypeScript", "Redux", "Tailwind",
    "Node.js", "Express", "Nest.js", "REST APIs", "Microservices",
    "AWS", "GCP", "Docker", "CI/CD",
    "PostgreSQL", "MongoDB", "Redis",
    "performance optimization", "system design",
]

# Achievements tagged by keyword. The email shows the 3 whose keywords best match the
# role title. KEEP THESE TRUE AND SPECIFIC — recruiters verify them in interviews.
ACHIEVEMENTS = [
    {"keywords": ["react", "frontend", "front-end", "next", "ui", "typescript", "javascript", "web"],
     "text": "Cut page-load times ~35% on a React/Next.js SaaS frontend using code-splitting, lazy loading, and render optimization."},
    {"keywords": ["node", "backend", "back-end", "api", "rest", "microservice", "server"],
     "text": "Built and scaled Node.js REST APIs serving 10k+ daily active users with no downtime during peak traffic."},
    {"keywords": ["security", "auth", "authentication", "jwt", "oauth"],
     "text": "Implemented JWT auth and Bcrypt password storage, reducing login-related incidents ~40%."},
    {"keywords": ["aws", "gcp", "cloud", "devops", "docker", "ci", "cd", "infrastructure", "sre", "reliability"],
     "text": "Set up Docker + GitHub Actions CI/CD with Grafana/Sentry monitoring across client-facing apps."},
    {"keywords": ["database", "postgres", "mongodb", "mysql", "sql", "data"],
     "text": "Designed and optimized PostgreSQL/MongoDB data layers powering high-traffic SaaS products."},
    {"keywords": ["e-commerce", "ecommerce", "commerce", "shop", "cart", "payment", "checkout"],
     "text": "Delivered e-commerce flows (catalog, cart, payments) and lifted conversion via a faster, responsive frontend."},
]

# Used to top up when fewer than 3 ACHIEVEMENTS match the role. Keep these on DISTINCT themes
# (scale, ownership, remote delivery) so a top-up never echoes an already-shown bullet.
DEFAULT_ACHIEVEMENTS = [
    "Built and scaled web applications serving 10k+ daily active users with high reliability.",
    "Shipped features end-to-end — React/Next.js frontends through Node.js backends and deploys.",
    "Delivered in distributed remote teams across time zones with strong async communication.",
]

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

# Only include listings posted within this many days (7–10 is a good range; default 10).
MAX_JOB_POSTING_AGE_DAYS = 10

# One-shot batch (--run): find jobs + verified emails + sheet + DB + send for this many new listings.
BATCH_JOB_LIMIT = 50
# In batch mode, skip pattern-guessed emails unless SEND_ONLY_VERIFIED_EMAILS is False.
BATCH_REQUIRE_VERIFIED_EMAIL = True

# Legacy single location when REMOTE_ONLY is False (on-site / hybrid searches)
JOB_LOCATION = "India"

# Remote-only: search keywords + filters favour “remote / work from home” roles
REMOTE_ONLY = True

# At least 5 countries recommended — each entry is one regional search (LinkedIn/Indeed/Glassdoor).
# Naukri & Shine run only when one of these names matches India (see README).
TARGET_COUNTRIES = [
    "India",
    "Germany",
    "Dubai",
]

# Order matters: global boards (API/RSS) run first, then per-country scrapers.
# Default list = sources that work without paywall, OAuth, or anti-bot failures.
# Use the INCLUDE_* flags below to add optional sources.
PLATFORMS = [
    "remoteok",
    "remotive",
    "weworkremotely",
    "justremote",# public Freelancer.com read API (no token)
    "linkedin",
    "shine",
    "arc.dev",
    "ziprecruiter",
    "careerbuilder",
    "dice",
    "himalayas",
    "japan-dev",
]

# Append stub / paywall boards (Wellfound needs Playwright when USE_BROWSER_FETCH is True).
INCLUDE_STUB_PLATFORMS = False

# Append Upwork (requires UPWORK_ACCESS_TOKEN from OAuth — see INTEGRATIONS.md).
INCLUDE_MARKETPLACE_PLATFORMS = False

# Append Indeed + Glassdoor (often HTTP 403; use USE_BROWSER_FETCH + Playwright to improve odds).
INCLUDE_INDEED_GLASSDOOR = False

# Use Playwright Chromium for bot-prone or JS-heavy pages (Indeed, Glassdoor, Wellfound, Himalayas).
USE_BROWSER_FETCH = False

# Saved Playwright login sessions (see INTEGRATIONS.md). Default folder under this project (gitignored).
AUTH_STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".jobhunter", "auth")

# When True and a matching * _storage.json exists (from python3 main.py --auth-*), Playwright fetches use that session.
INDEED_USE_AUTH_STATE = False
WELLFOUND_USE_AUTH_STATE = False
# Reserved for a future browser-based Upwork job search; `python3 main.py --auth-upwork` still saves state now.
UPWORK_USE_AUTH_STATE = False

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


def auth_storage_path(platform: str) -> str:
    """Path to Playwright storage JSON for indeed | wellfound | upwork."""
    name = (platform or "").strip().lower()
    if name not in ("indeed", "wellfound", "upwork"):
        raise ValueError("platform must be indeed, wellfound, or upwork")
    base = os.environ.get("JOBHUNTER_AUTH_DIR") or AUTH_STATE_DIR
    if not os.path.isabs(base):
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), base)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{name}_storage.json")


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
