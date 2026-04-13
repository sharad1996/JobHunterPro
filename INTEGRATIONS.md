# Job Hunter Pro — integrations

## Default job sources

`config.py` **`PLATFORMS`** lists boards that work without extra setup. Stubbed or bot-heavy sources are **not** in the default list; turn them on with the **`INCLUDE_*`** flags (same file).

| Flag | Effect |
|------|--------|
| `INCLUDE_STUB_PLATFORMS` | Adds `himalayas`, `flexjobs`, `wellfound`. FlexJobs stays paywalled. Himalayas / Wellfound need Playwright when `USE_BROWSER_FETCH` is True. |
| `INCLUDE_MARKETPLACE_PLATFORMS` | Adds `upwork` (needs `UPWORK_ACCESS_TOKEN`). |
| `INCLUDE_INDEED_GLASSDOOR` | Adds `indeed` and `glassdoor` (often HTTP 403 without a browser). |
| `USE_BROWSER_FETCH` | Use Playwright Chromium for Indeed, Glassdoor, Himalayas, and Wellfound fetches. |

## Playwright (browser fetch)

1. `pip install playwright`
2. `playwright install chromium`
3. Set `USE_BROWSER_FETCH = True` in `config.py`.

## Upwork (GraphQL + OAuth)

1. Create an app at [Upwork Developers](https://www.upwork.com/developer/).
2. Complete OAuth 2.0 in a browser; exchange the code for an access token (Upwork docs: token endpoint `https://www.upwork.com/api/v3/oauth2/token`).
3. Export the bearer token (no quotes):

   ```bash
   export UPWORK_ACCESS_TOKEN="your_oauth_access_token"
   ```

4. Set `INCLUDE_MARKETPLACE_PLATFORMS = True` and add nothing manual if `upwork` is appended by that flag.

GraphQL field names can change; if Upwork returns GraphQL errors, adjust the query in `marketplace_boards.py` to match current schema / permissions on your key.

## Freelancer.com

`scrape_freelancer` uses the **public** `projects/active` read API — no API key for basic use. It is enabled in the default `PLATFORMS` list.

## Excel tracking

See `JOB_TRACKING_XLSX` in `config.py`. Requires `openpyxl` (`pip install openpyxl`).

## Export sheet from SQLite

```bash
python main.py --export-xlsx
```

Overwrites the workbook from the database (manual Excel columns may be reset).
