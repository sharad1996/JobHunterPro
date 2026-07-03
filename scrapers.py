"""
Job Scrapers — fetches job listings from Indeed, Naukri, Shine, LinkedIn, Glassdoor.
Each scraper returns a list of dicts:
  { company, title, url, platform, domain, search_country?, posted_at? }
"""

import compat  # noqa: F401 — before requests/urllib3

import os
import time
import random
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
import config
from job_filters import max_job_posting_age_days

from marketplace_boards import scrape_freelancer, scrape_upwork
from regional_boards import scrape_bayt, scrape_japan_dev, scrape_tokyodev
from remote_boards import (
    scrape_remoteok,
    scrape_remotive,
    scrape_weworkremotely_rss,
    scrape_justremote,
    scrape_skipthedrive,
    scrape_flexjobs,
    scrape_wellfound,
    scrape_himalayas,
)

# ─── Shared helpers ────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _get(url, params=None, timeout=15):
    """Safe GET with retry. Returns response only on HTTP 200."""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            time.sleep(2 ** attempt)
        except Exception:
            time.sleep(2 ** attempt)
    return None


def _print_fetch_failure(label: str, url: str, params=None, hint: str = ""):
    """One diagnostic request to explain why _get returned nothing (403, timeout, etc.)."""
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        code = r.status_code
        if code == 403:
            print(
                f"  ✗ {label}: Blocked (HTTP 403). The site rejects simple scripted requests; "
                "try the same search in a browser, or use a browser automation tool / official APIs."
            )
        elif code == 429:
            print(f"  ✗ {label}: Rate limited (HTTP 429). Wait and retry, or slow down requests.")
        else:
            print(f"  ✗ {label}: Could not get listings (HTTP {code}).")
        if hint:
            print(f"     {hint}")
    except Exception as e:
        print(f"  ✗ {label}: Could not connect ({e}).")
        if hint:
            print(f"     {hint}")


def _slug(text: str) -> str:
    """Convert 'Python Developer' → 'python-developer'."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _extract_domain(url: str) -> str:
    """Extract root domain from a URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.replace("www.", "")
        return host
    except Exception:
        return ""


def _pause():
    time.sleep(random.uniform(1.5, 3.5))


def _indeed_jobs_url(country: str) -> str:
    """Pick regional Indeed host from country label."""
    c = country.lower().strip()
    if "india" in c:
        return "https://in.indeed.com/jobs"
    if "united kingdom" in c or c in ("uk", "britain", "england", "scotland", "wales"):
        return "https://uk.indeed.com/jobs"
    if "germany" in c or c in ("de",):
        return "https://de.indeed.com/jobs"
    if "canada" in c:
        return "https://ca.indeed.com/jobs"
    if "australia" in c:
        return "https://au.indeed.com/jobs"
    if "united states" in c or c in ("us", "usa", "u.s.", "u.s.a."):
        return "https://www.indeed.com/jobs"
    return "https://www.indeed.com/jobs"


def _indeed_origin(jobs_url: str) -> str:
    """Site origin for resolving relative links, e.g. https://in.indeed.com"""
    return jobs_url.rsplit("/", 1)[0]


def _targets_india(countries: list) -> bool:
    return any("india" in (x or "").lower() for x in countries)


def _glassdoor_site(country: str) -> tuple:
    """(jobs_htm_url, locId) — rough Glassdoor region ids for search."""
    c = country.lower().strip()
    if "india" in c:
        return "https://www.glassdoor.co.in/Job/jobs.htm", 115
    if "united kingdom" in c or c == "uk":
        return "https://www.glassdoor.co.uk/Job/jobs.htm", 2
    if "germany" in c:
        return "https://www.glassdoor.de/Job/jobs.htm", 96
    if "canada" in c:
        return "https://www.glassdoor.ca/Job/jobs.htm", 3
    if "australia" in c:
        return "https://www.glassdoor.com.au/Job/jobs.htm", 5
    return "https://www.glassdoor.com/Job/jobs.htm", 1


def _glassdoor_origin(jobs_url: str) -> str:
    p = urllib.parse.urlparse(jobs_url)
    return f"{p.scheme}://{p.netloc}"


def _build_url(base: str, params: dict) -> str:
    if not params:
        return base
    q = urllib.parse.urlencode(params, doseq=True)
    sep = "&" if ("?" in base) else "?"
    return f"{base}{sep}{q}"


def _effective_platform_ids() -> list:
    """PLATFORMS plus optional groups controlled by INCLUDE_* flags in config."""
    pl = [p.lower() for p in config.PLATFORMS]
    seen = set(pl)

    def extend(names):
        for n in names:
            nl = (n or "").lower()
            if nl and nl not in seen:
                seen.add(nl)
                pl.append(nl)

    if getattr(config, "INCLUDE_STUB_PLATFORMS", False):
        extend(["himalayas", "flexjobs", "wellfound"])
    if getattr(config, "INCLUDE_MARKETPLACE_PLATFORMS", False):
        extend(["upwork"])
    if getattr(config, "INCLUDE_INDEED_GLASSDOOR", False):
        extend(["indeed", "glassdoor"])
    return pl


# ─── Indeed ────────────────────────────────────────────────────────────────────

def scrape_indeed(
    job_title: str,
    location: str = "India",
    max_results: int = 15,
    remote_only: bool = False,
) -> list:
    """Scrape Indeed job listings for one country/region."""
    results = []
    jobs_url = _indeed_jobs_url(location)
    origin = _indeed_origin(jobs_url)
    label = f"Indeed ({location}" + (", remote)" if remote_only else ")")
    print(f"  → Searching {label}...")
    try:
        import browser_fetch

        q = f"{job_title} remote" if remote_only else job_title
        params = {
            "q": q,
            "l": location,
            "sort": "date",
            "fromage": max_job_posting_age_days(),
        }
        if remote_only:
            params["remotejob"] = "1"

        html = None
        if getattr(config, "USE_BROWSER_FETCH", False):
            try:
                full_url = _build_url(jobs_url, params)
                storage = None
                if getattr(config, "INDEED_USE_AUTH_STATE", False):
                    p = config.auth_storage_path("indeed")
                    if os.path.isfile(p):
                        storage = p
                    else:
                        print(
                            "  ⚠ Indeed: INDEED_USE_AUTH_STATE=True but no session file — "
                            "run: python3 main.py --auth-indeed"
                        )
                html = browser_fetch.fetch_url(full_url, storage_state_path=storage)
            except Exception as e:
                print(f"  ⚠ Indeed (Playwright): {e}")

        if html is None:
            resp = _get(jobs_url, params=params)
            if not resp:
                _print_fetch_failure("Indeed", jobs_url, params)
                return results
            html = resp.text

        results = browser_fetch.parse_indeed_like_html(html, origin, job_title, location, max_results)

        print(f"  ✓ Indeed ({location}): {len(results)} results")
    except Exception as e:
        print(f"  ✗ Indeed error: {e}")
    _pause()
    return results


# ─── Naukri ────────────────────────────────────────────────────────────────────

def scrape_naukri(job_title: str, max_results: int = 15, remote_only: bool = False) -> list:
    """Scrape Naukri job listings (India-focused)."""
    results = []
    kw = f"{job_title} remote" if remote_only else job_title
    slug = _slug(kw)
    print("  → Searching Naukri (India, remote)..." if remote_only else "  → Searching Naukri...")
    try:
        age = max_job_posting_age_days()
        url = f"https://www.naukri.com/{slug}-jobs?jobAge={age}"
        resp = _get(url)
        if not resp:
            # Try search URL (often requires App Id / SystemId headers — may fail)
            resp = _get("https://www.naukri.com/jobapi/v3/search", params={
                "noOfResults": max_results,
                "urlType": "search_by_keyword",
                "searchType": "adv",
                "keyword": kw,
                "pageNo": 1,
                "seoKey": slug,
                "src": "jobsearchDesk",
                "latLong": "",
            })

        if not resp:
            print("  ✗ Naukri: Could not connect to listing/API")
            print(
                "     Naukri loads jobs in the browser; their API expects client headers. "
                "Open naukri.com in a browser for full results, or use browser automation."
            )
            return results

        # Try JSON API response first
        try:
            data = resp.json()
            job_list = data.get("jobDetails", [])
            for job in job_list[:max_results]:
                company = job.get("companyName", "").strip()
                job_url = job.get("jobUrl", "")
                if company:
                    results.append({
                        "company": company,
                        "title": job.get("title", job_title),
                        "url": f"https://www.naukri.com{job_url}" if job_url else "",
                        "platform": "Naukri",
                        "domain": "",
                        "search_country": "India",
                    })
        except Exception:
            # Fall back to HTML parsing
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("article.jobTuple") or soup.select("div.list")
            for card in cards[:max_results]:
                company_el = card.select_one("a.subTitle") or card.select_one(".companyInfo a")
                if not company_el:
                    continue
                company = company_el.get_text(strip=True)
                link_el = card.select_one("a.title")
                job_url = link_el["href"] if link_el else ""
                if company:
                    results.append({
                        "company": company,
                        "title": job_title,
                        "url": job_url,
                        "platform": "Naukri",
                        "domain": "",
                        "search_country": "India",
                    })

        if len(results) == 0 and "jobDetails\":[]" in resp.text and "loading\":true" in resp.text:
            print(
                "  ⚠ Naukri: Page loaded but job list is empty in static HTML (loaded by JavaScript). "
                "Use the website in a browser or automation; API calls need current app headers."
            )
        print(f"  ✓ Naukri: {len(results)} results")
    except Exception as e:
        print(f"  ✗ Naukri error: {e}")
    _pause()
    return results


# ─── Shine ─────────────────────────────────────────────────────────────────────

def scrape_shine(job_title: str, max_results: int = 15, remote_only: bool = False) -> list:
    """Scrape Shine.com job listings (India-focused)."""
    results = []
    kw = f"{job_title} remote" if remote_only else job_title
    slug = _slug(kw)
    print("  → Searching Shine (India, remote)..." if remote_only else "  → Searching Shine...")
    try:
        age = max_job_posting_age_days()
        url = f"https://www.shine.com/job-search/{slug}-jobs/?posted={age}"
        resp = _get(url)
        if not resp:
            print("  ✗ Shine: Could not connect")
            return results

        soup = BeautifulSoup(resp.text, "html.parser")
        # Shine redesign: job cards use jobCardNova_* classes; older li.job-listing-item may be gone
        cards = (
            soup.select("div.jobCardNova_bigCard__W2xn3")
            or soup.select("div[class*='jdbigCard']")
            or soup.select("li.job-listing-item")
            or soup.select("div.job_container")
        )

        for card in cards[:max_results]:
            try:
                link_el = card.select_one("a[href*='/jobs/']")
                company_el = (
                    card.select_one("span.jdTruncationCompany")
                    or card.select_one("span[class*='bigCardTopTitleName']")
                    or card.select_one("a.com_name")
                    or card.select_one(".company-name")
                )
                company = company_el.get_text(strip=True) if company_el else ""
                job_url = ""
                title_text = job_title
                if link_el:
                    href = link_el.get("href", "")
                    job_url = href if href.startswith("http") else f"https://www.shine.com{href}"
                    title_text = link_el.get_text(strip=True) or job_title

                if company:
                    results.append({
                        "company": company,
                        "title": title_text,
                        "url": job_url,
                        "platform": "Shine",
                        "domain": "",
                        "search_country": "India",
                    })
            except Exception:
                continue

        print(f"  ✓ Shine: {len(results)} results")
    except Exception as e:
        print(f"  ✗ Shine error: {e}")
    _pause()
    return results


# ─── LinkedIn ──────────────────────────────────────────────────────────────────

def scrape_linkedin(
    job_title: str,
    location: str = "India",
    max_results: int = 15,
    remote_only: bool = False,
) -> list:
    """Scrape LinkedIn public job search."""
    results = []
    kw = f"{job_title} remote" if remote_only else job_title
    label = f"LinkedIn ({location}" + (", remote)" if remote_only else ")")
    print(f"  → Searching {label}...")
    try:
        age_sec = max_job_posting_age_days() * 86400
        params = {
            "keywords": kw,
            "location": location,
            "f_TPR": f"r{age_sec}",
            "position": 1,
            "pageNum": 0,
        }
        if remote_only:
            params["f_WT"] = "2"   # Remote (on-site=1, hybrid=3, remote=2)

        resp = _get("https://www.linkedin.com/jobs/search/", params=params)
        if not resp:
            print("  ✗ LinkedIn: Could not connect (try with VPN or manually)")
            return results

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.base-card") or soup.select("li.jobs-search-results__list-item")

        for card in cards[:max_results]:
            try:
                company_el = card.select_one("h4.base-search-card__subtitle a") or card.select_one("a.hidden-nested-link")
                title_el   = card.select_one("h3.base-search-card__title")
                link_el    = card.select_one("a.base-card__full-link") or card.select_one("a[href*='/jobs/view/']")

                company = company_el.get_text(strip=True) if company_el else ""
                job_url = link_el["href"] if link_el else ""

                if company:
                    results.append({
                        "company": company,
                        "title": title_el.get_text(strip=True) if title_el else job_title,
                        "url": job_url,
                        "platform": "LinkedIn",
                        "domain": "",
                        "search_country": location,
                    })
            except Exception:
                continue

        print(f"  ✓ LinkedIn ({location}): {len(results)} results")
    except Exception as e:
        print(f"  ✗ LinkedIn error: {e}")
    _pause()
    return results


# ─── Glassdoor ─────────────────────────────────────────────────────────────────

def scrape_glassdoor(
    job_title: str,
    location: str = "India",
    max_results: int = 15,
    remote_only: bool = False,
) -> list:
    """Scrape Glassdoor job listings for one region."""
    results = []
    jobs_url, loc_id = _glassdoor_site(location)
    origin = _glassdoor_origin(jobs_url)
    kw = f"{job_title} remote" if remote_only else job_title
    label = f"Glassdoor ({location}" + (", remote)" if remote_only else ")")
    print(f"  → Searching {label}...")
    try:
        params = {
            "suggestCount": 0,
            "suggestChosen": "false",
            "clickSource": "searchBtn",
            "typedKeyword": kw,
            "sc.keyword": kw,
            "locT": "N",
            "locId": loc_id,
            "fromAge": max_job_posting_age_days(),
        }
        if remote_only:
            params["remoteWorkType"] = "1"

        import browser_fetch

        html = None
        if getattr(config, "USE_BROWSER_FETCH", False):
            try:
                full_url = _build_url(jobs_url, params)
                html = browser_fetch.fetch_url(full_url)
            except Exception as e:
                print(f"  ⚠ Glassdoor (Playwright): {e}")

        if html is None:
            resp = _get(jobs_url, params=params)
            if not resp:
                _print_fetch_failure("Glassdoor", jobs_url, params)
                return results
            html = resp.text

        results = browser_fetch.parse_glassdoor_like_html(html, origin, job_title, location, max_results)

        print(f"  ✓ Glassdoor ({location}): {len(results)} results")
    except Exception as e:
        print(f"  ✗ Glassdoor error: {e}")
    _pause()
    return results


# ─── Aggregate ─────────────────────────────────────────────────────────────────

# Platforms that run once (global / RSS / APIs), not per TARGET_COUNTRY
_GLOBAL_REMOTE_SCRAPERS = {
    "remoteok": scrape_remoteok,
    "remotive": scrape_remotive,
    "weworkremotely": scrape_weworkremotely_rss,
    "justremote": scrape_justremote,
    "skipthedrive": scrape_skipthedrive,
    "flexjobs": scrape_flexjobs,
    "wellfound": scrape_wellfound,
    "upwork": scrape_upwork,
    "freelancer": scrape_freelancer,
    "himalayas": scrape_himalayas,
    "tokyodev": scrape_tokyodev,
    "japan-dev": scrape_japan_dev,
}

# Per-country scrapers (not in _GLOBAL_REMOTE_SCRAPERS or India-only boards)
_PER_COUNTRY_SCRAPERS = {
    "indeed": scrape_indeed,
    "linkedin": scrape_linkedin,
    "glassdoor": scrape_glassdoor,
    "bayt": scrape_bayt,
}


def search_all_platforms(job_title: str) -> list:
    """
    Run all scrapers and return a de-duplicated combined list.

    If config.REMOTE_ONLY is True, uses config.TARGET_COUNTRIES and applies
    remote-oriented query/filter parameters. Indeed, LinkedIn, and Glassdoor
    run once per country. Naukri and Shine (India-only) run once if India is
    among the target countries (remote mode) or always in legacy single-location mode.

    Global boards (RemoteOK, Remotive, …) run once, in PLATFORMS order.
    """
    max_r = config.MAX_RESULTS_PER_PLATFORM
    remote = getattr(config, "REMOTE_ONLY", False)
    countries = (
        list(config.TARGET_COUNTRIES)
        if remote
        else [getattr(config, "JOB_LOCATION", "India")]
    )
    plats = _effective_platform_ids()
    all_jobs = []

    for platform in plats:
        fn = _GLOBAL_REMOTE_SCRAPERS.get(platform)
        if not fn:
            continue
        try:
            all_jobs.extend(fn(job_title, max_r))
        except Exception as e:
            print(f"  ✗ {platform} failed: {e}")

    for country in countries:
        for platform in plats:
            if platform in _GLOBAL_REMOTE_SCRAPERS or platform in ("naukri", "shine"):
                continue
            fn = _PER_COUNTRY_SCRAPERS.get(platform)
            if not fn:
                continue
            try:
                all_jobs.extend(fn(job_title, country, max_r, remote))
            except Exception as e:
                print(f"  ✗ {platform} ({country}) failed: {e}")

    india_eligible = (not remote) or _targets_india(countries)
    for platform in plats:
        if platform == "naukri" and india_eligible:
            try:
                all_jobs.extend(scrape_naukri(job_title, max_r, remote))
            except Exception as e:
                print(f"  ✗ naukri failed: {e}")
        elif platform == "shine" and india_eligible:
            try:
                all_jobs.extend(scrape_shine(job_title, max_r, remote))
            except Exception as e:
                print(f"  ✗ shine failed: {e}")

    # Drop identical URLs; company-level dedupe is done later in job_filters
    seen = set()
    unique = []
    for job in all_jobs:
        co = (job.get("company") or "").lower().strip()
        if not co:
            continue
        url = (job.get("url") or "").strip().lower()
        reg = (job.get("search_country") or "").strip().lower()
        key = (url, co, reg) if url else (co, job.get("title"), reg, job.get("platform"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)

    return unique
