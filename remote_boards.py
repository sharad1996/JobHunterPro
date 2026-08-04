"""
Additional remote job sources (APIs + RSS + light HTML).

Many sites are JS-heavy or login-gated; stubs log a short hint instead of failing silently.
"""

import compat  # noqa: F401 — before requests/urllib3

import os
import random
import re
import time
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

import config
from job_filters import parse_posted_at, posted_at_within_window

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# Jobicy `geo` slugs, keyed by TARGET_COUNTRIES labels. Only these values are valid —
# anything else returns HTTP 400, so unmapped countries (India, UAE, Vietnam, NZ…) are
# deliberately absent and get covered by the unfiltered sweep at the end instead.
# Verified live: germany, usa, uk, canada, australia, europe, singapore, japan, france,
# spain, netherlands, poland, ukraine, philippines.
_JOBICY_GEOS = {
    "germany": "germany",
    "united kingdom": "uk",
    "uk": "uk",
    "united states": "usa",
    "usa": "usa",
    "us": "usa",
    "canada": "canada",
    "australia": "australia",
    "singapore": "singapore",
    "japan": "japan",
    "france": "france",
    "spain": "spain",
    "netherlands": "netherlands",
    "poland": "poland",
    "ukraine": "ukraine",
    "philippines": "philippines",
}


def _pause():
    time.sleep(random.uniform(1.0, 2.2))


def _kw_tokens(job_title: str) -> list:
    return [t for t in re.split(r"[^\w+]+", (job_title or "").lower()) if len(t) > 1]


def _matches_keywords(text: str, tokens: list) -> bool:
    if not tokens:
        return True
    t = (text or "").lower()
    return any(tok in t for tok in tokens)


def _within_posting_window(posted_value) -> bool:
    dt = parse_posted_at(posted_value)
    if dt is None:
        return True
    return posted_at_within_window(dt)


def _remote_wanted() -> bool:
    return bool(getattr(config, "REMOTE_ONLY", False))


def scrape_arbeitnow(job_title: str, max_results: int = 50) -> list:
    """
    https://www.arbeitnow.com/api/job-board-api — free, no key, paginated.

    Returns Europe-heavy listings (many visa-sponsor / English-speaking roles) with a
    clean shape: company_name, title, url, location, remote, created_at (epoch seconds).
    """
    results = []
    print("  → Searching Arbeitnow (API)...")
    tokens = _kw_tokens(job_title)
    seen = set()
    try:
        pages = max(1, int(getattr(config, "ARBEITNOW_MAX_PAGES", 3)))
        for page in range(1, pages + 1):
            r = requests.get(
                "https://www.arbeitnow.com/api/job-board-api",
                headers=HEADERS,
                params={"page": page},
                timeout=25,
            )
            if r.status_code != 200:
                print(f"  ✗ Arbeitnow: HTTP {r.status_code}")
                break
            jobs = (r.json() or {}).get("data") or []
            if not jobs:
                break
            for j in jobs:
                company = (j.get("company_name") or "").strip()
                title = (j.get("title") or "").strip()
                url = (j.get("url") or "").strip()
                if not (company and url):
                    continue
                tag_blob = " ".join(j.get("tags") or []) + " " + " ".join(j.get("job_types") or [])
                if not _matches_keywords(f"{title} {tag_blob}", tokens):
                    continue
                if not _within_posting_window(j.get("created_at")):
                    continue
                if _remote_wanted() and not j.get("remote"):
                    # keep explicit remote listings only when REMOTE_ONLY is set
                    if "remote" not in f"{title} {j.get('location') or ''}".lower():
                        continue
                key = url.split("?")[0].lower()
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    {
                        "company": company,
                        "title": title or job_title,
                        "url": url,
                        "platform": "Arbeitnow",
                        "domain": "",
                        "search_country": (j.get("location") or "Global").strip() or "Global",
                        "posted_at": j.get("created_at"),
                    }
                )
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
            _pause()
        print(f"  ✓ Arbeitnow: {len(results)} results")
    except Exception as e:
        print(f"  ✗ Arbeitnow error: {e}")
    _pause()
    return results


def scrape_jobicy(job_title: str, max_results: int = 50) -> list:
    """
    https://jobicy.com/api/v2/remote-jobs — free, no key, remote-only by definition.

    `geo` accepts region slugs (india, europe, usa, apac…); we query the configured
    TARGET_COUNTRIES that Jobicy recognises, then fall back to an unfiltered call.
    """
    results = []
    print("  → Searching Jobicy (API)...")
    tokens = _kw_tokens(job_title)
    seen = set()

    geos = []
    for c in (getattr(config, "TARGET_COUNTRIES", None) or []):
        slug = _JOBICY_GEOS.get((c or "").lower().strip())
        if slug and slug not in geos:
            geos.append(slug)
    geos.append(None)  # unfiltered sweep last

    try:
        for geo in geos:
            if len(results) >= max_results:
                break
            params = {"count": 50, "tag": job_title}
            if geo:
                params["geo"] = geo
            r = requests.get(
                "https://jobicy.com/api/v2/remote-jobs",
                headers=HEADERS,
                params=params,
                timeout=25,
            )
            if r.status_code != 200:
                print(f"  ✗ Jobicy ({geo or 'all'}): HTTP {r.status_code}")
                continue
            jobs = (r.json() or {}).get("jobs") or []
            for j in jobs:
                company = (j.get("companyName") or "").strip()
                title = (j.get("jobTitle") or "").strip()
                url = (j.get("url") or "").strip()
                if not (company and url):
                    continue
                industry = " ".join(j.get("jobIndustry") or [])
                if not _matches_keywords(f"{title} {industry}", tokens):
                    continue
                if not _within_posting_window(j.get("pubDate")):
                    continue
                key = url.split("?")[0].lower()
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    {
                        "company": company,
                        "title": title or job_title,
                        "url": url,
                        "platform": "Jobicy",
                        "domain": "",
                        "search_country": (j.get("jobGeo") or "Global").strip() or "Global",
                        "posted_at": j.get("pubDate"),
                    }
                )
                if len(results) >= max_results:
                    break
            _pause()
        print(f"  ✓ Jobicy: {len(results)} results")
    except Exception as e:
        print(f"  ✗ Jobicy error: {e}")
    _pause()
    return results


def scrape_remoteok(job_title: str, max_results: int = 50) -> list:
    """https://remoteok.com/api — global remote listings."""
    results = []
    print("  → Searching RemoteOK (API)...")
    try:
        r = requests.get("https://remoteok.com/api", headers=HEADERS, timeout=25)
        if r.status_code != 200:
            print(f"  ✗ RemoteOK: HTTP {r.status_code}")
            return results
        data = r.json()
        if not isinstance(data, list):
            print("  ✗ RemoteOK: unexpected JSON")
            return results
        tokens = _kw_tokens(job_title)
        for item in data[1:]:  # [0] is legal/meta
            if not isinstance(item, dict):
                continue
            if not item.get("company"):
                continue
            company = (item.get("company") or "").strip()
            title = (item.get("position") or "").strip()
            slug = item.get("slug") or item.get("id") or ""
            url = (item.get("url") or "").strip()
            if not url and slug:
                url = f"https://remoteok.com/remote-jobs/{slug}"
            tags = " ".join(item.get("tags") or [])
            blob = f"{title} {tags} {company}"
            if not _matches_keywords(blob, tokens):
                continue
            posted = item.get("date") or item.get("epoch")
            if not _within_posting_window(posted):
                continue
            if company and url:
                results.append(
                    {
                        "company": company,
                        "title": title or job_title,
                        "url": url,
                        "platform": "RemoteOK",
                        "domain": "",
                        "search_country": "Global",
                        "posted_at": posted,
                    }
                )
            if len(results) >= max_results:
                break
        print(f"  ✓ RemoteOK: {len(results)} results")
    except Exception as e:
        print(f"  ✗ RemoteOK error: {e}")
    _pause()
    return results


def scrape_remotive(job_title: str, max_results: int = 50) -> list:
    """https://remotive.com/api/remote-jobs — public API."""
    results = []
    print("  → Searching Remotive (API)...")
    try:
        params = {"search": job_title}
        r = requests.get(
            "https://remotive.com/api/remote-jobs",
            headers=HEADERS,
            params=params,
            timeout=25,
        )
        if r.status_code != 200:
            print(f"  ✗ Remotive: HTTP {r.status_code}")
            return results
        jobs = r.json().get("jobs") or []
        for j in jobs[: max_results * 3]:
            company = (j.get("company_name") or "").strip()
            title = (j.get("title") or "").strip()
            url = (j.get("url") or "").strip()
            posted = j.get("publication_date")
            if not _within_posting_window(posted):
                continue
            if company and url:
                results.append(
                    {
                        "company": company,
                        "title": title or job_title,
                        "url": url,
                        "platform": "Remotive",
                        "domain": "",
                        "search_country": "Global",
                        "posted_at": posted,
                    }
                )
            if len(results) >= max_results:
                break
        print(f"  ✓ Remotive: {len(results)} results")
    except Exception as e:
        print(f"  ✗ Remotive error: {e}")
    _pause()
    return results


def scrape_weworkremotely_rss(job_title: str, max_results: int = 50) -> list:
    """We Work Remotely — programming category RSS."""
    results = []
    print("  → Searching We Work Remotely (RSS)...")
    url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
    tokens = _kw_tokens(job_title)
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200:
            print(f"  ✗ We Work Remotely: HTTP {r.status_code}")
            return results
        root = ET.fromstring(r.content)
        for item in root.findall(".//item"):
            title_el = item.findtext("title") or ""
            link_el = item.findtext("link") or ""
            pub_date = item.findtext("pubDate") or ""
            # "Company: Role — …"
            company = "Unknown"
            title = title_el
            if ":" in title_el:
                parts = title_el.split(":", 1)
                company = parts[0].strip()
                title = parts[1].strip() if len(parts) > 1 else title_el
            if not _matches_keywords(title_el, tokens):
                continue
            if not _within_posting_window(pub_date):
                continue
            if link_el and company:
                results.append(
                    {
                        "company": company,
                        "title": title or job_title,
                        "url": link_el.strip(),
                        "platform": "WeWorkRemotely",
                        "domain": "",
                        "search_country": "Global",
                        "posted_at": pub_date,
                    }
                )
            if len(results) >= max_results:
                break
        print(f"  ✓ We Work Remotely: {len(results)} results")
    except Exception as e:
        print(f"  ✗ We Work Remotely error: {e}")
    _pause()
    return results


def scrape_justremote(job_title: str, max_results: int = 30) -> list:
    """JustRemote — best-effort HTML (site is often JS-rendered)."""
    results = []
    print("  → Searching JustRemote (HTML)...")
    try:
        r = requests.get(
            "https://justremote.co/remote-jobs",
            headers=HEADERS,
            params={"search": job_title},
            timeout=20,
        )
        if r.status_code != 200:
            print(f"  ✗ JustRemote: HTTP {r.status_code}")
            return results
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select('a[href*="/remote-jobs/"]'):
            href = a.get("href") or ""
            if "/remote-jobs/new" in href or not href.startswith("/"):
                continue
            text = a.get_text(" ", strip=True)
            if len(text) < 8:
                continue
            if not _matches_keywords(text, _kw_tokens(job_title)):
                continue
            full = f"https://justremote.co{href}" if href.startswith("/") else href
            company = "Unknown"
            title = text
            if " at " in text.lower():
                idx = text.lower().rfind(" at ")
                title, company = text[:idx].strip(), text[idx + 4 :].strip()
            elif ":" in text:
                company, _, title = text.partition(":")
                company, title = company.strip(), title.strip()
            results.append(
                {
                    "company": company or "Unknown",
                    "title": title or job_title,
                    "url": full,
                    "platform": "JustRemote",
                    "domain": "",
                    "search_country": "Global",
                }
            )
            if len(results) >= max_results:
                break
        print(f"  ✓ JustRemote: {len(results)} results")
    except Exception as e:
        print(f"  ✗ JustRemote error: {e}")
    _pause()
    return results


def scrape_skipthedrive(job_title: str, max_results: int = 30) -> list:
    """SkipTheDrive — best-effort WordPress search."""
    results = []
    print("  → Searching SkipTheDrive (HTML)...")
    try:
        r = requests.get(
            "https://www.skipthedrive.com/",
            headers=HEADERS,
            params={"s": job_title, "post_type": "job_listing"},
            timeout=20,
        )
        if r.status_code != 200:
            print(f"  ✗ SkipTheDrive: HTTP {r.status_code}")
            return results
        soup = BeautifulSoup(r.text, "html.parser")
        for art in soup.select("article, li.job_listing, div.job"):
            a = art.select_one("a[href*='skipthedrive.com']")
            if not a:
                continue
            href = a.get("href") or ""
            title = a.get_text(strip=True)
            if len(title) < 6 or "http" not in href:
                continue
            if not _matches_keywords(title, _kw_tokens(job_title)):
                continue
            company = "Unknown"
            sub = art.select_one(".company, .employer, .job-company")
            if sub:
                company = sub.get_text(strip=True) or company
            results.append(
                {
                    "company": company,
                    "title": title,
                    "url": href.split("#")[0],
                    "platform": "SkipTheDrive",
                    "domain": "",
                    "search_country": "Global",
                }
            )
            if len(results) >= max_results:
                break
        print(f"  ✓ SkipTheDrive: {len(results)} results")
    except Exception as e:
        print(f"  ✗ SkipTheDrive error: {e}")
    _pause()
    return results


def scrape_flexjobs(job_title: str, max_results: int = 30) -> list:
    print(
        "  → FlexJobs: skipped — paid membership / login required "
        "(remove from PLATFORMS or set INCLUDE_STUB_PLATFORMS=False)"
    )
    return []


def scrape_wellfound(job_title: str, max_results: int = 30) -> list:
    """Wellfound is JS-heavy and often 403 for raw requests; optional Playwright path."""
    print("  → Searching Wellfound…")
    if getattr(config, "USE_BROWSER_FETCH", False):
        try:
            import browser_fetch

            storage = None
            if getattr(config, "WELLFOUND_USE_AUTH_STATE", False):
                p = config.auth_storage_path("wellfound")
                if os.path.isfile(p):
                    storage = p
                else:
                    print(
                        "  ⚠ Wellfound: WELLFOUND_USE_AUTH_STATE=True but no session file — "
                        "run: python3 main.py --auth-wellfound"
                    )
            html = browser_fetch.fetch_url(
                "https://wellfound.com/jobs",
                params={"query": job_title},
                storage_state_path=storage,
            )
            results = browser_fetch.parse_wellfound_jobs_html(html, job_title, max_results)
            print(f"  ✓ Wellfound (browser): {len(results)} results")
            return results
        except Exception as e:
            print(f"  ✗ Wellfound (browser): {e}")
            return []
    print(
        "  → Wellfound: skipped — set USE_BROWSER_FETCH=True + Playwright "
        "(see INTEGRATIONS.md) or use the site manually"
    )
    return []


def _parse_himalayas_rss(content: bytes, job_title: str, max_results: int) -> list:
    """Parse Himalayas Atom RSS (100 most recent remote jobs)."""
    results = []
    tokens = _kw_tokens(job_title)
    soup = BeautifulSoup(content, "xml")
    entries = soup.find_all("entry") or soup.find_all("item")
    for entry in entries:
        title_el = entry.find("title")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title or not _matches_keywords(title, tokens):
            continue

        link_el = entry.find("link", href=True) or entry.find("link")
        url = ""
        if link_el is not None:
            url = (link_el.get("href") or link_el.get_text(strip=True) or "").strip()
        if not url:
            id_el = entry.find("id")
            if id_el:
                url = id_el.get_text(strip=True)
        if not url:
            continue

        company = "Unknown"
        for child in entry.children:
            if getattr(child, "name", None) and "companyName" in child.name:
                company = child.get_text(strip=True) or company
                break

        pub_el = entry.find("published") or entry.find("updated") or entry.find("pubDate")
        posted = pub_el.get_text(strip=True) if pub_el else None
        if not _within_posting_window(posted):
            continue

        results.append(
            {
                "company": company,
                "title": title,
                "url": url.split("?")[0],
                "platform": "Himalayas",
                "domain": "",
                "search_country": "Global",
                "posted_at": posted,
            }
        )
        if len(results) >= max_results:
            break
    return results


def scrape_himalayas(job_title: str, max_results: int = 30) -> list:
    """Himalayas — public RSS feed (no auth); optional Playwright keyword search as fallback."""
    print("  → Searching Himalayas (RSS)...")
    results = []
    try:
        r = requests.get("https://himalayas.app/jobs/rss", headers=HEADERS, timeout=25)
        if r.status_code == 200:
            results = _parse_himalayas_rss(r.content, job_title, max_results)
        else:
            print(f"  ✗ Himalayas RSS: HTTP {r.status_code}")
    except Exception as e:
        print(f"  ✗ Himalayas RSS error: {e}")

    if not results and getattr(config, "USE_BROWSER_FETCH", False):
        try:
            import browser_fetch

            html = browser_fetch.fetch_url(
                "https://himalayas.app/jobs",
                params={"q": job_title},
            )
            results = browser_fetch.parse_himalayas_jobs_html(html, job_title, max_results)
            print(f"  ✓ Himalayas (browser): {len(results)} results")
            return results
        except Exception as e:
            print(f"  ✗ Himalayas (browser): {e}")

    print(f"  ✓ Himalayas: {len(results)} results")
    _pause()
    return results
