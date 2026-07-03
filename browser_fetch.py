"""
Optional Playwright-based HTML fetch for bot-prone or JS-heavy job sites.

Requires: pip install playwright && python3 -m playwright install chromium
Enable in config: USE_BROWSER_FETCH = True

Saved login sessions: run `python3 main.py --auth-indeed` (etc.) then set
INDEED_USE_AUTH_STATE / WELLFOUND_USE_AUTH_STATE in config.py.
"""

import os
import urllib.parse
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

# Reduces obvious automation signals; cannot defeat all bot checks (Google SSO often still fails).
_STEALTH_INIT = """
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  } catch (e) {}
  try {
    window.chrome = window.chrome || { runtime: {} };
  } catch (e) {}
})();
"""

_CHROMIUM_ARGS = ("--disable-blink-features=AutomationControlled",)


def _build_url(url: str, params: Optional[dict]) -> str:
    if not params:
        return url
    q = urllib.parse.urlencode(params, doseq=True)
    sep = "&" if ("?" in url) else "?"
    return f"{url}{sep}{q}"


def fetch_url(
    url: str,
    params: Optional[dict] = None,
    timeout_ms: int = 60000,
    storage_state_path: Optional[str] = None,
    headless: bool = True,
    wait_for_selector: Optional[str] = None,
) -> str:
    """
    Return page HTML after Chromium loads the URL.
    If storage_state_path is set and the file exists, reuse cookies from a prior --auth-* run.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is not installed. Run: pip install playwright && python3 -m playwright install chromium"
        ) from e

    full = _build_url(url, params)
    with sync_playwright() as p:
        browser = None
        try:
            try:
                browser = p.chromium.launch(
                    headless=headless,
                    channel="chrome",
                    args=list(_CHROMIUM_ARGS),
                    ignore_default_args=["--enable-automation"],
                )
            except Exception:
                browser = p.chromium.launch(
                    headless=headless,
                    args=list(_CHROMIUM_ARGS),
                    ignore_default_args=["--enable-automation"],
                )
            ctx_args: dict = {
                "viewport": {"width": 1365, "height": 900},
                "locale": "en-US",
            }
            if storage_state_path:
                if not os.path.isfile(storage_state_path):
                    raise FileNotFoundError(
                        f"Missing Playwright storage state: {storage_state_path}\n"
                        f"Run the matching --auth-* command once to create it."
                    )
                ctx_args["storage_state"] = storage_state_path
            context = browser.new_context(**ctx_args)
            context.add_init_script(_STEALTH_INIT)
            page = context.new_page()
            page.goto(full, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=15000)
                except Exception:
                    page.wait_for_timeout(2500)
            else:
                page.wait_for_timeout(2500)
            html = page.content()
            context.close()
            return html
        finally:
            if browser:
                browser.close()


def interactive_save_storage_state(
    start_url: str, output_path: str, profile_key: str = "default"
) -> None:
    """
    Open a headed browser so the user can log in; save Playwright storage_state JSON.

    Uses a persistent profile directory (reused on re-runs) and prefers real Google Chrome
    when installed (better compatibility than bundled Chromium for OAuth / SMS codes).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is not installed. Run: pip install playwright && python3 -m playwright install chromium"
        ) from e

    parent = os.path.dirname(os.path.abspath(output_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    safe_key = "".join(c if c.isalnum() or c in "-_" else "-" for c in profile_key)[:48]
    user_data_dir = os.path.join(parent, f".pw-profile-{safe_key}")
    os.makedirs(user_data_dir, exist_ok=True)

    print(f"\nOpening browser for: {start_url}")
    print("  Using a persistent local profile (helps look less like a one-off bot).")
    print("1. Log in in the window. If SMS or authenticator codes appear, complete them on your phone.")
    print("2. When the site shows you as logged in, return here and press Enter to save cookies.\n")

    with sync_playwright() as p:
        context = None
        launch_kw = dict(
            user_data_dir=user_data_dir,
            headless=False,
            viewport={"width": 1365, "height": 900},
            locale="en-US",
            args=list(_CHROMIUM_ARGS),
            ignore_default_args=["--enable-automation"],
        )
        try:
            context = p.chromium.launch_persistent_context(channel="chrome", **launch_kw)
        except Exception:
            try:
                context = p.chromium.launch_persistent_context(**launch_kw)
            except TypeError:
                launch_kw.pop("ignore_default_args", None)
                context = p.chromium.launch_persistent_context(**launch_kw)

        try:
            context.add_init_script(_STEALTH_INIT)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(start_url, wait_until="domcontentloaded", timeout=180000)
            input("Press Enter here after you are logged in… ")
            context.storage_state(path=output_path)
        finally:
            context.close()

    print(f"Saved session state to: {output_path}")


def parse_indeed_like_html(html: str, origin: str, job_title: str, location: str, max_results: int) -> List[Dict[str, Any]]:
    """Shared DOM parse for Indeed (same selectors as requests path). Logged-in HTML may differ — adjust selectors if needed."""
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
    """
    Best-effort parse for Wellfound job list after JS render.
    Logged-in markup can differ from anonymous pages; extend selectors here if cards move.
    """
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
