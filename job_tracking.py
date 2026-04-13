"""
Excel (xlsx) job tracking + skip rules for already-actioned roles.

Columns are looked up by header name so you can reorder columns in Excel.
Mark \"Applied on portal\", \"Application email sent\", or isEmailed=TRUE to skip application emails.
Mark \"Follow-up email sent\" or isFollowed=TRUE to skip follow-up emails.
"""

import os
from datetime import datetime
from urllib.parse import urlparse, urlunparse

import config

try:
    from openpyxl import Workbook, load_workbook
except ImportError:  # pragma: no cover
    Workbook = load_workbook = None  # type: ignore


HEADERS = [
    "Job URL",
    "Company",
    "Job title",
    "Platform",
    "Region",
    "Headcount note",
    "Application email sent",
    "Follow-up email sent",
    "isEmailed",
    "isFollowed",
    "Applied on portal",
    "HR email",
    "Notes",
    "Updated at",
]


def normalize_job_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return ""
    u = url.strip()
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = (p.path or "").rstrip("/") or "/"
        q = ""  # strip query for stable matching
        return urlunparse((p.scheme.lower(), host, path, "", q, ""))
    except Exception:
        return u.lower().rstrip("/")


def _xlsx_path() -> str:
    return getattr(config, "JOB_TRACKING_XLSX", "job_tracking.xlsx")


def _ensure_openpyxl():
    if Workbook is None:
        raise RuntimeError("openpyxl is required for Excel tracking. Run: pip install openpyxl")


def ensure_workbook(path: str = None) -> str:
    _ensure_openpyxl()
    path = path or _xlsx_path()
    if os.path.exists(path):
        return path
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Jobs"
    ws.append(HEADERS)
    wb.save(path)
    return path


def _header_map(ws) -> dict:
    row1 = [str(c.value or "").strip() for c in ws[1]]
    return {name: idx + 1 for idx, name in enumerate(row1)}


def _cell(ws, col_map: dict, row: int, header: str, default=""):
    c = col_map.get(header)
    if not c:
        return default
    v = ws.cell(row=row, column=c).value
    return "" if v is None else str(v).strip()


def _is_yes(val: str) -> bool:
    v = (val or "").strip().lower()
    return v in ("y", "yes", "true", "1", "x")


def load_skip_url_set(path: str = None) -> set:
    """URLs that should not be searched/applied again."""
    path = path or _xlsx_path()
    if not os.path.exists(path):
        return set()
    _ensure_openpyxl()
    wb = load_workbook(path, read_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    try:
        header = next(it)
    except StopIteration:
        wb.close()
        return set()
    headers = [str(h or "").strip() for h in header]
    col_map = {h: i for i, h in enumerate(headers)}
    url_i = col_map.get("Job URL")
    app_i = col_map.get("Application email sent")
    portal_i = col_map.get("Applied on portal")
    is_emailed_i = col_map.get("isEmailed")
    if url_i is None:
        wb.close()
        return set()
    skip = set()
    for row in it:
        if not row or url_i >= len(row) or not row[url_i]:
            continue
        url = normalize_job_url(str(row[url_i]))
        if not url:
            continue
        app = _is_yes(str(row[app_i]) if app_i is not None and app_i < len(row) else "")
        portal = _is_yes(str(row[portal_i]) if portal_i is not None and portal_i < len(row) else "")
        is_emailed = _is_yes(
            str(row[is_emailed_i]) if is_emailed_i is not None and is_emailed_i < len(row) else ""
        )
        if app or portal or is_emailed:
            skip.add(url)
    wb.close()
    return skip


def load_followup_skip_urls(path: str = None) -> set:
    """URLs that must not receive a follow-up (Follow-up email sent / isFollowed on the sheet)."""
    path = path or _xlsx_path()
    if not os.path.exists(path):
        return set()
    _ensure_openpyxl()
    wb = load_workbook(path, read_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    try:
        header = next(it)
    except StopIteration:
        wb.close()
        return set()
    headers = [str(h or "").strip() for h in header]
    col_map = {h: i for i, h in enumerate(headers)}
    url_i = col_map.get("Job URL")
    fu_i = col_map.get("Follow-up email sent")
    is_followed_i = col_map.get("isFollowed")
    if url_i is None:
        wb.close()
        return set()
    skip = set()
    for row in it:
        if not row or url_i >= len(row) or not row[url_i]:
            continue
        url = normalize_job_url(str(row[url_i]))
        if not url:
            continue
        fu = _is_yes(str(row[fu_i]) if fu_i is not None and fu_i < len(row) else "")
        is_followed = _is_yes(
            str(row[is_followed_i]) if is_followed_i is not None and is_followed_i < len(row) else ""
        )
        if fu or is_followed:
            skip.add(url)
    wb.close()
    return skip


def upsert_row(
    job: dict,
    job_title: str,
    path: str = None,
    *,
    application_email_sent: str = "",
    followup_sent: str = "",
    applied_portal: str = "",
    hr_email: str = "",
    notes: str = "",
) -> None:
    """Insert or update one row keyed by Job URL."""
    path = ensure_workbook(path)
    _ensure_openpyxl()
    wb = load_workbook(path)
    ws = wb.active
    cmap = _header_map(ws)
    for h in HEADERS:
        if h not in cmap:
            # append missing columns
            col = ws.max_column + 1
            ws.cell(row=1, column=col, value=h)
            cmap = _header_map(ws)

    url = normalize_job_url(job.get("url") or "")
    target_row = None
    for r in range(2, ws.max_row + 1):
        if normalize_job_url(_cell(ws, cmap, r, "Job URL")) == url and url:
            target_row = r
            break

    if target_row is None:
        target_row = ws.max_row + 1

    def put(header, value, overwrite=True):
        c = cmap.get(header)
        if not c:
            return
        cur = ws.cell(row=target_row, column=c).value
        if not overwrite and cur not in (None, ""):
            return
        ws.cell(row=target_row, column=c, value=value)

    put("Job URL", job.get("url") or "", True)
    put("Company", job.get("company") or "", True)
    put("Job title", job.get("title") or job_title, True)
    put("Platform", job.get("platform") or "", True)
    put("Region", job.get("search_country") or "", True)
    hn = job.get("headcount_note") or job.get("company_size") or ""
    put("Headcount note", hn, True)
    if application_email_sent:
        put("Application email sent", application_email_sent, True)
        put("isEmailed", "TRUE", True)
    if followup_sent:
        put("Follow-up email sent", followup_sent, True)
        put("isFollowed", "TRUE", True)
    if applied_portal:
        put("Applied on portal", applied_portal, True)
    if hr_email:
        put("HR email", hr_email, True)
    if notes:
        put("Notes", notes, False)
    put("Updated at", datetime.now().strftime("%Y-%m-%d %H:%M"), True)

    wb.save(path)
    wb.close()


def sync_from_database(db, path: str = None) -> None:
    """Rebuild sheet rows from SQLite (one row per job)."""
    path = path or _xlsx_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    path = ensure_workbook(path)
    _ensure_openpyxl()
    jobs = db.get_all_jobs(5000)
    wb = Workbook()
    ws = wb.active
    ws.title = "Jobs"
    ws.append(HEADERS)
    for j in jobs:
        url = j.get("job_url") or ""
        app = "Y" if (j.get("email_status") == "sent") else ""
        fu = "Y" if j.get("follow_up_sent") else ""
        is_em = "TRUE" if j.get("email_status") == "sent" else ""
        is_fol = "TRUE" if j.get("follow_up_sent") else ""
        ws.append(
            [
                url,
                j.get("company") or "",
                j.get("job_title") or "",
                j.get("platform") or "",
                j.get("search_country") or "",
                "",
                app,
                fu,
                is_em,
                is_fol,
                "",
                j.get("hr_email") or "",
                "",
                (j.get("applied_at") or "")[:19],
            ]
        )
    wb.save(path)
    wb.close()


def filter_jobs_not_skipped(jobs: list, skip_urls: set) -> tuple:
    """Remove jobs whose URL is in skip_urls."""
    if not skip_urls:
        return jobs, 0
    out = []
    n = 0
    for j in jobs:
        u = normalize_job_url(j.get("url") or "")
        if u and u in skip_urls:
            n += 1
            continue
        out.append(j)
    if n:
        print(f"  ⏭️  Skipped {n} job(s) already marked applied / emailed in {_xlsx_path()}.")
    return out, n
