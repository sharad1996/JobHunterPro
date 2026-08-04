"""
Outreach history index — avoids re-running the slow HR-email lookup.

Finding an email costs several HTTP requests per company (domain guess → contact-page
fetches, sometimes a DuckDuckGo hop), so it dominates runtime. The URL skip list only
catches *identical* job URLs, which means a second listing from a company we already
emailed still paid full price for a lookup whose answer was already in the database.

This module loads the whole history in one query and answers two questions in memory:

  already_emailed(company, title)  → we've SENT for this company+role; skip it entirely
  known_email(company)            → we already know an address; reuse it, skip the lookup

Matching is normalised (case, punctuation, legal suffixes) but never fuzzy — a different
role at a known company should still go out, so only exact normalised pairs are skipped.

The `job_title` column holds the *search term* for rows created by a search run, but the
listing's own title for rows synced from the Excel sheet. Both are indexed, and an
incoming job is checked against both its search term and its listing title.
"""

import re
from typing import Any, Dict, Optional, Set, Tuple

import config
from job_filters import normalize_company_name

# Legal incorporation suffixes only — these never distinguish two companies, so
# "Acme Inc" and "Acme" are the same employer.
#
# Descriptive words (Labs, Systems, Solutions, Technologies, Studio, Group…) are
# deliberately NOT here: they're part of the brand. Stripping them would collapse
# "Tech Solutions Inc" and "Tech Systems Ltd" onto the same key and skip a company we
# never emailed — a false skip costs a real application, a redundant lookup costs 12s.
_SUFFIXES = (
    "inc", "inc.", "llc", "l.l.c", "ltd", "limited", "plc", "llp", "lp",
    "gmbh", "ag", "bv", "nv", "sa", "sas", "srl", "spa", "ab", "as", "oy", "oyj",
    "pvt", "private", "pte", "corp", "corporation", "co", "company", "kk", "kg",
)


def norm_company(name: str) -> str:
    """Normalised company key: lowercase, punctuation-stripped, legal suffixes removed."""
    base = normalize_company_name(name)
    if not base:
        return ""
    parts = [p for p in base.split() if p]
    while len(parts) > 1 and parts[-1] in _SUFFIXES:
        parts.pop()
    return " ".join(parts)


def norm_title(title: str) -> str:
    """Normalised role key: lowercase, punctuation collapsed to single spaces."""
    t = (title or "").lower()
    t = re.sub(r"[^\w\s+#]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


class OutreachHistory:
    """In-memory view of who we've already emailed and which addresses we already know."""

    def __init__(self):
        self.sent_pairs: Set[Tuple[str, str]] = set()
        self.sent_companies: Set[str] = set()
        self.known_emails: Dict[str, Dict[str, Any]] = {}
        self.rows_loaded = 0

    # ── construction ────────────────────────────────────────────────────────────

    @classmethod
    def from_rows(cls, rows) -> "OutreachHistory":
        """Build from an iterable of dict-like rows (sqlite3.Row works directly)."""
        self = cls()
        for row in rows or []:
            self.rows_loaded += 1
            company = norm_company(_get(row, "company"))
            if not company:
                continue
            status = (_get(row, "email_status") or "").strip().lower()
            title = norm_title(_get(row, "job_title"))

            if status == "sent":
                self.sent_companies.add(company)
                if title:
                    self.sent_pairs.add((company, title))

            email = (_get(row, "hr_email") or "").strip()
            if email:
                verified = _get(row, "hr_email_verified")
                is_verified = verified is True or verified == 1
                prev = self.known_emails.get(company)
                # Prefer a verified address; otherwise keep the first one seen.
                if prev is None or (is_verified and not prev.get("hr_email_verified")):
                    self.known_emails[company] = {
                        "hr_email": email,
                        "hr_name": (_get(row, "hr_name") or "").strip(),
                        "hr_email_verified": is_verified,
                        "domain": (_get(row, "company_domain") or "").strip(),
                    }
        return self

    @classmethod
    def load(cls, db) -> "OutreachHistory":
        """Build from a Database instance (single query)."""
        try:
            return cls.from_rows(db.get_outreach_history_rows())
        except Exception as e:
            print(f"  ⚠ Outreach history unavailable ({e}) — every company will be looked up")
            return cls()

    # ── queries ─────────────────────────────────────────────────────────────────

    def already_emailed(self, company: str, *titles) -> bool:
        """
        True when an application was already SENT for this company and role.

        Honours two config switches:
          SKIP_ALREADY_EMAILED_ANY_ROLE   — any role at this company counts (opt-in)
          SKIP_ALREADY_EMAILED_SAME_ROLE  — only this exact company+role (default)
        """
        c = norm_company(company)
        if not c:
            return False
        if getattr(config, "SKIP_ALREADY_EMAILED_ANY_ROLE", False):
            if c in self.sent_companies:
                return True
        if not getattr(config, "SKIP_ALREADY_EMAILED_SAME_ROLE", True):
            return False
        for t in titles:
            nt = norm_title(t)
            if nt and (c, nt) in self.sent_pairs:
                return True
        return False

    def known_email(self, company: str) -> Optional[Dict[str, Any]]:
        """A previously-resolved address for this company, or None."""
        if not getattr(config, "REUSE_KNOWN_COMPANY_EMAILS", True):
            return None
        c = norm_company(company)
        if not c:
            return None
        hit = self.known_emails.get(c)
        if not hit:
            return None
        if getattr(config, "REUSE_ONLY_VERIFIED_COMPANY_EMAILS", True) and not hit.get(
            "hr_email_verified"
        ):
            return None
        # Screen replayed addresses too. Older rows were saved before the placeholder
        # blocklist was tightened, so the database still holds things like
        # john.doe@company.com marked "verified" — reusing those would keep them alive
        # forever instead of letting a fresh lookup find the real address.
        if _is_junk(hit.get("hr_email")):
            return None
        return dict(hit)

    def summary(self) -> str:
        return (
            f"{self.rows_loaded} history row(s): {len(self.sent_companies)} company(ies) "
            f"already emailed, {len(self.known_emails)} known address(es)"
        )


def _is_junk(email: str) -> bool:
    """Placeholder/no-reply screen. Imported lazily — email_finder is a heavy module."""
    try:
        from email_finder import is_junk_email

        return is_junk_email(email)
    except Exception:
        return not (email or "").strip()


def _get(row, key: str):
    """Read a key from a sqlite3.Row, dict, or object without assuming the type."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, None)
