"""
Email Finder — locates HR/recruiter email addresses for a company.

Strategy (in order):
  1. Infer corporate domain from job posting URL (ATS / careers subdomains)
  2. DuckDuckGo instant answer, then optional HTML search fallback
  3. Normalized company-name → simple domain guesses (e.g. acme.com)
  4. Hunter.io domain search (personal + generic mailboxes)
  5. Hunter.io email-finder for common local-parts (careers, hr, …)
  6. Pattern guessing (hr@, careers@, …) on the best domain candidate
"""

import json
import re
import time
import requests
from urllib.parse import urlparse

from bs4 import BeautifulSoup

import config

# ─── HTTP ─────────────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_HUNTER_LOGGED_ERRORS = set()


def _log_hunter_error(endpoint: str, resp: requests.Response) -> None:
    """Log Hunter non-200 once per (endpoint, status) so quota issues are visible."""
    key = (endpoint, resp.status_code)
    if key in _HUNTER_LOGGED_ERRORS:
        return
    _HUNTER_LOGGED_ERRORS.add(key)
    try:
        data = resp.json()
        snippet = data.get("errors", data)
        msg = json.dumps(snippet)[:300]
    except Exception:
        msg = (resp.text or "")[:200]
    hint = ""
    if resp.status_code in (402, 403, 429):
        hint = " — often monthly quota or plan limit; check dashboard.hunter.io"
    print(f"\n  ⚠️  Hunter.io {endpoint} HTTP {resp.status_code}{hint}: {msg}")


# ─── Hunter.io API ────────────────────────────────────────────────────────────

def hunter_domain_search(domain: str, company: str = "") -> dict:
    """
    Search Hunter.io for emails at a domain.
    Returns: { hr_name, hr_email } or empty dict.
    """
    if not config.HUNTER_API_KEY or "your_hunter" in config.HUNTER_API_KEY.lower():
        return {}

    try:
        url = "https://api.hunter.io/v2/domain-search"
        params = {
            "domain": domain,
            "api_key": config.HUNTER_API_KEY,
            "limit": 15,
            # Omit "type" so we get both personal and generic (careers@, …) when available
        }
        resp = requests.get(url, params=params, timeout=12)
        if resp.status_code != 200:
            _log_hunter_error("domain-search", resp)
            return {}

        data = resp.json().get("data", {})
        emails = data.get("emails", [])

        hr_keywords = ["hr", "recruit", "talent", "people", "hiring", "career"]
        for e in emails:
            title = (e.get("position") or "").lower()
            if any(k in title for k in hr_keywords):
                return {
                    "hr_email": e.get("value", ""),
                    "hr_name": f"{e.get('first_name','')} {e.get('last_name','')}".strip(),
                    "hr_email_verified": True,
                }

        # Prefer generic department inboxes if present
        for e in emails:
            v = (e.get("value") or "").lower()
            if any(x in v for x in ("careers@", "jobs@", "hr@", "talent@", "recruit@", "people@")):
                return {
                    "hr_email": e.get("value", ""),
                    "hr_name": f"{e.get('first_name','')} {e.get('last_name','')}".strip(),
                    "hr_email_verified": True,
                }

        if emails:
            e = emails[0]
            return {
                "hr_email": e.get("value", ""),
                "hr_name": f"{e.get('first_name','')} {e.get('last_name','')}".strip(),
                "hr_email_verified": True,
            }

    except Exception:
        pass
    return {}


def hunter_email_finder(domain: str, first_name: str = "HR", last_name: str = "") -> dict:
    """Guess a specific person's or role inbox via Hunter.io email finder."""
    if not config.HUNTER_API_KEY or "your_hunter" in config.HUNTER_API_KEY.lower():
        return {}
    try:
        params = {
            "domain": domain,
            "first_name": first_name,
            "last_name": last_name,
            "api_key": config.HUNTER_API_KEY,
        }
        resp = requests.get("https://api.hunter.io/v2/email-finder", params=params, timeout=12)
        if resp.status_code != 200:
            _log_hunter_error("email-finder", resp)
            return {}
        data = resp.json().get("data", {})
        email = data.get("email", "")
        score = data.get("score", 0)
        if email and score and int(score) > 40:
            return {
                "hr_email": email,
                "hr_name": f"{first_name} {last_name}".strip(),
                "hr_email_verified": True,
            }
    except Exception:
        pass
    return {}


def _hunter_role_fallback(domain: str) -> dict:
    """Try common recruiting mailboxes via Email Finder (config-gated)."""
    if not getattr(config, "HUNTER_EMAIL_FINDER_FALLBACK", True):
        return {}
    for first, last in [
        ("careers", ""),
        ("jobs", ""),
        ("hr", ""),
        ("talent", ""),
        ("recruiting", ""),
        ("people", ""),
    ]:
        r = hunter_email_finder(domain, first, last)
        if r.get("hr_email"):
            return r
        time.sleep(0.15)
    return {}


# ─── Domain from job URL (ATS / careers) ─────────────────────────────────────

def domain_hints_from_job_url(url: str) -> list:
    """
    Extract likely corporate email domains from a job URL.
    Many boards use careers.company.com, Lever, Greenhouse, Workday, etc.
    """
    if not url or not str(url).startswith("http"):
        return []
    try:
        p = urlparse(url.strip())
    except Exception:
        return []

    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path_parts = [x for x in (p.path or "").split("/") if x]

    candidates = []
    labels = host.split(".")

    # careers.company.com / jobs.company.co.uk (not jobs.lever.co — handled below)
    if len(labels) >= 3 and labels[0] in ("careers", "jobs", "apply", "work", "talent"):
        if not any(x in host for x in ("lever.co", "greenhouse.io", "ashbyhq.com", "smartrecruiters.com")):
            candidates.append(".".join(labels[1:]))

    # *.myworkdayjobs.com / *.wd*.myworkdayjobs.com → tenant subdomain
    if "myworkdayjobs.com" in host or "workdayjobs.com" in host:
        tenant = labels[0] if labels else ""
        if tenant and tenant not in ("www", "jobs", "careers") and not tenant.startswith("wd"):
            candidates.append(f"{tenant}.com")

    if "lever.co" in host and path_parts:
        slug = path_parts[0].replace("-", "").lower()
        if slug.isalnum() and len(slug) > 1:
            candidates.append(f"{slug}.com")

    if "greenhouse.io" in host and path_parts:
        slug = path_parts[0].lower()
        if slug.replace("-", "").isalnum():
            candidates.append(f"{slug.replace('-', '')}.com" if "-" not in slug else f"{slug}.com")

    if "ashbyhq.com" in host and path_parts:
        slug = path_parts[0].lower()
        candidates.append(f"{slug}.com")

    if "workable.com" in host and "apply" in path_parts:
        idx = path_parts.index("apply") if "apply" in path_parts else -1
        if idx >= 0 and idx + 1 < len(path_parts):
            slug = path_parts[idx + 1].lower()
            candidates.append(f"{slug}.com")

    # SmartRecruiters: careers.smartrecruiters.com/CompanyName
    if "smartrecruiters.com" in host and path_parts:
        candidates.append(f"{path_parts[0].lower()}.com")

    # De-dupe, keep order
    seen = set()
    out = []
    for c in candidates:
        c = c.strip(".").lower()
        if c and "." in c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


# ─── Company name → domain via web search ──────────────────────────────────────

def find_company_domain_ddg_api(company_name: str) -> str:
    """DuckDuckGo instant answer JSON (fast when it works)."""
    try:
        query = f"{company_name} official website"
        params = {
            "q": query,
            "format": "json",
            "no_redirect": 1,
            "no_html": 1,
            "skip_disambig": 1,
        }
        resp = requests.get("https://api.duckduckgo.com/", params=params, timeout=10)
        data = resp.json()

        url = data.get("AbstractURL", "") or data.get("OfficialWebsite", "")
        if url:
            return urlparse(url).netloc.replace("www.", "")

        for topic in data.get("RelatedTopics", [])[:5]:
            first_url = topic.get("FirstURL", "")
            if first_url and "duckduckgo" not in first_url.lower():
                netloc = urlparse(first_url).netloc.replace("www.", "")
                if netloc and "duckduckgo" not in netloc:
                    return netloc
    except Exception:
        pass
    return ""


def find_company_domain_ddg_html(company_name: str) -> str:
    """Scrape DuckDuckGo HTML results when instant API has no abstract URL."""
    if not getattr(config, "USE_DDG_HTML_DOMAIN_LOOKUP", True):
        return ""
    try:
        q = f"{company_name} official website"
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": q},
            headers=_HEADERS,
            timeout=12,
        )
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")
        skip = (
            "duckduckgo.com",
            "facebook.com",
            "twitter.com",
            "x.com",
            "linkedin.com",
            "instagram.com",
            "youtube.com",
            "wikipedia.org",
            "crunchbase.com",
            "glassdoor.com",
            "indeed.com",
            "monster.com",
        )

        for a in soup.select("a.result__a, a.result-link"):
            href = a.get("href") or ""
            if not href.startswith("http"):
                continue
            netloc = urlparse(href).netloc.lower().replace("www.", "")
            if not netloc:
                continue
            if any(s in netloc for s in skip):
                continue
            return netloc
    except Exception:
        pass
    return ""


_NAME_NOISE = re.compile(
    r"\b(inc\.?|llc|ltd\.?|limited|plc|corp\.?|corporation|company|co\.|"
    r"pvt\.?\s*ltd\.?|private\s+limited|gmbh|ag|ug|sa|s\.a\.|bv|nv|pty|"
    r"technologies|technology|solutions|services|group|holdings|labs)\b",
    re.I,
)


def normalize_company_name(name: str) -> str:
    n = _NAME_NOISE.sub(" ", name or "")
    n = re.sub(r"[^\w\s&.-]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def slug_domain_guesses(company_name: str) -> list:
    """Very rough brand → domain.com guesses (last resort)."""
    n = normalize_company_name(company_name)
    if not n:
        return []
    slug = re.sub(r"[^a-z0-9]+", "", n.lower())[:48]
    if len(slug) < 3:
        return []
    return [f"{slug}.com", f"{slug}.io"]


def collect_domain_candidates(company: str, job_url: str) -> list:
    """Ordered unique domain candidates to try with Hunter."""
    seen = set()
    ordered = []

    def add(d: str):
        d = (d or "").strip().lower().replace("www.", "")
        if not d or "." not in d:
            return
        if d not in seen:
            seen.add(d)
            ordered.append(d)

    for d in domain_hints_from_job_url(job_url):
        add(d)

    add(find_company_domain_ddg_api(company))
    add(find_company_domain_ddg_html(company))

    for d in slug_domain_guesses(company):
        add(d)

    return ordered


# ─── Pattern guessing ─────────────────────────────────────────────────────────

COMMON_HR_PREFIXES = [
    "hr", "careers", "jobs", "recruit", "talent", "hiring",
    "recruitment", "people", "humanresources",
]


def guess_hr_emails(domain: str) -> list:
    if not domain:
        return []
    return [f"{prefix}@{domain}" for prefix in COMMON_HR_PREFIXES]


# ─── Main entry ────────────────────────────────────────────────────────────────

def find_hr_emails(jobs: list) -> list:
    """
    Enriches each job dict with `hr_email` and `hr_name` fields.
    """
    print("\n📧 Finding company domains & HR emails…")
    if not config.HUNTER_API_KEY or "your_hunter" in config.HUNTER_API_KEY.lower():
        print(
            "  ⚠️  Set HUNTER_API_KEY in config.py for verified addresses; "
            "without it we only use guessed mailboxes when a domain is known."
        )

    enriched = []
    total = len(jobs)

    for i, job in enumerate(jobs, 1):
        company = job.get("company", "") or ""
        job_url = job.get("url", "") or ""
        print(f"  [{i}/{total}] {company[:56]}", end="  ", flush=True)

        result = {}
        candidates = collect_domain_candidates(company, job_url)
        job["domain_candidates"] = candidates

        chosen_domain = ""
        for dom in candidates:
            chosen_domain = dom
            result = hunter_domain_search(dom, company)
            if result.get("hr_email"):
                job["domain"] = dom
                break

        if not result.get("hr_email") and chosen_domain:
            job["domain"] = chosen_domain
            result = _hunter_role_fallback(chosen_domain) or result

        if not result.get("hr_email"):
            for dom in candidates:
                job["domain"] = dom
                result = _hunter_role_fallback(dom)
                if result.get("hr_email"):
                    break

        if not result.get("hr_email"):
            for dom in candidates:
                guesses = guess_hr_emails(dom)
                if guesses:
                    job["domain"] = dom
                    job["hr_email_guesses"] = guesses
                    result["hr_email"] = guesses[0]
                    result["hr_email_verified"] = False
                    break

        if result.get("hr_email"):
            job.update(result)
            print(f"→ {result.get('hr_email', '?')}")
        else:
            job["hr_email"] = ""
            job["domain"] = job.get("domain") or (candidates[0] if candidates else "")
            print("→ Not found (use job URL to apply on-site or find contacts manually)")

        enriched.append(job)
        time.sleep(0.25)

    found = sum(1 for j in enriched if j.get("hr_email"))
    print(f"\n  ✅ Resolved at least one address for {found}/{total} listing(s)")
    return enriched


def looks_valid_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))
