"""
Post-search filters: block large tech, optional headcount band, posting age, dedupe by company.
"""

import re
import unicodedata
from datetime import datetime, timedelta, timezone

import config


def max_job_posting_age_days() -> int:
    """Days since posting — listings older than this are dropped when a date is known."""
    try:
        return max(1, int(getattr(config, "MAX_JOB_POSTING_AGE_DAYS", 10)))
    except (TypeError, ValueError):
        return 10


def parse_posted_at(value):
    """Parse ISO/RFC dates or epoch seconds into timezone-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            try:
                from email.utils import parsedate_to_datetime

                dt = parsedate_to_datetime(s)
            except (TypeError, ValueError, IndexError):
                return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def posted_at_within_window(posted_at: datetime) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_job_posting_age_days())
    return posted_at >= cutoff


def passes_posting_age(job: dict) -> bool:
    """Drop jobs with posted_at older than MAX_JOB_POSTING_AGE_DAYS; keep if date unknown."""
    raw = job.get("posted_at")
    if raw is None:
        return True
    dt = raw if isinstance(raw, datetime) else parse_posted_at(raw)
    if dt is None:
        return True
    return posted_at_within_window(dt)


def normalize_company_name(name: str) -> str:
    """Public company-name normaliser (shared with outreach_history)."""
    return _norm_company(name)


def _norm_company(name: str) -> str:
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip().lower()
    return n


def is_blocked_giant(company: str) -> bool:
    """True if company name matches configured big-tech / giant blocklist (whole-word)."""
    if not getattr(config, "FILTER_OUT_BIG_TECH", True):
        return False
    n = (company or "").lower()
    for needle in getattr(config, "BIG_TECH_BLOCKLIST", []) or []:
        g = (needle or "").strip().lower()
        if not g:
            continue
        try:
            if re.search(rf"(?<![a-z0-9]){re.escape(g)}(?![a-z0-9])", n, re.I):
                return True
        except re.error:
            if g in n:
                return True
    return False


def _parse_int(x):
    if x is None:
        return None
    if isinstance(x, int):
        return x
    try:
        return int(str(x).strip())
    except (ValueError, TypeError):
        return None


def passes_headcount_band(job: dict) -> bool:
    """
    If job has employee_count_min / employee_count_max (from a board that provides it),
    keep only when band overlaps [TARGET_EMPLOYEE_MIN, TARGET_EMPLOYEE_MAX].
    If SKIP_JOBS_WITHOUT_HEADCOUNT_DATA is True, drop jobs with no headcount fields.
    """
    lo = _parse_int(job.get("employee_count_min"))
    hi = _parse_int(job.get("employee_count_max"))
    tmin = int(getattr(config, "TARGET_EMPLOYEE_MIN", 1))
    tmax = int(getattr(config, "TARGET_EMPLOYEE_MAX", 500))

    if getattr(config, "SKIP_JOBS_WITHOUT_HEADCOUNT_DATA", False):
        if lo is None and hi is None:
            return False

    if lo is None and hi is None:
        return True

    lo = lo if lo is not None else 1
    hi = hi if hi is not None else lo
    if hi < lo:
        lo, hi = hi, lo
    # overlap [tmin, tmax]
    return not (hi < tmin or lo > tmax)


def dedupe_same_company_keep_first(jobs: list) -> list:
    """Keep only the first listing per normalized company name."""
    if not getattr(config, "DEDUPE_BY_COMPANY_NAME", True):
        return list(jobs)
    seen = set()
    out = []
    for j in jobs:
        key = _norm_company(j.get("company", ""))
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(j)
    return out


def filter_job_list(jobs: list) -> list:
    """Apply giant blocklist, headcount rules, posting age, then company dedupe."""
    filtered = []
    skipped_giant = 0
    skipped_headcount = 0
    skipped_old = 0
    for j in jobs:
        if is_blocked_giant(j.get("company", "")):
            skipped_giant += 1
            continue
        if not passes_headcount_band(j):
            skipped_headcount += 1
            continue
        if not passes_posting_age(j):
            skipped_old += 1
            continue
        filtered.append(j)

    deduped = dedupe_same_company_keep_first(filtered)
    if skipped_giant or skipped_headcount or skipped_old or len(deduped) < len(filtered):
        parts = []
        if skipped_giant:
            parts.append(f"{skipped_giant} giant(s)")
        if skipped_headcount:
            parts.append(f"{skipped_headcount} headcount / no-data rule")
        if skipped_old:
            parts.append(
                f"{skipped_old} older than {max_job_posting_age_days()} day(s)"
            )
        if len(deduped) < len(filtered):
            parts.append("company dedupe")
        print(f"\n  🧹 Filters: {', '.join(parts)} — {len(filtered)} → {len(deduped)} listing(s).")
    return deduped
