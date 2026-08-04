"""
Email Finder — locates HR/recruiter email addresses for a company.

Strategy (in order):
  1. Infer corporate domain from job posting URL (ATS / careers subdomains)
  2. DuckDuckGo instant answer, then optional HTML search fallback
  3. Normalized company-name → simple domain guesses (e.g. acme.com)
  4. Scrape company website contact / contact-us pages for published emails
  5. Pattern guessing (hr@, careers@, …) on the best domain candidate (unverified)
"""

import compat  # noqa: F401 — before requests/urllib3

import re
import time
from urllib.parse import urljoin, urlparse

import requests
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

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9][a-zA-Z0-9._%+\-]*@[a-zA-Z0-9][a-zA-Z0-9.\-]*\.[a-zA-Z]{2,}",
)

_EMAIL_JUNK_LOCAL = (
    "noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon",
    "postmaster", "abuse", "unsubscribe", "newsletter", "marketing",
    "privacy", "legal", "dmca", "webmaster", "sentry", "wixpress",
    "example", "test", "placeholder", "yourname", "email@",
    # Documentation/mockup names. Contact pages and form placeholders are full of these,
    # and they were being saved as *verified* addresses (e.g. john.doe@company.com).
    # NOTE: these are matched as SUBSTRINGS of the local part, so every entry must be
    # long and distinctive — "bar" would blocklist barbara@, "foo" would hit foods@.
    "john.doe", "johndoe", "jane.doe", "janedoe", "john.smith", "johnsmith",
    "jane.smith", "janesmith", "firstname", "first.last", "lastname",
    "fullname", "your.name", "yourname", "your.email", "youremail",
    "lorem", "ipsum", "dummyemail", "placeholder",
)

_EMAIL_JUNK_DOMAINS = (
    "example.com", "email.com", "domain.com", "sentry.io", "wix.com",
    "schema.org", "w3.org", "googleapis.com", "cloudflare.com",
    "facebook.com", "twitter.com", "linkedin.com", "instagram.com",
    "youtube.com", "gravatar.com", "github.com",
    # Placeholder domains that appear in sample markup, never real employers.
    "company.com", "acme.com", "acme.co", "doe.com", "yourcompany.com",
    "yourdomain.com", "mycompany.com", "example.org", "example.net",
    "test.com", "sample.com", "domain.co", "site.com", "website.com",
    "placeholder.com", "lorem.com", "foo.com", "bar.com", "email.address",
)

_HR_LOCAL_KEYWORDS = (
    "hr", "career", "careers", "jobs", "job", "recruit", "recruiting",
    "talent", "hiring", "people", "humanresources", "employment",
    "contact", "info", "hello", "enquiry", "inquiry", "support",
)

_CONTACT_LINK_KEYWORDS = (
    "contact", "get-in-touch", "getintouch", "reach-us", "reachus",
    "contact-us", "contactus", "write-us", "talk-to-us",
)


def _contact_scrape_use_browser() -> bool:
    explicit = getattr(config, "CONTACT_SCRAPE_USE_BROWSER", None)
    if explicit is not None:
        return bool(explicit)
    return bool(getattr(config, "USE_BROWSER_FETCH", False))


def _fetch_page_html(url: str) -> str:
    """Fetch page HTML via HTTP; optionally Playwright when configured."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=14, allow_redirects=True)
        if resp.status_code == 200 and resp.text and len(resp.text) > 200:
            return resp.text
    except Exception:
        pass

    if not _contact_scrape_use_browser():
        return ""

    try:
        import browser_fetch

        return browser_fetch.fetch_url(url, timeout_ms=45000) or ""
    except Exception:
        return ""


def _decode_email_obfuscation(text: str) -> str:
    """Normalize common obfuscations: user [at] domain [dot] com."""
    t = text or ""
    t = re.sub(r"\s*\[\s*at\s*\]\s*", "@", t, flags=re.I)
    t = re.sub(r"\s*\(\s*at\s*\)\s*", "@", t, flags=re.I)
    t = re.sub(r"\s+at\s+", "@", t, flags=re.I)
    t = re.sub(r"\s*\[\s*dot\s*\]\s*", ".", t, flags=re.I)
    t = re.sub(r"\s*\(\s*dot\s*\)\s*", ".", t, flags=re.I)
    return t


def is_junk_email(email: str) -> bool:
    """Public alias — also used to screen addresses replayed from the database."""
    return _is_junk_email(email)


def _is_junk_email(email: str) -> bool:
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return True
    local, _, domain = e.partition("@")
    if any(j in local for j in _EMAIL_JUNK_LOCAL):
        return True
    if any(domain == d or domain.endswith("." + d) for d in _EMAIL_JUNK_DOMAINS):
        return True
    if e.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
        return True
    return False


def _extract_emails_from_html(html: str) -> list:
    if not html:
        return []
    text = _decode_email_obfuscation(html)
    found = []
    seen = set()

    for match in _EMAIL_RE.findall(text):
        em = match.strip().rstrip(".,;:)")
        key = em.lower()
        if key in seen or _is_junk_email(em):
            continue
        seen.add(key)
        found.append(em)

    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('a[href^="mailto:"]'):
            href = (a.get("href") or "").split("?", 1)[0]
            raw = href.replace("mailto:", "").strip()
            if raw and not _is_junk_email(raw):
                key = raw.lower()
                if key not in seen:
                    seen.add(key)
                    found.append(raw)
    except Exception:
        pass

    return found


def _email_domain_match(email: str, domain: str) -> bool:
    dom = (domain or "").lower().replace("www.", "")
    ed = (email.split("@")[-1] if "@" in email else "").lower()
    if not dom or not ed:
        return False
    return ed == dom or ed.endswith("." + dom) or dom.endswith("." + ed)


def _score_email_for_hr(email: str, domain: str) -> int:
    e = email.lower()
    local = e.split("@", 1)[0]
    score = 0
    if _email_domain_match(email, domain):
        score += 50
    for i, kw in enumerate(_HR_LOCAL_KEYWORDS):
        if kw in local:
            score += 30 - min(i, 20)
            break
    if any(x in local for x in ("sales", "billing", "invoice", "press", "media", "pr@")):
        score -= 15
    return score


def _pick_best_hr_email(emails: list, domain: str) -> str:
    if not emails:
        return ""
    on_domain = [e for e in emails if _email_domain_match(e, domain)]
    pool = on_domain if on_domain else emails
    ranked = sorted(pool, key=lambda e: _score_email_for_hr(e, domain), reverse=True)
    return ranked[0] if ranked else ""


def _discover_contact_urls(html: str, base_url: str, domain: str) -> list:
    """Find contact-page links from homepage navigation."""
    urls = []
    seen = set()
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return urls

    dom = domain.lower().replace("www.", "")
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        text = (a.get_text() or "").lower()
        path = href.lower()
        if not any(k in path or k in text for k in _CONTACT_LINK_KEYWORDS):
            continue
        full = urljoin(base_url, href)
        try:
            p = urlparse(full)
        except Exception:
            continue
        host = (p.netloc or "").lower().replace("www.", "")
        if host and host != dom and not host.endswith("." + dom):
            continue
        if full not in seen:
            seen.add(full)
            urls.append(full)
    return urls[:8]


def _urls_for_domain(domain: str) -> list:
    """Ordered URLs to fetch for contact-page email discovery."""
    dom = (domain or "").strip().lower().replace("www.", "")
    if not dom or "." not in dom:
        return []

    paths = getattr(config, "CONTACT_PAGE_PATHS", ()) or (
        "/contact", "/contact-us", "/contactus",
    )
    hosts = [dom]
    if not dom.startswith("www."):
        hosts.append(f"www.{dom}")

    urls = []
    seen = set()
    for host in hosts:
        for path in paths:
            path = path if path.startswith("/") else f"/{path}"
            for scheme in ("https", "http"):
                u = f"{scheme}://{host}{path}"
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
        if getattr(config, "CONTACT_SCRAPE_HOMEPAGE", True):
            for scheme in ("https", "http"):
                u = f"{scheme}://{host}/"
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
    return urls


def scrape_contact_page_emails(domain: str) -> dict:
    """
    Visit company contact pages and extract a suitable HR/contact email.
    Returns: { hr_email, hr_name, hr_email_verified, contact_source_url } or {}.
    """
    if not getattr(config, "CONTACT_PAGE_SCRAPE_ENABLED", True):
        return {}

    dom = (domain or "").strip().lower().replace("www.", "")
    if not dom:
        return {}

    all_emails = []
    source_url = ""
    extra_urls = []
    fetch_urls = _urls_for_domain(dom)

    for url in fetch_urls:
        html = _fetch_page_html(url)
        if not html:
            continue
        emails = _extract_emails_from_html(html)
        if emails and not source_url:
            source_url = url
        all_emails.extend(emails)

        if getattr(config, "CONTACT_SCRAPE_HOMEPAGE", True) and url.rstrip("/").endswith(dom):
            extra_urls.extend(_discover_contact_urls(html, url, dom))

        if all_emails and _pick_best_hr_email(all_emails, dom):
            break
        time.sleep(0.12)

    for url in extra_urls:
        if url in fetch_urls:
            continue
        html = _fetch_page_html(url)
        if not html:
            continue
        emails = _extract_emails_from_html(html)
        if emails:
            if not source_url:
                source_url = url
            all_emails.extend(emails)
            if _pick_best_hr_email(all_emails, dom):
                break
        time.sleep(0.12)

    best = _pick_best_hr_email(all_emails, dom)
    if not best:
        return {}

    out = {
        "hr_email": best,
        "hr_name": "",
        "hr_email_verified": True,
    }
    if source_url:
        out["contact_source_url"] = source_url
    return out


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


def domain_from_website_field(website: str) -> str:
    """Normalize Company website cell (URL or bare domain) to a hostname."""
    w = (website or "").strip()
    if not w:
        return ""
    if "@" in w:
        return ""
    if not w.startswith(("http://", "https://")):
        w = "https://" + w
    try:
        host = urlparse(w).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host if "." in host else ""


def collect_domain_candidates(
    company: str, job_url: str, company_website: str = ""
) -> list:
    """Ordered unique domain candidates to try for contact-page scraping."""
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

    add(domain_from_website_field(company_website))

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


def domain_blocked_for_guessing(domain: str) -> bool:
    """True if we should not fabricate hr@… addresses on this host (consumer / wrong DDG hits)."""
    d = (domain or "").strip().lower().replace("www.", "")
    if not d or "." not in d:
        return True
    blocked = getattr(config, "BLOCKED_GUESS_EMAIL_DOMAINS", ()) or ()
    for b in blocked:
        b = (b or "").strip().lower()
        if not b:
            continue
        if d == b or d.endswith("." + b):
            return True
    return False


def guess_hr_emails(domain: str) -> list:
    if not domain:
        return []
    return [f"{prefix}@{domain}" for prefix in COMMON_HR_PREFIXES]


# ─── Main entry ────────────────────────────────────────────────────────────────

def find_hr_email_for_company(
    company: str,
    job_url: str = "",
    company_website: str = "",
    *,
    allow_guesses: bool = True,
) -> dict:
    """
    Resolve one HR/contact email for a company (contact pages, then optional guess).
    Returns dict with hr_email, hr_email_verified, domain, contact_source_url, etc.
    """
    company = (company or "").strip()
    result: dict = {}
    candidates = collect_domain_candidates(company, job_url, company_website)

    chosen_domain = ""
    for dom in candidates:
        chosen_domain = dom
        if getattr(config, "CONTACT_PAGE_SCRAPE_ENABLED", True):
            result = scrape_contact_page_emails(dom)
            if result.get("hr_email"):
                result["domain"] = dom
                break

    if not result.get("hr_email") and chosen_domain:
        result["domain"] = chosen_domain

    if not result.get("hr_email"):
        for dom in candidates:
            if getattr(config, "CONTACT_PAGE_SCRAPE_ENABLED", True):
                result = scrape_contact_page_emails(dom)
                if result.get("hr_email"):
                    result["domain"] = dom
                    break

    if not result.get("hr_email") and allow_guesses:
        for dom in candidates:
            if domain_blocked_for_guessing(dom):
                continue
            guesses = guess_hr_emails(dom)
            if guesses:
                result = {
                    "hr_email": guesses[0],
                    "hr_email_verified": False,
                    "domain": dom,
                    "hr_email_guesses": guesses,
                }
                break

    if not result.get("domain") and candidates:
        result["domain"] = candidates[0]
    result.setdefault("domain_candidates", candidates)
    return result


def find_hr_emails(jobs: list, history=None) -> list:
    """
    Enriches each job dict with `hr_email` and `hr_name` fields.

    When `history` (an OutreachHistory) is supplied, companies whose address is already
    in the database reuse it instead of re-scraping contact pages — the lookup costs
    several HTTP requests per company, so this is where the time goes.
    """
    print("\n📧 Finding company domains & HR emails (contact pages)…")
    if not getattr(config, "CONTACT_PAGE_SCRAPE_ENABLED", True):
        print(
            "  ⚠️  CONTACT_PAGE_SCRAPE_ENABLED is False — only pattern guesses will be used."
        )

    enriched = []
    total = len(jobs)
    reused = 0

    for i, job in enumerate(jobs, 1):
        company = job.get("company", "") or ""
        job_url = job.get("url", "") or ""
        print(f"  [{i}/{total}] {company[:56]}", end="  ", flush=True)

        cached = history.known_email(company) if history is not None else None
        if cached:
            result = dict(cached)
            reused += 1
        else:
            result = find_hr_email_for_company(company, job_url)
        job["domain_candidates"] = result.get("domain_candidates") or []
        if result.get("domain"):
            job["domain"] = result["domain"]

        if result.get("hr_email"):
            if cached:
                note = "  [known company email — lookup skipped]"
            elif result.get("hr_email_verified"):
                note = "  [contact page]" if result.get("contact_source_url") else ""
            else:
                note = "  [guessed — not on contact page]"
            job.update(result)
            print(f"→ {result.get('hr_email', '?')}{note}")
        else:
            job["hr_email"] = ""
            cands = result.get("domain_candidates") or []
            job["domain"] = job.get("domain") or (cands[0] if cands else "")
            print("→ Not found (use job URL to apply on-site or find contacts manually)")

        enriched.append(job)
        if not cached:
            time.sleep(0.25)

    found = sum(1 for j in enriched if j.get("hr_email"))
    verified = sum(1 for j in enriched if j.get("hr_email") and j.get("hr_email_verified"))
    suffix = f" — {reused} reused a known address (no lookup)" if reused else ""
    print(
        f"\n  ✅ Resolved at least one address for {found}/{total} listing(s) "
        f"({verified} from contact pages){suffix}"
    )
    return enriched


def looks_valid_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))
