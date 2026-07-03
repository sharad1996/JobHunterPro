"""
Regional job boards: Japan (TokyoDev, Japan Dev) and Middle East (Bayt).

TokyoDev and Japan Dev work with plain HTTP. Bayt often returns HTTP 403 without
Playwright — set USE_BROWSER_FETCH = True in config.py when Bayt returns zero jobs.
"""

import compat  # noqa: F401 — before requests/urllib3

import random
import re
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

import config
from job_filters import max_job_posting_age_days

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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


def _slug_to_name(slug: str) -> str:
    return " ".join(part.capitalize() for part in (slug or "").split("-") if part)


def _append_job(results: list, *, company: str, title: str, url: str, platform: str, country: str):
    company = (company or "").strip()
    title = (title or "").strip()
    url = (url or "").strip()
    if not company or not url:
        return
    results.append(
        {
            "company": company,
            "title": title,
            "url": url,
            "platform": platform,
            "domain": "",
            "search_country": country,
        }
    )


def scrape_tokyodev(job_title: str, max_results: int = 30) -> list:
    """TokyoDev — English-friendly tech jobs in Japan."""
    results = []
    print("  → Searching TokyoDev (Japan)...")
    tokens = _kw_tokens(job_title)
    try:
        r = requests.get(
            "https://www.tokyodev.com/jobs",
            headers=HEADERS,
            params={"q": job_title},
            timeout=25,
        )
        if r.status_code != 200:
            print(f"  ✗ TokyoDev: HTTP {r.status_code}")
            return results

        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for h4 in soup.select("h4"):
            link = h4.find("a", href=True)
            if not link:
                continue
            href = link.get("href") or ""
            if "/companies/" not in href or "/jobs/" not in href:
                continue
            title = h4.get_text(" ", strip=True) or link.get_text(" ", strip=True)
            if not title or not _matches_keywords(title, tokens):
                continue

            company = "Unknown"
            h3 = h4.find_previous("h3")
            if h3:
                company = h3.get_text(strip=True) or company
            else:
                block = h4.find_parent(["div", "section", "article"])
                if block:
                    inner = block.find("h3")
                    if inner:
                        company = inner.get_text(strip=True) or company

            full = href if href.startswith("http") else f"https://www.tokyodev.com{href}"
            key = full.split("?")[0].lower()
            if key in seen:
                continue
            seen.add(key)
            _append_job(
                results,
                company=company,
                title=title,
                url=full.split("?")[0],
                platform="TokyoDev",
                country="Japan",
            )
            if len(results) >= max_results:
                break

        print(f"  ✓ TokyoDev: {len(results)} results")
    except Exception as e:
        print(f"  ✗ TokyoDev error: {e}")
    _pause()
    return results


def scrape_japan_dev(job_title: str, max_results: int = 30) -> list:
    """Japan Dev — curated English-friendly tech jobs in Japan."""
    results = []
    print("  → Searching Japan Dev (Japan)...")
    tokens = _kw_tokens(job_title)
    job_path = re.compile(r"^/jobs/[^/]+/[^/]+$")
    try:
        r = requests.get(
            "https://japan-dev.com/jobs",
            headers=HEADERS,
            params={"q": job_title},
            timeout=25,
        )
        if r.status_code != 200:
            print(f"  ✗ Japan Dev: HTTP {r.status_code}")
            return results

        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for a in soup.select('a[href*="/jobs/"]'):
            href = (a.get("href") or "").split("?")[0]
            if not job_path.match(href):
                continue
            title = a.get_text(" ", strip=True)
            if len(title) < 4 or not _matches_keywords(title, tokens):
                continue

            parts = href.strip("/").split("/")
            company = _slug_to_name(parts[1]) if len(parts) >= 2 else "Unknown"
            full = href if href.startswith("http") else f"https://japan-dev.com{href}"
            key = full.lower()
            if key in seen:
                continue
            seen.add(key)
            _append_job(
                results,
                company=company,
                title=title,
                url=full,
                platform="Japan Dev",
                country="Japan",
            )
            if len(results) >= max_results:
                break

        print(f"  ✓ Japan Dev: {len(results)} results")
    except Exception as e:
        print(f"  ✗ Japan Dev error: {e}")
    _pause()
    return results


_BAYT_REGIONS = {
    "dubai": "uae",
    "uae": "uae",
    "united arab emirates": "uae",
    "saudi": "saudi-arabia",
    "saudi arabia": "saudi-arabia",
    "qatar": "qatar",
    "kuwait": "kuwait",
    "bahrain": "bahrain",
    "oman": "oman",
    "egypt": "egypt",
    "jordan": "jordan",
    "lebanon": "lebanon",
    "india": "india",
}


def _bayt_region(country: str) -> str:
    c = (country or "").lower().strip()
    for key, slug in _BAYT_REGIONS.items():
        if key in c:
            return slug
    return "international"


def _parse_bayt_html(html: str, job_title: str, location: str, max_results: int) -> list:
    """Best-effort Bayt job card parse from search results HTML."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    tokens = _kw_tokens(job_title)
    seen = set()

    selectors = (
        "li.has-pointer",
        "div.card",
        "article",
        'div[data-js-job]',
        'li[data-js-job]',
    )
    cards = []
    for sel in selectors:
        cards = soup.select(sel)
        if cards:
            break

    if not cards:
        for a in soup.select('a[href*="/jobs/"]'):
            href = a.get("href") or ""
            if "/jobs/search" in href or "/jobs/" not in href:
                continue
            title = a.get_text(" ", strip=True)
            if len(title) < 4:
                continue
            cards.append(a)

    for card in cards:
        try:
            if card.name == "a":
                link_el = card
                block = card.find_parent(["li", "div", "article"]) or card
            else:
                link_el = card.select_one('a[href*="/jobs/"]') or card.find("a", href=True)
                block = card
            if not link_el:
                continue
            href = (link_el.get("href") or "").strip()
            if not href or "search" in href.lower():
                continue
            title_el = (
                block.select_one("h2")
                or block.select_one("h3")
                or block.select_one('[class*="job-title"]')
                or link_el
            )
            title = title_el.get_text(" ", strip=True) if title_el else link_el.get_text(" ", strip=True)
            if len(title) < 4 or not _matches_keywords(title, tokens):
                continue
            company_el = (
                block.select_one('[class*="company"]')
                or block.select_one('[data-company-name]')
                or block.select_one("span.t-bold")
            )
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            full = href if href.startswith("http") else f"https://www.bayt.com{href}"
            key = full.split("?")[0].lower()
            if key in seen:
                continue
            seen.add(key)
            _append_job(
                out,
                company=company,
                title=title,
                url=full.split("?")[0],
                platform="Bayt",
                country=location,
            )
            if len(out) >= max_results:
                break
        except Exception:
            continue
    return out


def scrape_bayt(
    job_title: str,
    location: str = "Dubai",
    max_results: int = 30,
    remote_only: bool = False,
) -> list:
    """Bayt — Middle East job board (often needs Playwright)."""
    region = _bayt_region(location)
    kw = f"{job_title} remote" if remote_only else job_title
    label = f"Bayt ({location}" + (", remote)" if remote_only else ")")
    print(f"  → Searching {label}...")
    results = []
    jobs_url = f"https://www.bayt.com/en/{region}/jobs/"
    params = {"keywords": kw}
    try:
        r = requests.get(jobs_url, headers=HEADERS, params=params, timeout=25)
        html = r.text if r.status_code == 200 else None
        if html:
            results = _parse_bayt_html(html, job_title, location, max_results)

        if not results and getattr(config, "USE_BROWSER_FETCH", False):
            try:
                import browser_fetch

                full_url = jobs_url + "?" + urllib.parse.urlencode(params)
                html = browser_fetch.fetch_url(full_url)
                if html:
                    results = _parse_bayt_html(html, job_title, location, max_results)
            except Exception as e:
                print(f"  ⚠ Bayt (Playwright): {e}")

        if not results and r.status_code == 403:
            print(
                "  ✗ Bayt: Blocked (HTTP 403). Set USE_BROWSER_FETCH=True and install Playwright "
                "(see INTEGRATIONS.md), or search Bayt manually in a browser."
            )
        else:
            print(f"  ✓ Bayt ({location}): {len(results)} results")
    except Exception as e:
        print(f"  ✗ Bayt error: {e}")
    _pause()
    return results
