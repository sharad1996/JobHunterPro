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


def scrape_himalayas(job_title: str, max_results: int = 30) -> list:
    """Himalayas is client-rendered; use Playwright when enabled."""
    print("  → Searching Himalayas…")
    if getattr(config, "USE_BROWSER_FETCH", False):
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
            return []
    print(
        "  → Himalayas: skipped — set USE_BROWSER_FETCH=True + Playwright "
        "(see INTEGRATIONS.md)"
    )
    return []
