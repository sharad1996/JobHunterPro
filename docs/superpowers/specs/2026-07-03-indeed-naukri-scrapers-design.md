# Enable & Harden Indeed + Naukri Scrapers

**Date:** 2026-07-03
**Status:** Approved (design)

## Background

The original request was to add Indeed, Workday, and Naukri as job sources.
Investigation of the codebase reframed the task:

- **Indeed** — `scrape_indeed()` already exists (`scrapers.py:178`) with a Playwright
  path and `parse_indeed_like_html()` (`browser_fetch.py:159`). It is gated OFF behind
  `INCLUDE_INDEED_GLASSDOOR = False`. Indeed aggressively blocks scripted access
  (HTTP 403 + Cloudflare); its Publisher API is closed to new signups.
- **Naukri** — `scrape_naukri()` already exists (`scrapers.py:239`) but is not listed
  in `PLATFORMS`, so it never runs. It is JS-rendered; its internal `jobapi/v3/search`
  endpoint needs specific client headers (`appid`, `systemid`).
- **Workday** — does not exist and is architecturally different (an ATS hosting
  thousands of per-company career sites at `<tenant>.myworkdayjobs.com`, with no global
  search). **Dropped from scope** for now per decision below.

## Decisions

1. **Scope:** Indeed + Naukri only. Workday dropped for now.
2. **Anti-bot strategy:** Playwright-primary. Assume `USE_BROWSER_FETCH = True` and
   optional saved login sessions (`--auth-*`).
3. **Naukri data source:** hit Naukri's internal JSON API (`jobapi/v3/search`) with the
   required `appid`/`systemid` headers via the browser context; DOM parse as fallback.
4. **Glassdoor stays OFF.** Enable Indeed by adding `"indeed"` directly to `PLATFORMS`,
   NOT via `INCLUDE_INDEED_GLASSDOOR` (that flag enables Glassdoor too).
5. **Deliverable:** written plan, then implement in-session after approval.

## Goals

- Indeed and Naukri return results in a normal `python3 main.py` run when
  `USE_BROWSER_FETCH = True`.
- Failures produce clear "blocked"/diagnostic messages, never silent zeros.
- No new top-level module; reuse the existing scraper dispatch and `browser_fetch` infra.
- Parse logic is unit-tested against saved fixtures.

## Non-Goals

- Workday integration (deferred).
- Guaranteeing Indeed results despite Cloudflare — best-effort with auth-session support.
- Changing the job dict schema, dedupe, filtering, or downstream email/DB/sheet logic.

## Architecture

No new module. Both scrapers already slot into `search_all_platforms()`:
`indeed` → `_PER_COUNTRY_SCRAPERS` (runs per `TARGET_COUNTRY`); `naukri` → the
India-gated block (`scrapers.py:566`). The work is: config changes, hardening two
existing scrapers, one shared `browser_fetch` improvement, extending the auth pattern
to Naukri, and tests. Follows the existing `scrape_bayt` pattern:
HTTP try → Playwright fallback → pure parse function in `browser_fetch.py`.

The job dict contract is unchanged:
`{ company, title, url, platform, domain, search_country, posted_at? }`.

## Components & Changes

### 1. Shared: `browser_fetch.fetch_url()` waits for content
- Add optional `wait_for_selector: Optional[str] = None` param.
- When set, after `page.goto(...)` call `page.wait_for_selector(sel, timeout=...)`
  inside a try/except; on timeout fall back to the current fixed `wait_for_timeout(2500)`
  so pages that never show the selector still return HTML.
- Backward-compatible: all existing callers pass nothing and keep current behavior.

### 2. Indeed — enable + harden
- **Config:** add `"indeed"` to `PLATFORMS`. Document `USE_BROWSER_FETCH = True` and
  optional `INDEED_USE_AUTH_STATE = True` (+ `python3 main.py --auth-indeed`). All auth
  plumbing already exists.
- **`scrape_indeed` Playwright branch:** pass a `wait_for_selector` for the job-card
  container so results render before HTML is captured.
- **`parse_indeed_like_html`:** add fallback selectors for cards, company, and title;
  extract the **real job title** (currently hardcoded to the query term); extract
  `posted_at` when available. Keep returning `[]` cleanly on no match.

### 3. Naukri — wire in + browser/API path + auth
- **Config:** add `"naukri"` to `PLATFORMS` (India-gating already handles it).
- **`scrape_naukri` browser path:** when `USE_BROWSER_FETCH` is on, open a Naukri page
  in the browser context, then call the internal JSON API
  (`https://www.naukri.com/jobapi/v3/search`) from that same-origin context with headers
  `appid: 109`, `systemid: Naukri` (plus cookies from the loaded page). Parse the JSON
  `jobDetails` into job dicts.
- **Fallback:** new pure `parse_naukri_like_html()` in `browser_fetch.py` for rendered
  DOM cards, used if the API path yields nothing. Retain the existing plain-HTTP attempt
  as a last resort with the current diagnostic message.
- **Auth (mirror Indeed):**
  - `config.auth_storage_path()` — add `"naukri"` to the allowed set.
  - Add `NAUKRI_USE_AUTH_STATE = False` flag in `config.py`.
  - Add `cmd_auth_naukri()` and `--auth-naukri` CLI arg in `main.py`
    (start URL `https://www.naukri.com/nlogin/login`).
  - When `NAUKRI_USE_AUTH_STATE` is set and the session file exists, pass
    `storage_state_path` to the browser fetch.

### 4. Documentation
- Update the config comment block (`config.py:208-210`) and the `PLATFORMS` list comment.
- Note the new `--auth-naukri` flow in `INTEGRATIONS.md` / `main.py` usage text.

### 5. Testing
- Add `tests/test_indeed_naukri.py` (or extend existing tests):
  - `parse_indeed_like_html` against a saved Indeed results HTML fixture → asserts
    company/title/url extraction and fallback-selector paths.
  - `parse_naukri_like_html` against a saved Naukri HTML fixture, and a Naukri JSON
    fixture → asserts `jobDetails` mapping to the job dict contract.
- Fixtures are small trimmed samples stored under `tests/fixtures/`.

## Data Flow

`main.py` → `search_all_platforms(job_title)` →
- per country: `scrape_indeed(title, country, max, remote)` →
  `browser_fetch.fetch_url(url, wait_for_selector=...)` → `parse_indeed_like_html(...)`.
- India-gated: `scrape_naukri(title, max, remote)` → browser context → internal JSON API
  (`parse` JSON) → fallback `parse_naukri_like_html(...)`.
- Results merged + de-duplicated by existing logic; schema unchanged.

## Error Handling

- HTTP 403 / Cloudflare / empty renders → existing `_print_fetch_failure` style
  diagnostics ("Blocked… enable USE_BROWSER_FETCH / run --auth-indeed").
- Playwright not installed → the existing `RuntimeError` message from `browser_fetch`.
- Naukri API non-200 or unexpected JSON → fall through to DOM parse, then to the
  current plain-HTTP diagnostic; never raise out of the scraper.

## Risks

- **Indeed Cloudflare:** headless Chromium may still be challenged; a saved login session
  improves but does not guarantee results. Documented as an expectation, not a bug.
- **Selector drift:** Indeed/Naukri markup changes often. Mitigated by layered fallback
  selectors and by preferring Naukri's JSON API over DOM.
- **Naukri app-header changes:** `appid`/`systemid` values can change; if the API path
  fails the DOM fallback still runs.
