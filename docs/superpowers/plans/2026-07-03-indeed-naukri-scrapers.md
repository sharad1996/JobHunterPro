# Enable & Harden Indeed + Naukri Scrapers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing (but disabled/broken) Indeed and Naukri scrapers return results in a normal run, using a Playwright-primary strategy, without changing the job dict schema or downstream logic.

**Architecture:** No new module. Both scrapers already slot into `search_all_platforms()` (`indeed` → `_PER_COUNTRY_SCRAPERS`; `naukri` → the India-gated block). Work is: one shared `browser_fetch.fetch_url` improvement, hardening/rewriting the two scrapers, extending the existing `--auth-*` pattern to Naukri, config wiring, and unit tests for the pure parse functions. Follows the `scrape_bayt` pattern: HTTP try → Playwright fallback → pure parse function in `browser_fetch.py`.

**Tech Stack:** Python 3, `requests`, `beautifulsoup4`, `playwright` (already in `requirements.txt`), `unittest` for tests.

## Global Constraints

- Job dict contract is unchanged: `{ "company", "title", "url", "platform", "domain", "search_country", "posted_at"? }`. `posted_at` is optional — include only when found.
- Every scraper returns a `list` and NEVER raises out to the caller (wrap in try/except, print a diagnostic, return partial/empty list). Match existing `  → / ✓ / ✗ / ⚠` print prefixes.
- Tests use the stdlib `unittest` framework with inline HTML/JSON strings (match `tests/test_regional_boards.py`). Run with `python3 -m unittest`.
- Playwright code MUST keep the existing import guard: `from playwright.sync_api import sync_playwright` wrapped so a missing install raises the existing `RuntimeError` message, not `ImportError`.
- Keep Glassdoor OFF. Enable Indeed by adding `"indeed"` to `PLATFORMS`, NOT by flipping `INCLUDE_INDEED_GLASSDOOR`.
- Naukri internal API values: header `appid: "109"`, header `systemid: "Naukri"`; endpoint `https://www.naukri.com/jobapi/v3/search`.

---

### Task 1: Add `wait_for_selector` to `browser_fetch.fetch_url`

Shared infra so Indeed/Naukri can wait for job cards to render instead of a fixed 2.5s.

**Files:**
- Modify: `browser_fetch.py:40-96` (the `fetch_url` function)
- Test: `tests/test_browser_fetch.py` (create)

**Interfaces:**
- Produces: `browser_fetch.fetch_url(url, params=None, timeout_ms=60000, storage_state_path=None, headless=True, wait_for_selector=None) -> str`. When `wait_for_selector` is set, blocks until that CSS selector appears (15s cap) then falls back to the fixed wait; behavior identical to before when `None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_browser_fetch.py`:

```python
"""Unit tests for browser_fetch (signature + pure parsers, no real browser)."""

import inspect
import unittest

import browser_fetch as bf


class TestFetchUrlSignature(unittest.TestCase):
    def test_fetch_url_accepts_wait_for_selector(self):
        params = inspect.signature(bf.fetch_url).parameters
        self.assertIn("wait_for_selector", params)
        self.assertIsNone(params["wait_for_selector"].default)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_browser_fetch -v`
Expected: FAIL — `AssertionError: 'wait_for_selector' not found in ...` (param does not exist yet).

- [ ] **Step 3: Add the parameter and wait logic**

In `browser_fetch.py`, change the `fetch_url` signature (currently ends at `headless: bool = True,`) to add the new param:

```python
def fetch_url(
    url: str,
    params: Optional[dict] = None,
    timeout_ms: int = 60000,
    storage_state_path: Optional[str] = None,
    headless: bool = True,
    wait_for_selector: Optional[str] = None,
) -> str:
```

Then replace the existing post-navigation wait. Current code (`browser_fetch.py:89-91`):

```python
            page.goto(full, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2500)
            html = page.content()
```

becomes:

```python
            page.goto(full, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=15000)
                except Exception:
                    page.wait_for_timeout(2500)
            else:
                page.wait_for_timeout(2500)
            html = page.content()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_browser_fetch -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add browser_fetch.py tests/test_browser_fetch.py
git commit -m "feat(browser_fetch): add wait_for_selector to fetch_url"
```

---

### Task 2: Harden `parse_indeed_like_html` and enable Indeed

Extract the real job title (currently hardcoded to the query term) + `posted_at`, add fallback selectors, wire `wait_for_selector` into `scrape_indeed`, and add `"indeed"` to `PLATFORMS`.

**Files:**
- Modify: `browser_fetch.py:159-197` (`parse_indeed_like_html`)
- Modify: `scrapers.py:204-217` (Playwright branch of `scrape_indeed`)
- Modify: `config.py:172-185` (`PLATFORMS` list)
- Test: `tests/test_indeed_naukri.py` (create)

**Interfaces:**
- Consumes: `browser_fetch.fetch_url(..., wait_for_selector=...)` from Task 1.
- Produces: `parse_indeed_like_html(html, origin, job_title, location, max_results) -> list[dict]` — same signature, now returns the parsed title (not `job_title`) when a title element is present, and includes `"posted_at"` when a date element is present.

- [ ] **Step 1: Write the failing test**

Create `tests/test_indeed_naukri.py`:

```python
"""Unit tests for Indeed + Naukri parse functions (pure, no network)."""

import unittest

import browser_fetch as bf


INDEED_HTML = """
<html><body>
  <div id="mosaic-provider-jobcards">
    <div class="job_seen_beacon">
      <h2 class="jobTitle"><a data-jk="abc123"><span title="Senior React Engineer">Senior React Engineer</span></a></h2>
      <span data-testid="company-name">Acme Labs</span>
      <span data-testid="myJobsStateDate">Posted 2 days ago</span>
    </div>
  </div>
</body></html>
"""


class TestParseIndeed(unittest.TestCase):
    def test_extracts_company_title_url_and_posted(self):
        jobs = bf.parse_indeed_like_html(
            INDEED_HTML, "https://in.indeed.com", "React Developer", "India", 10
        )
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["company"], "Acme Labs")
        # Real title, NOT the query term "React Developer"
        self.assertEqual(job["title"], "Senior React Engineer")
        self.assertEqual(job["platform"], "Indeed")
        self.assertEqual(job["search_country"], "India")
        self.assertEqual(job["posted_at"], "Posted 2 days ago")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_indeed_naukri -v`
Expected: FAIL — `AssertionError: 'React Developer' != 'Senior React Engineer'` (title currently hardcoded to the query term).

- [ ] **Step 3: Harden the parser**

In `browser_fetch.py`, replace the body of the `for card in cards[:max_results]:` loop in `parse_indeed_like_html` (currently `browser_fetch.py:168-196`) with:

```python
        try:
            company_el = (
                card.select_one("span[data-testid='company-name']")
                or card.select_one(".companyName")
                or card.select_one("[data-company-name]")
            )
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

            title_el = (
                card.select_one("h2.jobTitle span[title]")
                or card.select_one("h2.jobTitle a span")
                or card.select_one("h2.jobTitle a")
                or card.select_one("h2.jobTitle")
            )
            title = title_el.get_text(strip=True) if title_el else job_title

            date_el = (
                card.select_one("span[data-testid='myJobsStateDate']")
                or card.select_one(".date")
            )
            posted_at = date_el.get_text(strip=True) if date_el else None

            if company:
                job = {
                    "company": company,
                    "title": title,
                    "url": job_url,
                    "platform": "Indeed",
                    "domain": "",
                    "search_country": location,
                }
                if posted_at:
                    job["posted_at"] = posted_at
                out.append(job)
        except Exception:
            continue
```

Also broaden the card selector list at the top of the function (currently `browser_fetch.py:162-166`) to add the container fallback:

```python
    cards = (
        soup.select("div.job_seen_beacon")
        or soup.select("div[class*='jobCard']")
        or soup.select("#mosaic-provider-jobcards div.result")
        or soup.select("td.resultContent")
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_indeed_naukri -v`
Expected: PASS.

- [ ] **Step 5: Wire `wait_for_selector` into `scrape_indeed`**

In `scrapers.py`, inside the `if getattr(config, "USE_BROWSER_FETCH", False):` branch of `scrape_indeed`, change the fetch call (currently `scrapers.py:217`):

```python
                html = browser_fetch.fetch_url(full_url, storage_state_path=storage)
```

to:

```python
                html = browser_fetch.fetch_url(
                    full_url,
                    storage_state_path=storage,
                    wait_for_selector="div.job_seen_beacon, #mosaic-provider-jobcards",
                )
```

- [ ] **Step 6: Enable Indeed in config**

In `config.py`, add `"indeed"` to the `PLATFORMS` list (after `"japan-dev",` at `config.py:184`):

```python
    "himalayas",
    "japan-dev",
    "indeed",          # needs USE_BROWSER_FETCH=True; often Cloudflare-blocked without --auth-indeed
]
```

- [ ] **Step 7: Verify import + registration**

Run:
```bash
python3 -c "import scrapers; print('indeed' in scrapers._effective_platform_ids()); print(scrapers._PER_COUNTRY_SCRAPERS.get('indeed') is not None)"
```
Expected: two lines, both `True`.

- [ ] **Step 8: Commit**

```bash
git add browser_fetch.py scrapers.py config.py tests/test_indeed_naukri.py
git commit -m "feat(indeed): harden parser (real title + posted_at), enable in PLATFORMS"
```

---

### Task 3: Add pure Naukri parsers (JSON API + DOM fallback)

Two pure functions in `browser_fetch.py` so they are unit-testable without a browser.

**Files:**
- Modify: `browser_fetch.py` (add two functions after `parse_glassdoor_like_html`, ~line 239)
- Test: `tests/test_indeed_naukri.py` (extend)

**Interfaces:**
- Produces: `parse_naukri_api_json(data: dict, job_title: str, max_results: int) -> list[dict]` — maps `data["jobDetails"]` to job dicts (`platform="Naukri"`, `search_country="India"`). Handles both `jdURL` and `jobUrl` keys.
- Produces: `parse_naukri_like_html(html: str, job_title: str, max_results: int) -> list[dict]` — best-effort DOM parse of rendered Naukri search cards.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_indeed_naukri.py` (before the `if __name__` block):

```python
NAUKRI_API = {
    "jobDetails": [
        {
            "companyName": "Beta Systems",
            "title": "Backend Engineer (Node.js)",
            "jdURL": "/job-listings-backend-engineer-beta-systems-remote-123",
        },
        {
            "companyName": "",  # skipped: no company
            "title": "Ghost Role",
            "jdURL": "/job-listings-ghost-456",
        },
    ]
}

NAUKRI_HTML = """
<html><body>
  <div class="srp-jobtuple-wrapper">
    <a class="title" href="https://www.naukri.com/job-listings-frontend-gamma-789">Frontend Developer</a>
    <a class="comp-name">Gamma Tech</a>
  </div>
</body></html>
"""


class TestParseNaukriApi(unittest.TestCase):
    def test_maps_jobdetails_and_skips_empty_company(self):
        jobs = bf.parse_naukri_api_json(NAUKRI_API, "Node Developer", 10)
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["company"], "Beta Systems")
        self.assertEqual(job["title"], "Backend Engineer (Node.js)")
        self.assertEqual(job["url"], "https://www.naukri.com/job-listings-backend-engineer-beta-systems-remote-123")
        self.assertEqual(job["platform"], "Naukri")
        self.assertEqual(job["search_country"], "India")


class TestParseNaukriHtml(unittest.TestCase):
    def test_parses_rendered_cards(self):
        jobs = bf.parse_naukri_like_html(NAUKRI_HTML, "Frontend Developer", 10)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Gamma Tech")
        self.assertEqual(jobs[0]["title"], "Frontend Developer")
        self.assertEqual(jobs[0]["platform"], "Naukri")
        self.assertTrue(jobs[0]["url"].startswith("https://www.naukri.com/"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_indeed_naukri -v`
Expected: FAIL — `AttributeError: module 'browser_fetch' has no attribute 'parse_naukri_api_json'`.

- [ ] **Step 3: Implement both parsers**

In `browser_fetch.py`, add after `parse_glassdoor_like_html` (after `browser_fetch.py:239`):

```python
def parse_naukri_api_json(data: Dict[str, Any], job_title: str, max_results: int) -> List[Dict[str, Any]]:
    """Map Naukri internal search API (jobapi/v3/search) JSON to job dicts."""
    out = []
    jobs = (data or {}).get("jobDetails") or []
    for job in jobs[:max_results]:
        company = (job.get("companyName") or "").strip()
        if not company:
            continue
        rel = job.get("jdURL") or job.get("jobUrl") or ""
        if rel.startswith("http"):
            url = rel
        elif rel:
            url = f"https://www.naukri.com{rel}"
        else:
            url = ""
        out.append(
            {
                "company": company,
                "title": (job.get("title") or job_title).strip(),
                "url": url,
                "platform": "Naukri",
                "domain": "",
                "search_country": "India",
            }
        )
    return out


def parse_naukri_like_html(html: str, job_title: str, max_results: int) -> List[Dict[str, Any]]:
    """Best-effort parse of rendered Naukri search result cards."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    cards = (
        soup.select("div.srp-jobtuple-wrapper")
        or soup.select("article.jobTuple")
        or soup.select("div.cust-job-tuple")
    )
    for card in cards[:max_results]:
        try:
            company_el = (
                card.select_one("a.comp-name")
                or card.select_one("a.subTitle")
                or card.select_one(".comp-name")
                or card.select_one(".companyInfo a")
            )
            company = company_el.get_text(strip=True) if company_el else ""
            if not company:
                continue
            title_el = card.select_one("a.title")
            href = title_el.get("href", "") if title_el else ""
            if href.startswith("http"):
                url = href
            elif href:
                url = f"https://www.naukri.com{href}"
            else:
                url = ""
            out.append(
                {
                    "company": company,
                    "title": title_el.get_text(strip=True) if title_el else job_title,
                    "url": url,
                    "platform": "Naukri",
                    "domain": "",
                    "search_country": "India",
                }
            )
        except Exception:
            continue
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_indeed_naukri -v`
Expected: PASS (all Indeed + Naukri parse tests).

- [ ] **Step 5: Commit**

```bash
git add browser_fetch.py tests/test_indeed_naukri.py
git commit -m "feat(naukri): add pure JSON-API and DOM parsers with tests"
```

---

### Task 4: Naukri browser fetch + rewrite `scrape_naukri`, enable in config

Add the browser-context API fetch and rewrite the orchestration to: API path → DOM render fallback → plain-HTTP last resort. Add `"naukri"` to `PLATFORMS`.

**Files:**
- Modify: `browser_fetch.py` (add `fetch_naukri_search` after the parsers from Task 3)
- Modify: `scrapers.py:239-316` (rewrite `scrape_naukri`)
- Modify: `config.py:172-185` (`PLATFORMS` list)

**Interfaces:**
- Consumes: `parse_naukri_api_json`, `parse_naukri_like_html` (Task 3); `fetch_url(..., wait_for_selector=...)` (Task 1).
- Produces: `browser_fetch.fetch_naukri_search(keyword, slug, max_results, job_age, storage_state_path=None, timeout_ms=60000) -> dict | None` — loads Naukri in a browser context (for cookies), then calls the internal JSON API with `appid`/`systemid` headers; returns parsed JSON or `None`.

- [ ] **Step 1: Add `fetch_naukri_search` to `browser_fetch.py`**

Add after `parse_naukri_like_html`:

```python
def fetch_naukri_search(
    keyword: str,
    slug: str,
    max_results: int,
    job_age: int,
    storage_state_path: Optional[str] = None,
    timeout_ms: int = 60000,
) -> Optional[dict]:
    """
    Call Naukri's internal search API from a real browser context.

    Loads a Naukri search page first (to acquire cookies), then issues the
    JSON API request from that same-origin context with the required headers.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is not installed. Run: pip install playwright && python3 -m playwright install chromium"
        ) from e

    api = "https://www.naukri.com/jobapi/v3/search"
    params = {
        "noOfResults": max_results,
        "urlType": "search_by_keyword",
        "searchType": "adv",
        "keyword": keyword,
        "pageNo": 1,
        "seoKey": slug,
        "src": "jobsearchDesk",
        "jobAge": job_age,
    }
    headers = {"appid": "109", "systemid": "Naukri"}

    with sync_playwright() as p:
        browser = None
        try:
            try:
                browser = p.chromium.launch(
                    headless=True,
                    channel="chrome",
                    args=list(_CHROMIUM_ARGS),
                    ignore_default_args=["--enable-automation"],
                )
            except Exception:
                browser = p.chromium.launch(
                    headless=True,
                    args=list(_CHROMIUM_ARGS),
                    ignore_default_args=["--enable-automation"],
                )
            ctx_args: dict = {
                "viewport": {"width": 1365, "height": 900},
                "locale": "en-US",
            }
            if storage_state_path and os.path.isfile(storage_state_path):
                ctx_args["storage_state"] = storage_state_path
            context = browser.new_context(**ctx_args)
            context.add_init_script(_STEALTH_INIT)
            page = context.new_page()
            page.goto(
                f"https://www.naukri.com/{slug}-jobs",
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )
            page.wait_for_timeout(1500)
            resp = context.request.get(api, params=params, headers=headers)
            data = resp.json() if resp.ok else None
            context.close()
            return data
        finally:
            if browser:
                browser.close()
```

- [ ] **Step 2: Rewrite `scrape_naukri`**

In `scrapers.py`, replace the entire `scrape_naukri` function (`scrapers.py:239-316`) with:

```python
def scrape_naukri(job_title: str, max_results: int = 15, remote_only: bool = False) -> list:
    """Scrape Naukri (India). Playwright-primary: internal JSON API → DOM render → plain HTTP."""
    results = []
    kw = f"{job_title} remote" if remote_only else job_title
    slug = _slug(kw)
    age = max_job_posting_age_days()
    print("  → Searching Naukri (India, remote)..." if remote_only else "  → Searching Naukri...")
    try:
        import browser_fetch

        storage = None
        if getattr(config, "USE_BROWSER_FETCH", False):
            if getattr(config, "NAUKRI_USE_AUTH_STATE", False):
                p = config.auth_storage_path("naukri")
                if os.path.isfile(p):
                    storage = p
                else:
                    print(
                        "  ⚠ Naukri: NAUKRI_USE_AUTH_STATE=True but no session file — "
                        "run: python3 main.py --auth-naukri"
                    )

            # 1) Internal JSON API via browser context
            try:
                data = browser_fetch.fetch_naukri_search(
                    kw, slug, max_results, age, storage_state_path=storage
                )
                results = browser_fetch.parse_naukri_api_json(data, job_title, max_results)
            except Exception as e:
                print(f"  ⚠ Naukri (Playwright API): {e}")

            # 2) Rendered DOM fallback
            if not results:
                try:
                    url = f"https://www.naukri.com/{slug}-jobs?jobAge={age}"
                    html = browser_fetch.fetch_url(
                        url,
                        storage_state_path=storage,
                        wait_for_selector="div.srp-jobtuple-wrapper, article.jobTuple",
                    )
                    results = browser_fetch.parse_naukri_like_html(html, job_title, max_results)
                except Exception as e:
                    print(f"  ⚠ Naukri (Playwright DOM): {e}")

        # 3) Plain-HTTP last resort (static HTML is JS-rendered — usually empty)
        if not results:
            url = f"https://www.naukri.com/{slug}-jobs?jobAge={age}"
            resp = _get(url)
            if not resp:
                print("  ✗ Naukri: Could not connect to listing page")
                print(
                    "     Naukri loads jobs in the browser. Set USE_BROWSER_FETCH=True "
                    "(and optionally run: python3 main.py --auth-naukri)."
                )
                return results
            results = browser_fetch.parse_naukri_like_html(resp.text, job_title, max_results)
            if not results:
                print(
                    "  ⚠ Naukri: Empty static HTML (JavaScript-rendered). "
                    "Set USE_BROWSER_FETCH=True for real results."
                )

        print(f"  ✓ Naukri: {len(results)} results")
    except Exception as e:
        print(f"  ✗ Naukri error: {e}")
    _pause()
    return results
```

Note: `os` and `config` are already imported at the top of `scrapers.py`; `BeautifulSoup` is no longer used inside `scrape_naukri` (parsing moved to `browser_fetch`), but leave the module import untouched — other scrapers use it.

- [ ] **Step 3: Enable Naukri in config**

In `config.py`, add `"naukri"` to `PLATFORMS` (right after the `"indeed",` line added in Task 2):

```python
    "japan-dev",
    "indeed",          # needs USE_BROWSER_FETCH=True; often Cloudflare-blocked without --auth-indeed
    "naukri",          # India-only; needs USE_BROWSER_FETCH=True (internal JSON API)
]
```

- [ ] **Step 4: Verify registration + no syntax errors**

Run:
```bash
python3 -c "import scrapers, browser_fetch; print('naukri' in scrapers._effective_platform_ids()); print(hasattr(browser_fetch, 'fetch_naukri_search'))"
```
Expected: two lines, both `True`.

- [ ] **Step 5: Run the full parse test suite (regression)**

Run: `python3 -m unittest tests.test_indeed_naukri tests.test_browser_fetch -v`
Expected: PASS (nothing broken by the rewrite).

- [ ] **Step 6: Commit**

```bash
git add browser_fetch.py scrapers.py config.py
git commit -m "feat(naukri): browser-context JSON-API fetch, rewrite scraper, enable in PLATFORMS"
```

---

### Task 5: Naukri saved-login support (`--auth-naukri`)

Extend the existing Indeed auth pattern to Naukri.

**Files:**
- Modify: `config.py:203` area (add `NAUKRI_USE_AUTH_STATE`) and `config.py:247-256` (`auth_storage_path` allowed set)
- Modify: `main.py` (new `cmd_auth_naukri`, arg, dispatch, usage line)

**Interfaces:**
- Consumes: `config.auth_storage_path("naukri")` and `config.NAUKRI_USE_AUTH_STATE` (read by `scrape_naukri` from Task 4 — already referenced there).
- Produces: CLI command `python3 main.py --auth-naukri`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_browser_fetch.py` (before the `if __name__` block):

```python
import config


class TestNaukriAuthConfig(unittest.TestCase):
    def test_auth_storage_path_allows_naukri(self):
        path = config.auth_storage_path("naukri")
        self.assertTrue(path.endswith("naukri_storage.json"))

    def test_naukri_use_auth_state_flag_exists(self):
        self.assertIsInstance(config.NAUKRI_USE_AUTH_STATE, bool)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_browser_fetch -v`
Expected: FAIL — `ValueError: platform must be indeed, wellfound, or upwork` (and/or `AttributeError` for `NAUKRI_USE_AUTH_STATE`).

- [ ] **Step 3: Update `config.py`**

Add the flag after `INDEED_USE_AUTH_STATE = False` (`config.py:203`):

```python
INDEED_USE_AUTH_STATE = False
NAUKRI_USE_AUTH_STATE = False
```

Update `auth_storage_path` (`config.py:249-251`) to allow `"naukri"`:

```python
    name = (platform or "").strip().lower()
    if name not in ("indeed", "wellfound", "upwork", "naukri"):
        raise ValueError("platform must be indeed, wellfound, upwork, or naukri")
```

Update the docstring on the line above (`config.py:248`):

```python
    """Path to Playwright storage JSON for indeed | wellfound | upwork | naukri."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_browser_fetch -v`
Expected: PASS.

- [ ] **Step 5: Add the CLI command in `main.py`**

Add a new command function after `cmd_auth_upwork` (`main.py:668`):

```python
def cmd_auth_naukri():
    cmd_auth_save("naukri", "https://www.naukri.com/nlogin/login")
```

Add the argument after the `--auth-upwork` arg (`main.py:941`):

```python
    parser.add_argument("--auth-naukri", action="store_true", help="Save Naukri login session for Playwright (headed browser)")
```

Add to the dispatch chain after the `--auth-upwork` branch (`main.py:1022-1023`):

```python
    elif args.auth_upwork:
        cmd_auth_upwork()
    elif args.auth_naukri:
        cmd_auth_naukri()
```

Add to the usage examples in the epilog after the `--auth-upwork` line (`main.py:928`):

```python
  python3 main.py --auth-upwork
  python3 main.py --auth-naukri
```

- [ ] **Step 6: Verify the CLI wires up**

Run:
```bash
python3 main.py --help | grep -- --auth-naukri
```
Expected: a line showing `--auth-naukri  Save Naukri login session for Playwright (headed browser)`.

- [ ] **Step 7: Commit**

```bash
git add config.py main.py tests/test_browser_fetch.py
git commit -m "feat(naukri): add --auth-naukri saved-login session support"
```

---

### Task 6: Documentation

Update in-code comments and `INTEGRATIONS.md` so the new behavior is discoverable.

**Files:**
- Modify: `config.py:208-210` (the "full list" comment block)
- Modify: `INTEGRATIONS.md`

- [ ] **Step 1: Update the config comment**

In `config.py`, the comment currently at `config.py:196` describing `USE_BROWSER_FETCH` mentions "Indeed, Glassdoor, Wellfound, Himalayas". Append Naukri:

```python
# Use Playwright Chromium for bot-prone or JS-heavy pages (Indeed, Glassdoor, Wellfound, Himalayas, Naukri).
```

- [ ] **Step 2: Update INTEGRATIONS.md**

Add a section to `INTEGRATIONS.md` documenting:
- Indeed: enabled in `PLATFORMS`; requires `USE_BROWSER_FETCH = True`; optional `INDEED_USE_AUTH_STATE = True` + `python3 main.py --auth-indeed`; expect Cloudflare blocks without a saved session.
- Naukri: enabled in `PLATFORMS` (India only); requires `USE_BROWSER_FETCH = True`; uses the internal JSON API; optional `NAUKRI_USE_AUTH_STATE = True` + `python3 main.py --auth-naukri`.

Exact text to append at the end of `INTEGRATIONS.md`:

```markdown
## Indeed & Naukri (Playwright-primary)

Both are enabled in `PLATFORMS` but need a real browser to return results:

1. `pip install playwright && python3 -m playwright install chromium`
2. Set `USE_BROWSER_FETCH = True` in `config.py`.

**Indeed** aggressively blocks headless browsers (Cloudflare). For better odds:
- `python3 main.py --auth-indeed` (log in once in the opened browser), then
- set `INDEED_USE_AUTH_STATE = True` in `config.py`.

**Naukri** (India only — runs when `TARGET_COUNTRIES` includes India) uses the
site's internal JSON search API via the browser context. Optional saved login:
- `python3 main.py --auth-naukri`, then set `NAUKRI_USE_AUTH_STATE = True`.
```

- [ ] **Step 3: Commit**

```bash
git add config.py INTEGRATIONS.md
git commit -m "docs: document Indeed + Naukri Playwright setup and --auth-naukri"
```

---

## Final Verification

- [ ] **Run the full test suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests pass (regional, marketplace, browser_fetch, indeed_naukri).

- [ ] **Smoke-test a real run (manual, optional — requires Playwright installed)**

Temporarily set `USE_BROWSER_FETCH = True`, then:
```bash
python3 main.py --job "React Developer" --dry-run
```
Expected: log lines `→ Searching Indeed (India, remote)...` and `→ Searching Naukri (India, remote)...` appear, each ending in a `✓ … results` or a clear `✗`/`⚠` diagnostic (never a silent hang or an uncaught traceback).
