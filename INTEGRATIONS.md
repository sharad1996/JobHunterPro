# Job Hunter Pro — integrations

## Default job sources

`config.py` **`PLATFORMS`** lists boards that work without extra setup. Stubbed or bot-heavy sources are **not** in the default list; turn them on with the **`INCLUDE_*`** flags (same file).

| Flag | Effect |
|------|--------|
| `INCLUDE_STUB_PLATFORMS` | Adds `himalayas`, `flexjobs`, `wellfound`. FlexJobs stays paywalled. Himalayas / Wellfound need Playwright when `USE_BROWSER_FETCH` is True. |
| `INCLUDE_MARKETPLACE_PLATFORMS` | Adds `upwork` (OAuth; see Upwork below). |
| `INCLUDE_INDEED_GLASSDOOR` | Adds `indeed` and `glassdoor` (often HTTP 403 without a browser). |
| `USE_BROWSER_FETCH` | Use Playwright Chromium for Indeed, Glassdoor, Wellfound, Himalayas. |

## Playwright (browser fetch)

1. `pip3 install playwright` (or `pip install playwright` inside your venv)
2. `python3 -m playwright install chromium`

   Do **not** run bare `playwright install` — that shell command is often not on your `PATH`. Always use `python3 -m playwright …` (on Windows: `python -m playwright install chromium`).
3. Set `USE_BROWSER_FETCH = True` in `config.py`.

## Logged-in Indeed / Wellfound (saved session)

Some pages return more (or fewer blocks) when you are logged in.

1. Run **once** (or when the site logs you out), in the project directory:

   ```bash
   python3 main.py --auth-indeed
   python3 main.py --auth-wellfound
   ```

   A **visible** browser window opens (prefers **Google Chrome** if installed). Sign in (complete 2FA if prompted). When you see the logged-in site, focus the terminal and press **Enter** to save cookies to:

   - `AUTH_STATE_DIR` / `indeed_storage.json`
   - `AUTH_STATE_DIR` / `wellfound_storage.json`

   Default `AUTH_STATE_DIR` is under the repo: `.jobhunter/auth/` (see `config.py`). Override with env **`JOBHUNTER_AUTH_DIR`** (absolute path recommended).

2. In `config.py` set:

   - `INDEED_USE_AUTH_STATE = True` (uses `indeed_storage.json` when `USE_BROWSER_FETCH` runs Indeed)
   - `WELLFOUND_USE_AUTH_STATE = True` (uses `wellfound_storage.json` for Wellfound)

3. **Security:** do **not** commit `*_storage.json` or `.jobhunter/` (listed in `.gitignore`). Anyone with that file can act as your session on that site.

4. **Selectors:** logged-in HTML can differ. If you get zero jobs, adjust parsers in `browser_fetch.py` (`parse_indeed_like_html`, `parse_wellfound_jobs_html`).

### Bot detection, Google login, and SMS / “login with code”

Sites and **Google Sign-In** often block or limit automated browsers. You may see security warnings or **SMS / email codes that never arrive** in the Playwright window.

**What the tool does:** `--auth-*` prefers **Google Chrome** when installed (`channel="chrome"`), keeps a **reusable profile** under `.jobhunter/auth/.pw-profile-*`, removes some automation flags, and injects light stealth scripts. Headless fetches use similar settings.

**What usually works better:**

- Use **email + password** on the job site instead of **Continue with Google** when available.
- Approve sign-in on your **phone** (Google prompt) or use an **authenticator app** if the site offers it; if codes never show up, Google is blocking the browser — avoid Google on that site.
- Install **Google Chrome** so the auth window is real Chrome, not only Playwright’s Chromium.
- Use boards that do not need that login, or **Upwork’s OAuth API** (no browser job search login).

There is no guaranteed way to pass Google OAuth in automation for every account.

### Upwork browser session (optional / reserved)

```bash
python3 main.py --auth-upwork
```

Saves `upwork_storage.json` for a possible future browser-based job search. **Current** Upwork job discovery uses the **GraphQL API** below, not this file.

## Upwork (GraphQL + OAuth)

### Option A — Access token only

1. Create an app at [Upwork Developers](https://www.upwork.com/developer/).
2. Complete OAuth 2.0 in a browser; obtain an **access token**.
3. Export:

   ```bash
   export UPWORK_ACCESS_TOKEN="your_oauth_access_token"
   ```

### Option B — Refresh token (recommended for automation)

1. Same app registration; obtain **refresh token**, **client id**, and **client secret** from the OAuth flow.
2. Export:

   ```bash
   export UPWORK_CLIENT_ID="..."
   export UPWORK_CLIENT_SECRET="..."
   export UPWORK_REFRESH_TOKEN="..."
   ```

   If `UPWORK_ACCESS_TOKEN` is missing or returns **401**, Job Hunter Pro will call  
   `POST https://www.upwork.com/api/v3/oauth2/token` with `grant_type=refresh_token`, then retry GraphQL **in the same process** (env vars are updated in memory). Re-export `UPWORK_ACCESS_TOKEN` in your shell if you want it persisted for other tools.

3. Set `INCLUDE_MARKETPLACE_PLATFORMS = True` (or add `upwork` to `PLATFORMS`).

GraphQL field names can change; if Upwork returns GraphQL errors, adjust the query in `marketplace_boards.py` to match current schema / permissions on your key.

## Freelancer.com

`scrape_freelancer` uses the **public** `projects/active` read API — no API key for basic use. It is enabled in the default `PLATFORMS` list.

## Excel tracking

See `JOB_TRACKING_XLSX` in `config.py`. Requires `openpyxl` (`pip install openpyxl`).

After a job search, every listing is written to the sheet (URL, company, etc.), and the **HR email** column is filled when Hunter finds one. If you find an address elsewhere, type it into **HR email** for that row, then run:

```bash
python3 main.py --sync-from-xlsx
```

That copies sheet values into **pending** SQLite rows with the same normalized Job URL so you can run `--send-pending` without a new search.

## Export sheet from SQLite

```bash
python3 main.py --export-xlsx
```

Overwrites the workbook from the database (manual Excel columns may be reset).
