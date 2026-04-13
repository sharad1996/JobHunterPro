"""
Optional Playwright-based HTML fetch for bot-prone or JS-heavy job sites.

Requires: pip install playwright && playwright install chromium
Enable in config: USE_BROWSER_FETCH = True
"""

import urllib.parse
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup


def _build_url(url: str, params: Optional[dict]) -> str:
    if not params:
        return url
    q = urllib.parse.urlencode(params, doseq=True)
    sep = "&" if ("?" in url) else "?"
    return f"{url}{sep}{q}"


def fetch_url(url: str, params: Optional[dict] = None, timeout_ms: int = 60000) -> str:
    """Return page HTML after Chromium loads the URL."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from e

    full = _build_url(url, params)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(full, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2500)
            return page.content()
        finally:
            browser.close()


def parse_indeed_like_html(html: str, origin: str, job_title: str, location: str, max_results: int) -> List[Dict[str, Any]]:
    """Shared DOM parse for Indeed (same selectors as requests path)."""
    soup = BeautifulSoup(html, "html.parser")
    cards = (
        soup.select("div.job_seen_beacon")
        or soup.select("div[class*='jobCard']")
        or soup.select("td.resultContent")
    )
    out = []
    for card in cards[:max_results]:
        try:
            company_el = card.select_one("span[data-testid='company-name']") or card.select_one(".companyName")
            if not company_el:
                continue
            company = company_el.get_text(strip=True)
            link_el = card.select_one("a[data-jk]") or card.select_one("h2.jobTitle a")
            job_url = ""
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("/"):
                    job_url = urllib.parse.urljoin(origin + "/", href.lstrip("/"))
                elif href.startswith("http"):
                    job_url = href
                else:
                    job_url = urllib.parse.urljoin(origin + "/", href)
            if company:
                out.append(
                    {
                        "company": company,
                        "title": job_title,
                        "url": job_url,
                        "platform": "Indeed",
                        "domain": "",
                        "search_country": location,
                    }
                )
        except Exception:
            continue
    return out


def parse_glassdoor_like_html(
    html: str, origin: str, job_title: str, location: str, max_results: int
) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    cards = (
        soup.select("li.react-job-listing")
        or soup.select("li[data-test='jobListing']")
        or soup.select("div.jobContainer")
    )
    out = []
    for card in cards[:max_results]:
        try:
            company_el = (
                card.select_one("div.job-search-key-ow3ely")
                or card.select_one("[data-test='employer-name']")
                or card.select_one("span.css-63koeb")
            )
            link_el = card.select_one("a[href*='/job-listing/']") or card.select_one("a.jobLink")
            company = company_el.get_text(strip=True) if company_el else ""
            job_url = ""
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("/"):
                    job_url = urllib.parse.urljoin(origin + "/", href.lstrip("/"))
                else:
                    job_url = href
            if company:
                out.append(
                    {
                        "company": company,
                        "title": job_title,
                        "url": job_url,
                        "platform": "Glassdoor",
                        "domain": "",
                        "search_country": location,
                    }
                )
        except Exception:
            continue
    return out


def parse_himalayas_jobs_html(html: str, job_title: str, max_results: int) -> List[Dict[str, Any]]:
    """Best-effort parse after JS render."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select('a[href*="/jobs/"]'):
        href = a.get("href") or ""
        if not href or "/jobs/new" in href:
            continue
        text = a.get_text(" ", strip=True)
        if len(text) < 6:
            continue
        full = href if href.startswith("http") else f"https://himalayas.app{href}"
        company = "Unknown"
        title = text
        if " at " in text.lower():
            i = text.lower().rfind(" at ")
            title, company = text[:i].strip(), text[i + 4 :].strip()
        out.append(
            {
                "company": company or "Unknown",
                "title": title or job_title,
                "url": full.split("?")[0],
                "platform": "Himalayas",
                "domain": "",
                "search_country": "Global",
            }
        )
        if len(out) >= max_results:
            break
    return out


def parse_wellfound_jobs_html(html: str, job_title: str, max_results: int) -> List[Dict[str, Any]]:
    """Best-effort parse for Wellfound job list after JS render."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select('a[href*="/jobs/"], a[href*="/role/"], a[href*="/company/"]'):
        href = (a.get("href") or "").strip()
        if not href or "login" in href.lower():
            continue
        if "/jobs/" not in href and "/role/" not in href:
            continue
        text = a.get_text(" ", strip=True)
        if len(text) < 4:
            continue
        full = href if href.startswith("http") else f"https://wellfound.com{href}"
        company = "Unknown"
        title = text
        if " at " in text.lower():
            i = text.lower().rfind(" at ")
            title, company = text[:i].strip(), text[i + 4 :].strip()
        elif " · " in text:
            parts = text.split(" · ", 1)
            title, company = parts[0].strip(), parts[-1].strip()
        out.append(
            {
                "company": company or "Unknown",
                "title": title or job_title,
                "url": full.split("?")[0],
                "platform": "Wellfound",
                "domain": "",
                "search_country": "Global",
            }
        )
        if len(out) >= max_results:
            break
    return out
