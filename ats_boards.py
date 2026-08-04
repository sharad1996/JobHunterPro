"""
ATS job boards: Greenhouse, Lever, Ashby — the sources Google for Jobs indexes.

All three expose a public read API with no key and no bot protection, but they are keyed
by a per-company "board token" and offer no cross-company search. Coverage therefore
equals the token lists in config (GREENHOUSE_BOARDS / LEVER_BOARDS / ASHBY_BOARDS) plus
tokens harvested from URLs already collected (`python3 main.py --harvest-ats`), which are
appended to ATS_TOKENS_FILE so the list compounds every run.

  Greenhouse  https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false
  Lever       https://api.lever.co/v0/postings/{token}?mode=json
  Ashby       https://api.ashbyhq.com/posting-api/job-board/{token}

Unknown tokens return HTTP 404 and are skipped quietly — a stale token costs one request.
"""

import compat  # noqa: F401 — before requests/urllib3

import json
import os
import random
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set

import requests

import config
from job_filters import parse_posted_at, posted_at_within_window

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false"
LEVER_URL = "https://api.lever.co/v0/postings/{token}?mode=json"
ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{token}"

# Provider → regex matching ONLY that vendor's job-board hosts.
#
# Deliberately excludes the vendors' marketing sites (www.ashbyhq.com,
# www.greenhouse.io, www.lever.co): a link to ashbyhq.com/blog/engineering/... would
# otherwise harvest "blog" as a board token and 404 on every future run.
_ATS_HOST_PATTERNS = {
    "greenhouse": re.compile(r"^(job-boards|boards)(\.eu)?\.greenhouse\.io$", re.I),
    "lever": re.compile(r"^jobs(\.eu)?\.lever\.co$", re.I),
    "ashby": re.compile(r"^jobs\.ashbyhq\.com$", re.I),
}

# Path segments that are never a board token.
_TOKEN_STOPWORDS = {
    "", "jobs", "job", "embed", "board", "boards", "v1", "v0", "postings",
    "posting-api", "job-board", "apply", "application", "search", "en", "www",
    "blog", "engineering", "resources", "customers", "pricing", "about",
    "company", "careers", "login", "signup", "product", "docs", "guides",
}


def _pause():
    time.sleep(random.uniform(0.2, 0.5))


def _kw_tokens(job_title: str) -> List[str]:
    return [t for t in re.split(r"[^\w+]+", (job_title or "").lower()) if len(t) > 1]


def _matches_keywords(text: str, tokens: List[str]) -> bool:
    if not tokens:
        return True
    t = (text or "").lower()
    return any(tok in t for tok in tokens)


def _within_posting_window(posted_value) -> bool:
    dt = parse_posted_at(posted_value)
    if dt is None:
        return True
    return posted_at_within_window(dt)


def _token_to_name(token: str) -> str:
    """'shieldai' → 'Shieldai'; 'ribbon-health' → 'Ribbon Health'. Overridable in config."""
    overrides = getattr(config, "ATS_COMPANY_NAMES", None) or {}
    hit = overrides.get((token or "").lower().strip())
    if hit:
        return hit
    parts = [p for p in re.split(r"[-_]+", (token or "").strip()) if p]
    return " ".join(p.capitalize() for p in parts) or token


def _looks_remote(*fields) -> bool:
    blob = " ".join(str(f or "") for f in fields).lower()
    return any(w in blob for w in ("remote", "anywhere", "distributed", "work from home"))


def _remote_wanted() -> bool:
    return bool(getattr(config, "REMOTE_ONLY", False))


# ─── Token registry ────────────────────────────────────────────────────────────

def _tokens_file() -> str:
    path = getattr(config, "ATS_TOKENS_FILE", "ats_tokens.json")
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    return path


def load_harvested_tokens() -> Dict[str, List[str]]:
    """Read ATS_TOKENS_FILE; returns {provider: [tokens]} (empty dict when absent)."""
    path = _tokens_file()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return {
            k: sorted({str(t).lower().strip() for t in (v or []) if str(t).strip()})
            for k, v in data.items()
            if k in ("greenhouse", "lever", "ashby")
        }
    except Exception as e:
        print(f"  ⚠ ATS token file unreadable ({e}) — using config lists only")
        return {}


def save_harvested_tokens(found: Dict[str, Set[str]]) -> Dict[str, int]:
    """Merge newly-found tokens into ATS_TOKENS_FILE. Returns {provider: n_added}."""
    existing = load_harvested_tokens()
    added = {}
    merged = {}
    for provider in ("greenhouse", "lever", "ashby"):
        old = set(existing.get(provider) or [])
        new = {t.lower().strip() for t in (found.get(provider) or set()) if t.strip()}
        # never persist a token already hard-coded in config
        new -= {t.lower() for t in _config_tokens(provider)}
        merged[provider] = sorted(old | new)
        added[provider] = len(new - old)
    with open(_tokens_file(), "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2, sort_keys=True)
    return added


def extract_ats_token(url: str) -> Optional[tuple]:
    """
    ('greenhouse', 'vercel') from any Greenhouse/Lever/Ashby job URL, else None.

    Handles job-boards.greenhouse.io/vercel/jobs/123, boards.greenhouse.io/vercel/...,
    jobs.lever.co/shieldai/<uuid>, jobs.ashbyhq.com/ashby/<uuid>.
    """
    if not url:
        return None
    try:
        parsed = urllib.parse.urlparse(url if "//" in url else f"https://{url}")
    except Exception:
        return None
    host = (parsed.netloc or "").lower().split(":")[0]
    provider = None
    for name, pattern in _ATS_HOST_PATTERNS.items():
        if pattern.match(host):
            provider = name
            break
    if not provider:
        return None

    segments = [s for s in (parsed.path or "").split("/") if s]
    # Greenhouse embed links carry the token in the query string instead.
    if provider == "greenhouse":
        qs = urllib.parse.parse_qs(parsed.query or "")
        for key in ("for", "token"):
            if qs.get(key):
                cand = qs[key][0].strip().lower()
                if cand and cand not in _TOKEN_STOPWORDS:
                    return (provider, cand)
    for seg in segments:
        cand = seg.strip().lower()
        if cand in _TOKEN_STOPWORDS:
            continue
        # skip UUID / numeric job ids
        if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", cand):
            continue
        if cand.isdigit():
            continue
        return (provider, cand)
    return None


def harvest_tokens_from_urls(urls) -> Dict[str, Set[str]]:
    """Scan an iterable of job URLs and group any ATS board tokens by provider."""
    found: Dict[str, Set[str]] = {"greenhouse": set(), "lever": set(), "ashby": set()}
    for url in urls or []:
        hit = extract_ats_token(url)
        if hit:
            found[hit[0]].add(hit[1])
    return found


def _config_tokens(provider: str) -> List[str]:
    attr = {
        "greenhouse": "GREENHOUSE_BOARDS",
        "lever": "LEVER_BOARDS",
        "ashby": "ASHBY_BOARDS",
    }[provider]
    return [str(t).lower().strip() for t in (getattr(config, attr, None) or []) if str(t).strip()]


def board_tokens(provider: str) -> List[str]:
    """Config seed list + harvested tokens, de-duplicated, order-stable."""
    out, seen = [], set()
    for t in _config_tokens(provider) + (load_harvested_tokens().get(provider) or []):
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


# ─── Pure parsers (unit-tested; no network) ────────────────────────────────────

def parse_greenhouse_jobs(payload: dict, token: str, job_title: str, max_results: int) -> List[Dict[str, Any]]:
    """Greenhouse /jobs payload → job dicts. Company name comes from the API itself."""
    out: List[Dict[str, Any]] = []
    kw = _kw_tokens(job_title)
    remote_only = _remote_wanted()
    for j in (payload or {}).get("jobs") or []:
        title = (j.get("title") or "").strip()
        url = (j.get("absolute_url") or "").strip()
        if not (title and url):
            continue
        if not _matches_keywords(title, kw):
            continue
        location = ((j.get("location") or {}).get("name") or "").strip()
        if remote_only and not _looks_remote(location, title):
            continue
        posted = j.get("first_published") or j.get("updated_at")
        if not _within_posting_window(posted):
            continue
        company = (j.get("company_name") or "").strip() or _token_to_name(token)
        out.append(
            {
                "company": company,
                "title": title,
                "url": url,
                "platform": "Greenhouse",
                "domain": "",
                "search_country": location or "Global",
                "posted_at": posted,
            }
        )
        if len(out) >= max_results:
            break
    return out


def parse_lever_jobs(payload: list, token: str, job_title: str, max_results: int) -> List[Dict[str, Any]]:
    """Lever /postings payload → job dicts. createdAt is epoch MILLISECONDS."""
    out: List[Dict[str, Any]] = []
    kw = _kw_tokens(job_title)
    remote_only = _remote_wanted()
    company = _token_to_name(token)
    for j in payload or []:
        if not isinstance(j, dict):
            continue
        title = (j.get("text") or "").strip()
        url = (j.get("hostedUrl") or j.get("applyUrl") or "").strip()
        if not (title and url):
            continue
        if not _matches_keywords(title, kw):
            continue
        cats = j.get("categories") or {}
        location = (cats.get("location") or "").strip()
        workplace = (j.get("workplaceType") or "").strip()
        if remote_only and workplace.lower() != "remote" and not _looks_remote(location, title):
            continue
        created = j.get("createdAt")
        posted = None
        if isinstance(created, (int, float)):
            posted = float(created) / 1000.0  # ms → s for parse_posted_at
        elif isinstance(created, str) and created.isdigit():
            posted = float(created) / 1000.0
        if not _within_posting_window(posted):
            continue
        out.append(
            {
                "company": company,
                "title": title,
                "url": url,
                "platform": "Lever",
                "domain": "",
                "search_country": location or "Global",
                "posted_at": posted,
            }
        )
        if len(out) >= max_results:
            break
    return out


def parse_ashby_jobs(payload: dict, token: str, job_title: str, max_results: int) -> List[Dict[str, Any]]:
    """Ashby job-board payload → job dicts. Honours isListed and isRemote."""
    out: List[Dict[str, Any]] = []
    kw = _kw_tokens(job_title)
    remote_only = _remote_wanted()
    company = _token_to_name(token)
    for j in (payload or {}).get("jobs") or []:
        if j.get("isListed") is False:
            continue
        title = (j.get("title") or "").strip()
        url = (j.get("jobUrl") or j.get("applyUrl") or "").strip()
        if not (title and url):
            continue
        if not _matches_keywords(f"{title} {j.get('department') or ''}", kw):
            continue
        location = (j.get("location") or "").strip()
        if remote_only and not j.get("isRemote") and not _looks_remote(location, j.get("workplaceType")):
            continue
        posted = j.get("publishedAt")
        if not _within_posting_window(posted):
            continue
        out.append(
            {
                "company": company,
                "title": title,
                "url": url,
                "platform": "Ashby",
                "domain": "",
                "search_country": location or "Global",
                "posted_at": posted,
            }
        )
        if len(out) >= max_results:
            break
    return out


# ─── Fetch drivers ─────────────────────────────────────────────────────────────

def _fetch_json(url: str, timeout: int = 25):
    """GET → parsed JSON, or None on any non-200 / parse failure (404 = unknown token)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _scrape_provider(provider: str, label: str, url_tmpl: str, parser, job_title: str, max_results: int) -> List[Dict[str, Any]]:
    """Shared driver: fan out over board tokens concurrently, parse, cap at max_results."""
    tokens = board_tokens(provider)
    if not tokens:
        print(f"  → {label}: skipped — no board tokens (add to config or run --harvest-ats)")
        return []

    print(f"  → Searching {label} ({len(tokens)} board(s))...")
    workers = max(1, int(getattr(config, "ATS_FETCH_WORKERS", 6)))
    per_board = max(1, int(getattr(config, "ATS_MAX_PER_BOARD", 25)))
    results: List[Dict[str, Any]] = []
    dead = 0

    def one(token):
        return token, _fetch_json(url_tmpl.format(token=urllib.parse.quote(token, safe="")))

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for token, payload in pool.map(one, tokens):
                if payload is None:
                    dead += 1
                    continue
                try:
                    results.extend(parser(payload, token, job_title, per_board))
                except Exception as e:
                    print(f"  ⚠ {label}/{token}: parse failed ({e})")
        if dead:
            print(f"     ({dead} board token(s) returned no data — likely renamed or closed)")
        results = results[:max_results]
        print(f"  ✓ {label}: {len(results)} results")
    except Exception as e:
        print(f"  ✗ {label} error: {e}")
    _pause()
    return results


def scrape_greenhouse(job_title: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """Greenhouse public board API across every configured/harvested board token."""
    return _scrape_provider(
        "greenhouse", "Greenhouse", GREENHOUSE_URL, parse_greenhouse_jobs, job_title, max_results
    )


def scrape_lever(job_title: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """Lever public postings API across every configured/harvested board token."""
    return _scrape_provider(
        "lever", "Lever", LEVER_URL, parse_lever_jobs, job_title, max_results
    )


def scrape_ashby(job_title: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """Ashby public job-board API across every configured/harvested board token."""
    return _scrape_provider(
        "ashby", "Ashby", ASHBY_URL, parse_ashby_jobs, job_title, max_results
    )
