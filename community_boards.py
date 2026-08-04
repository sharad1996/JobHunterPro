"""
Hacker News "Ask HN: Who is hiring?" — the monthly thread, via the free Algolia API.

Two calls, no key:
  1. newest thread   https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring
  2. its comments    https://hn.algolia.com/api/v1/items/{id}   (top-level children only)

Top-level comments follow a strong community convention:

    Company | Role | Location | Salary | REMOTE | https://apply.here

so the first pipe-delimited line yields company/role/location, and the first link in the
body yields the apply URL. Nested replies are discussion, not postings, and are ignored.

Value here is small companies that never appear on aggregators, often with a founder
email inline — which is exactly what email_finder can use directly.
"""

import compat  # noqa: F401 — before requests/urllib3

import html
import random
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

import config
from job_filters import parse_posted_at

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"

# Segment noise that is never a company name.
_NOT_A_COMPANY = re.compile(
    r"^(remote|onsite|on-site|hybrid|full[\s-]?time|part[\s-]?time|contract|intern(ship)?|"
    r"visa|h1b|salary|equity|usd|eur|gbp|\$|www\.|https?:)",
    re.I,
)

_LOCATION_HINT = re.compile(
    r"\b(remote|onsite|on-site|hybrid|anywhere|worldwide|us|usa|uk|eu|emea|apac|india|"
    r"germany|berlin|london|nyc|new york|san francisco|sf|bay area|austin|toronto|"
    r"amsterdam|paris|singapore|tokyo|dubai|bangalore|bengaluru|pune|mumbai)\b",
    re.I,
)

_ROLE_HINT = re.compile(
    r"\b(engineer|developer|dev|designer|scientist|manager|lead|architect|analyst|"
    r"devops|sre|qa|founding|fullstack|full[\s-]?stack|frontend|front[\s-]?end|"
    r"backend|back[\s-]?end|mobile|ios|android|data|ml|ai|platform|infra|security|"
    r"intern|staff|senior|principal|head\sof)\b",
    re.I,
)


def _pause():
    time.sleep(random.uniform(0.4, 1.0))


def _kw_tokens(job_title: str) -> List[str]:
    return [t for t in re.split(r"[^\w+]+", (job_title or "").lower()) if len(t) > 1]


def _matches_keywords(text: str, tokens: List[str]) -> bool:
    if not tokens:
        return True
    t = (text or "").lower()
    return any(tok in t for tok in tokens)


def _strip_html(raw: str) -> str:
    """HN comment HTML → plain text, keeping paragraph breaks as newlines."""
    if not raw:
        return ""
    text = re.sub(r"<\s*p\s*/?\s*>", "\n", raw, flags=re.I)
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t ]+", " ", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def _first_url(raw_html: str, plain: str) -> str:
    """Prefer the href of the first real link; fall back to a bare URL in the text."""
    for m in re.finditer(r'href="([^"]+)"', raw_html or "", re.I):
        url = html.unescape(m.group(1)).strip()
        if url.startswith("http") and "news.ycombinator.com" not in url:
            return url
    m = re.search(r"https?://[^\s<>\"')]+", plain or "")
    return m.group(0).rstrip(".,);") if m else ""


def _clean_segment(seg: str) -> str:
    """Normalise one pipe-delimited header segment, dropping any inline URL/email.

    Plenty of posts write "Snout https://snout.com/ | Role | …" with no pipe before the
    link, which would otherwise end up glued onto the company name.
    """
    s = re.sub(r"https?://\S+", " ", seg or "")
    s = re.sub(r"\bwww\.\S+", " ", s)
    s = re.sub(r"\S+@\S+\.\w+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" \t|-–—*·,;:").strip()


def parse_hn_comment(raw_html: str, job_title: str) -> Optional[Dict[str, Any]]:
    """
    One top-level HN comment → job dict, or None when it isn't a parseable posting.

    Requires a company and a URL; role/location are best-effort from the header line.
    """
    plain = _strip_html(raw_html)
    if not plain:
        return None

    header = next((ln for ln in plain.split("\n") if ln.strip()), "")
    segments = [_clean_segment(s) for s in header.split("|")]
    segments = [s for s in segments if s]
    if not segments:
        return None

    company = segments[0]
    # A header without pipes is usually prose; only trust a short leading fragment.
    if len(segments) == 1:
        if len(company) > 60 or " " not in company:
            company = company.split(".")[0].strip()
        if len(company.split()) > 6:
            return None
    if not company or len(company) > 80 or _NOT_A_COMPANY.match(company):
        return None

    rest = segments[1:]
    title = next((s for s in rest if _ROLE_HINT.search(s)), "")
    location = next(
        (s for s in rest if s != title and _LOCATION_HINT.search(s)), ""
    )
    if not title:
        title = job_title

    url = _first_url(raw_html, plain)
    if not url:
        return None

    # Keyword gate against the whole posting, not just the header — roles are often
    # listed deeper in the body.
    if not _matches_keywords(plain, _kw_tokens(job_title)):
        return None

    return {
        "company": company,
        "title": title[:150],
        "url": url,
        "platform": "HN Who Is Hiring",
        "domain": "",
        "search_country": location[:80] or "Global",
    }


def _latest_thread() -> Optional[Dict[str, Any]]:
    """Newest 'Ask HN: Who is hiring?' story (skips the 'Who wants to be hired?' twin)."""
    try:
        r = requests.get(
            SEARCH_URL,
            headers=HEADERS,
            params={"tags": "story,author_whoishiring", "hitsPerPage": 10},
            timeout=25,
        )
        if r.status_code != 200:
            print(f"  ✗ HN: search HTTP {r.status_code}")
            return None
        for hit in (r.json() or {}).get("hits") or []:
            title = (hit.get("title") or "").lower()
            if "who is hiring" in title and "wants to be hired" not in title:
                return hit
    except Exception as e:
        print(f"  ✗ HN search error: {e}")
    return None


def scrape_hn_whoishiring(job_title: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """Parse the current month's HN 'Who is hiring?' thread for matching postings."""
    results: List[Dict[str, Any]] = []
    print("  → Searching HN Who Is Hiring (Algolia API)...")

    thread = _latest_thread()
    if not thread:
        print("  ✗ HN: could not locate a 'Who is hiring?' thread")
        return results

    thread_id = thread.get("objectID")
    created = thread.get("created_at")
    print(f"     thread: {thread.get('title')} (#{thread_id})")

    # HN posts one thread on the 1st of each month and it stays the live thread all month.
    # So it gets its own window (HN_MAX_THREAD_AGE_DAYS) rather than the global
    # MAX_JOB_POSTING_AGE_DAYS, which is tuned for day-fresh aggregator listings and
    # would blank this source out for most of every month.
    max_age = max(1, int(getattr(config, "HN_MAX_THREAD_AGE_DAYS", 40)))
    dt = parse_posted_at(created)
    if dt is not None:
        age_days = (datetime.now(timezone.utc) - dt).days
        if age_days > max_age:
            print(
                f"  ⚠ HN: newest thread is {age_days}d old (> HN_MAX_THREAD_AGE_DAYS "
                f"{max_age}d) — skipping as stale"
            )
            return results

    try:
        r = requests.get(ITEM_URL.format(id=thread_id), headers=HEADERS, timeout=40)
        if r.status_code != 200:
            print(f"  ✗ HN: item HTTP {r.status_code}")
            return results
        children = (r.json() or {}).get("children") or []
    except Exception as e:
        print(f"  ✗ HN item error: {e}")
        return results

    seen = set()
    for child in children:
        if len(results) >= max_results:
            break
        if child.get("parent_id") and child.get("parent_id") != int(thread_id):
            continue
        job = parse_hn_comment(child.get("text") or "", job_title)
        if not job:
            continue
        key = (job["company"].lower(), job["url"].split("?")[0].lower())
        if key in seen:
            continue
        seen.add(key)
        # Deliberately no posted_at: these are month-scoped, and job_filters would drop
        # them against MAX_JOB_POSTING_AGE_DAYS. Thread freshness is already checked above.
        job["notes"] = f"HN Who Is Hiring — {thread.get('title') or ''}".strip(" —")
        results.append(job)

    print(f"  ✓ HN Who Is Hiring: {len(results)} results (from {len(children)} postings)")
    _pause()
    return results
