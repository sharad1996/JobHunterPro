"""
Post-search filters: block large tech, optional headcount band, dedupe by company.
"""

import re
import unicodedata
import config


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
    """Apply giant blocklist, headcount rules, then company dedupe."""
    filtered = []
    skipped_giant = 0
    skipped_headcount = 0
    for j in jobs:
        if is_blocked_giant(j.get("company", "")):
            skipped_giant += 1
            continue
        if not passes_headcount_band(j):
            skipped_headcount += 1
            continue
        filtered.append(j)

    deduped = dedupe_same_company_keep_first(filtered)
    if skipped_giant or skipped_headcount or len(deduped) < len(filtered):
        parts = []
        if skipped_giant:
            parts.append(f"{skipped_giant} giant(s)")
        if skipped_headcount:
            parts.append(f"{skipped_headcount} headcount / no-data rule")
        if len(deduped) < len(filtered):
            parts.append("company dedupe")
        print(f"\n  🧹 Filters: {', '.join(parts)} — {len(filtered)} → {len(deduped)} listing(s).")
    return deduped
