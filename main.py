#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║              JOB HUNTER PRO  v1.0                           ║
║    Search → Find HR Emails → Apply → Auto Follow-Up         ║
╚══════════════════════════════════════════════════════════════╝

Usage:
  python3 main.py                          → Interactive menu
  python3 main.py --job "Python Developer" → Search and apply directly
  python3 main.py --followup               → Send due follow-ups
  python3 main.py --status                 → Show stats dashboard
  python3 main.py --list                   → List all applications
  python3 main.py --send-pending           → Send pending apps (no new search)
"""

import compat  # noqa: F401 — suppress urllib3/LibreSSL warning before other imports

import argparse
import sys
import os

# ─── Colour helpers (works on Windows too) ─────────────────────────────────────
try:
    import colorama
    colorama.init(autoreset=True)
    RED    = colorama.Fore.RED
    GREEN  = colorama.Fore.GREEN
    YELLOW = colorama.Fore.YELLOW
    CYAN   = colorama.Fore.CYAN
    BOLD   = colorama.Style.BRIGHT
    RESET  = colorama.Style.RESET_ALL
except ImportError:
    RED = GREEN = YELLOW = CYAN = BOLD = RESET = ""


# ─── Banner ────────────────────────────────────────────────────────────────────

def banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════╗
║           🎯  JOB HUNTER PRO  —  Auto Apply Tool            ║
║   Search Jobs → Find HR Emails → Send Resume → Follow Up    ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


# ─── Config check ──────────────────────────────────────────────────────────────

def check_config():
    import config
    errors = config.validate_config()
    if errors:
        print(f"{YELLOW}⚠️  Please complete your setup in config.py:{RESET}")
        for e in errors:
            print(f"   {e}")
        print(f"\n{CYAN}📖 See README.md for step-by-step setup instructions.{RESET}\n")
        return False
    return True


# ─── Search & Apply ────────────────────────────────────────────────────────────

def _load_skip_urls(db, job_tracking):
    """URLs already emailed / applied (Excel + database) — never apply twice."""
    skip = job_tracking.load_skip_url_set()
    for raw in db.get_sent_job_urls():
        nu = job_tracking.normalize_job_url(raw)
        if nu:
            skip.add(nu)
    return skip


def _job_ready_for_batch(job: dict, *, require_verified: bool) -> bool:
    import config
    from email_finder import looks_valid_email

    em = (job.get("hr_email") or "").strip()
    if not em or not looks_valid_email(em):
        return False
    if require_verified and getattr(config, "SEND_ONLY_VERIFIED_EMAILS", True):
        v = job.get("hr_email_verified")
        if not (v is True or v == 1):
            return False
    return True


def _select_jobs_for_batch(
    jobs: list, skip_urls: set, limit: int, history=None, search_title: str = ""
) -> list:
    """
    Find verified HR emails until `limit` new jobs are ready (stops early).

    `history` (OutreachHistory) short-circuits the expensive lookup twice over: jobs whose
    company+role were already emailed are dropped without any network calls, and companies
    with a known address reuse it instead of re-scraping contact pages.
    """
    import time

    import config
    from email_finder import find_hr_email_for_company
    import job_tracking

    require_verified = getattr(config, "BATCH_REQUIRE_VERIFIED_EMAIL", True)
    if not getattr(config, "SEND_ONLY_VERIFIED_EMAILS", True):
        require_verified = False

    selected = []
    scanned = 0
    skipped_history = 0
    reused = 0
    for job in jobs:
        if len(selected) >= limit:
            break
        url = job.get("url") or ""
        nu = job_tracking.normalize_job_url(url)
        if nu and nu in skip_urls:
            continue
        company = job.get("company", "") or ""

        # Already emailed for this company+role → no lookup, no duplicate application.
        if history is not None and history.already_emailed(
            company, search_title, job.get("title") or ""
        ):
            skipped_history += 1
            if nu:
                skip_urls.add(nu)
            continue

        scanned += 1
        print(f"  [{len(selected) + 1}/{limit} target] {company[:52]}", end="  ", flush=True)

        cached = history.known_email(company) if history is not None else None
        if cached:
            result = dict(cached)
            reused += 1
        else:
            result = find_hr_email_for_company(
                company,
                url,
                job.get("company_website") or job.get("domain") or "",
                allow_guesses=not require_verified,
            )
        job.update(result)
        if result.get("domain"):
            job["domain"] = result["domain"]
        if _job_ready_for_batch(job, require_verified=require_verified):
            selected.append(job)
            if cached:
                tag = "known company email"
            else:
                tag = "contact page" if job.get("hr_email_verified") else "email"
            print(f"→ {job['hr_email']}  [{tag}]")
            if nu:
                skip_urls.add(nu)
        else:
            em = job.get("hr_email") or ""
            print(f"→ skip ({em or 'no email'})")
        if not cached:
            time.sleep(0.2)

    notes = []
    if skipped_history:
        notes.append(f"{skipped_history} skipped as already emailed")
    if reused:
        notes.append(f"{reused} reused a known address")
    suffix = f" ({', '.join(notes)})" if notes else ""
    print(
        f"\n  Scanned {scanned} new listing(s), selected {len(selected)} "
        f"with sendable email.{suffix}"
    )
    return selected


def _print_batch_send_blockers(saved: int, eligible: int, send_meta: dict):
    """Explain why batch rows were saved but not emailed."""
    import config

    blocked = saved - eligible
    if blocked <= 0:
        return
    reasons = []
    if send_meta.get("sheet_skipped"):
        reasons.append(
            f"{send_meta['sheet_skipped']} blocked on {getattr(config, 'JOB_TRACKING_XLSX', 'job_tracking.xlsx')} "
            f"(Application email sent / isEmailed already marked)"
        )
    if send_meta.get("unverified_skipped"):
        reasons.append(
            f"{send_meta['unverified_skipped']} HR email not verified "
            f"(set SEND_ONLY_VERIFIED_EMAILS = False to send guesses — risky)"
        )
    if send_meta.get("invalid_syntax"):
        reasons.append(f"{send_meta['invalid_syntax']} invalid email address in database")
    if not reasons:
        reasons.append(
            f"{blocked} row(s) are not pending send in the database "
            f"(often already marked sent for the same company, or sync changed the row)"
        )
    print(f"  Why {blocked} were skipped:")
    for line in reasons:
        print(f"    • {line}")


def cmd_run_batch(job_title: str, dry_run: bool = False, limit: int = None):
    """
    One command: search → up to N new jobs with verified email → xlsx → DB → send → mark applied.
    Skips jobs already in the tracking sheet or database as sent/applied (by Job URL).
    """
    import config
    import job_tracking
    from job_filters import filter_job_list
    from scrapers import search_all_platforms
    from email_sender import send_applications, application_send_candidates
    from database import Database

    limit = limit or int(getattr(config, "BATCH_JOB_LIMIT", 25))
    db = Database()
    xlsx_path = getattr(config, "JOB_TRACKING_XLSX", "job_tracking.xlsx")

    print(
        f"\n{BOLD}🚀 Batch run: up to {limit} new application(s) for \"{job_title}\"{RESET}\n"
        f"  (skips URLs already marked applied/emailed in {xlsx_path} or DB)\n"
    )

    if getattr(config, "REMOTE_ONLY", False):
        cc = ", ".join(getattr(config, "TARGET_COUNTRIES", []) or [])
        print(f"{CYAN}Remote search — regions: {cc}{RESET}\n")
    else:
        print(f"{CYAN}Location: {getattr(config, 'JOB_LOCATION', '')}{RESET}\n")

    jobs = search_all_platforms(job_title)
    if not jobs:
        print(f"{RED}No jobs found.{RESET}")
        return

    print(f"{GREEN}✅ {len(jobs)} raw listing(s) from boards{RESET}")

    try:
        job_tracking.ensure_workbook()
        skip_urls = _load_skip_urls(db, job_tracking)
        jobs, n_skip = job_tracking.filter_jobs_not_skipped(jobs, skip_urls)
        if n_skip:
            print(f"  ⏭️  {n_skip} already applied/emailed (won't apply again)")
    except Exception as e:
        print(f"{YELLOW}⚠️  Excel skip list unavailable: {e}{RESET}")
        skip_urls = _load_skip_urls(db, job_tracking)

    jobs = filter_job_list(jobs)
    if not jobs:
        print(f"{RED}No new jobs after filters.{RESET}")
        return

    from outreach_history import OutreachHistory

    history = OutreachHistory.load(db)
    print(f"\n🧠 Outreach history: {history.summary()}")

    print(f"\n📧 Finding contact-page emails (target {limit} jobs)…")
    selected = _select_jobs_for_batch(
        jobs, skip_urls, limit, history=history, search_title=job_title
    )
    if not selected:
        print(
            f"{RED}\nNo sendable emails found in this batch. "
            f"Try another title or set BATCH_REQUIRE_VERIFIED_EMAIL = False in config.py.{RESET}"
        )
        return

    print(f"\n{GREEN}✅ {len(selected)} job(s) ready — writing sheet & database…{RESET}")
    try:
        job_tracking.bulk_upsert_initial(selected, job_title)
    except Exception as e:
        print(f"{YELLOW}⚠️  Sheet bulk write: {e}{RESET}")

    batch_ids = []
    for job in selected:
        jid, action = db.upsert_job_enrichment(job, job_title)
        batch_ids.append(jid)
        try:
            job_tracking.upsert_row(job, job_title, hr_email=job.get("hr_email") or "")
        except Exception:
            pass

    try:
        job_tracking.sync_with_database(db, xlsx_path)
    except Exception as e:
        print(f"{YELLOW}⚠️  Sheet sync: {e}{RESET}")

    print_results_table(selected)

    if dry_run:
        eligible, send_meta = application_send_candidates(db, None, job_ids=batch_ids)
        print(
            f"\n{YELLOW}[DRY RUN] Would send {len(eligible)} of {len(batch_ids)} "
            f"saved job(s); no messages sent.{RESET}"
        )
        if len(eligible) < len(batch_ids):
            _print_batch_send_blockers(len(batch_ids), len(eligible), send_meta)
        return

    eligible, send_meta = application_send_candidates(db, None, job_ids=batch_ids)
    if not eligible:
        print(f"\n{YELLOW}⚠️  Saved {len(batch_ids)} job(s) to the sheet and database, but none could be emailed.{RESET}")
        _print_batch_send_blockers(len(batch_ids), 0, send_meta)
        print(
            f"\n{CYAN}📒 {xlsx_path} was updated with job listings and HR emails (not marked as sent).{RESET}"
        )
        return

    if len(eligible) < len(batch_ids):
        print(
            f"\n{YELLOW}Note: {len(eligible)} of {len(batch_ids)} saved job(s) pass send filters "
            f"(the rest are already sent, blocked on the sheet, or unverified).{RESET}"
        )

    print(f"\n📨 Sending {len(eligible)} application email(s) (no prompt)…")
    sent = send_applications(db, job_title=None, dry_run=False, job_ids=batch_ids)
    print(f"\n{GREEN}✅ Batch complete: {sent} email(s) sent.{RESET}")
    if sent:
        print(f"{CYAN}📒 {xlsx_path} updated (Application email sent / isEmailed).{RESET}")
    print(f"{CYAN}📅 Follow-ups due in {config.FOLLOW_UP_DAYS} days — run: python3 main.py --followup{RESET}")


def cmd_search_and_apply(job_title: str, dry_run: bool = False):
    import config
    import job_tracking
    from job_filters import filter_job_list
    from scrapers import search_all_platforms
    from email_finder import find_hr_emails
    from email_sender import send_applications, application_send_candidates
    from database import Database

    db = Database()

    max_age = getattr(config, "MAX_JOB_POSTING_AGE_DAYS", 10)
    if getattr(config, "REMOTE_ONLY", False):
        cc = ", ".join(getattr(config, "TARGET_COUNTRIES", []) or [])
        print(
            f"\n{BOLD}🔍 Remote-only search for '{job_title}' — regions: {cc} "
            f"(posted within last {max_age} days){RESET}\n"
        )
    else:
        loc = getattr(config, "JOB_LOCATION", "")
        print(
            f"\n{BOLD}🔍 Searching for '{job_title}' (location: {loc}, "
            f"posted within last {max_age} days)...{RESET}\n"
        )

    jobs = search_all_platforms(job_title)

    if not jobs:
        print(f"{RED}No jobs found. Try a different job title or check your internet connection.{RESET}")
        return

    print(f"\n{GREEN}✅ Raw listings from boards: {len(jobs)}{RESET}")

    try:
        job_tracking.ensure_workbook()
        skip_urls = _load_skip_urls(db, job_tracking)
        jobs, _skipped_tr = job_tracking.filter_jobs_not_skipped(jobs, skip_urls)
    except Exception as e:
        print(f"{YELLOW}⚠️  Excel tracking unavailable ({e}). Install: pip install openpyxl{RESET}")

    jobs = filter_job_list(jobs)

    if not jobs:
        print(f"{RED}No jobs left after filters / skip list. Adjust config or your tracking sheet.{RESET}")
        return

    # Drop company+role combos already emailed BEFORE the HR-email lookup — that lookup
    # is the slowest step in the run, so paying it for a job we'd never send is pure waste.
    from outreach_history import OutreachHistory

    history = OutreachHistory.load(db)
    print(f"\n🧠 Outreach history: {history.summary()}")
    before_history = len(jobs)
    jobs = [
        j
        for j in jobs
        if not history.already_emailed(j.get("company", ""), job_title, j.get("title") or "")
    ]
    if before_history != len(jobs):
        print(
            f"  ⏭️  {before_history - len(jobs)} listing(s) already emailed for this "
            f"company+role — skipped before email lookup"
        )

    if not jobs:
        print(
            f"{RED}Every listing was already emailed for this role. "
            f"Try a different job title.{RESET}"
        )
        return

    print(f"\n{GREEN}✅ {len(jobs)} listing(s) after filters & skip rules{RESET}")

    xlsx_path = getattr(config, "JOB_TRACKING_XLSX", "job_tracking.xlsx")
    try:
        ins, upd = job_tracking.bulk_upsert_initial(jobs, job_title)
        print(
            f"{CYAN}📒 Wrote {len(jobs)} listing(s) to {xlsx_path} "
            f"({ins} new, {upd} already there) — before HR-email lookup. "
            f"Open the sheet to add emails for any row.{RESET}"
        )
    except Exception as e:
        print(f"{YELLOW}⚠️  Could not write initial rows to {xlsx_path}: {e}{RESET}")

    jobs_enriched = find_hr_emails(jobs, history=history)

    # Save / refresh jobs in DB (duplicates must be updated or HR emails stay empty)
    new_count = 0
    updated_count = 0
    for job in jobs_enriched:
        _jid, action = db.upsert_job_enrichment(job, job_title)
        if action == "inserted":
            new_count += 1
        elif action == "updated":
            updated_count += 1
        try:
            job_tracking.upsert_row(job, job_title)
        except Exception:
            pass

    print(
        f"\n{GREEN}💾 Database: {new_count} new, {updated_count} updated, "
        f"{len(jobs_enriched) - new_count - updated_count} unchanged (already sent or duplicate sent row){RESET}"
    )
    print(
        f"{CYAN}📎 HR emails refreshed in {xlsx_path} for jobs found on contact pages. "
        f"For the rest, add an address in the HR email column then "
        f"`python3 main.py --sync-from-xlsx`.{RESET}"
    )

    # Print results table
    print_results_table(jobs_enriched)

    guessed = sum(
        1
        for j in jobs_enriched
        if j.get("hr_email") and j.get("hr_email_verified") is False
    )
    if guessed:
        print(
            f"\n{YELLOW}⚠️  {guessed} address(es) are pattern guesses (not found on a contact page). "
            f"They are not auto-sent while SEND_ONLY_VERIFIED_EMAILS is True — use --add-email if you know the address.{RESET}"
        )

    # Save per-job application + follow-up drafts (includes job URLs for manual outreach)
    draft_path = write_outreach_drafts(job_title, jobs_enriched)

    # Ask to edit emails manually before sending
    print(f"\n{YELLOW}Tip: HR guesses often need verification. Edit drafts in {draft_path} or run --add-email.{RESET}")

    # Prompt to send — must match DB pending rows, not in-memory count (duplicates / already-sent differ)
    has_email = sum(1 for j in jobs_enriched if j.get("hr_email"))
    if has_email == 0:
        xlsx_path = getattr(config, "JOB_TRACKING_XLSX", "job_tracking.xlsx")
        print(
            f"{RED}\nNo HR emails found via contact pages or guessing. "
            f"Use job URLs in {draft_path} to find contacts.{RESET}"
        )
        print(
            f"{GREEN}All {len(jobs_enriched)} listing(s) are still in {xlsx_path} (company, URL, platform). "
            f"Add an address in the HR email column, then run:{RESET}\n"
            f"  {CYAN}python3 main.py --sync-from-xlsx{RESET}\n"
            f"{GREEN}Or use:{RESET} {CYAN}python3 main.py --add-email{RESET}"
        )
        return

    raw_pending = db.get_pending_applications(job_title)
    eligible, send_meta = application_send_candidates(db, job_title)
    pending_ready = len(eligible)
    if pending_ready == 0:
        if not raw_pending:
            print(
                f"{RED}\nNo pending application emails for job title \"{job_title}\" in the database "
                f"(all matching rows may already be marked sent, or rows were not saved).{RESET}"
            )
        else:
            xlsx_path = getattr(config, "JOB_TRACKING_XLSX", "job_tracking.xlsx")
            print(
                f"{YELLOW}\nNo sendable pending rows: {len(raw_pending)} in the database for this title, "
                f"but all were filtered (unverified guesses, tracking sheet, or invalid email). "
                f"Add HR emails in the sheet/--add-email or set SEND_ONLY_VERIFIED_EMAILS = False in config.py.{RESET}"
            )
            print(
                f"{GREEN}Rows stay in {xlsx_path}. Add or fix HR email there, then:{RESET} "
                f"{CYAN}python3 main.py --sync-from-xlsx{RESET}"
            )
        return
    if send_meta["unverified_skipped"] and getattr(config, "SEND_ONLY_VERIFIED_EMAILS", True):
        print(
            f"{YELLOW}\n  ({send_meta['unverified_skipped']} row(s) with guessed addresses excluded from send.){RESET}"
        )
    if has_email != pending_ready:
        print(
            f"{YELLOW}\nNote: This run has addresses for {has_email} listing(s), but only {pending_ready} "
            f"row(s) in the DB are pending send for this job title. "
            f"The rest are usually rows already marked sent, or duplicate rows that were not refreshed yet.{RESET}"
        )

    if not dry_run:
        confirm = input(
            f"\n{BOLD}📨 Send application emails to {pending_ready} recipient(s) for \"{job_title}\" now? (y/n): {RESET}"
        ).strip().lower()
        if confirm != "y":
            xlsx_path = getattr(config, "JOB_TRACKING_XLSX", "job_tracking.xlsx")
            print(
                f"\n{CYAN}No emails sent. Listings are in {xlsx_path}; add HR emails in the sheet, then "
                f"python3 main.py --sync-from-xlsx, then python3 main.py --send-pending --job \"{job_title}\"{RESET}"
            )
            print(f"{CYAN}Or run 'python3 main.py --list' to review.{RESET}")
            return

    sent = send_applications(db, job_title, dry_run=dry_run)
    print(f"\n{GREEN}✅ Successfully sent {sent} application emails!{RESET}")
    print(f"{CYAN}📅 Follow-up emails will be sent automatically in {config.FOLLOW_UP_DAYS} days.{RESET}")
    print(f"{CYAN}   Run 'python3 main.py --followup' any time to send due follow-ups.{RESET}")
    print(f"{CYAN}   Tracking sheet: {getattr(config, 'JOB_TRACKING_XLSX', 'job_tracking.xlsx')}{RESET}")


def cmd_fill_hr_emails(force: bool = False, limit: int = None, dry_run: bool = False):
    """Scrape contact pages for companies in job_tracking.xlsx and fill HR email column."""
    import config
    import job_tracking

    path = getattr(config, "JOB_TRACKING_XLSX", "job_tracking.xlsx")
    try:
        stats = job_tracking.enrich_hr_emails_in_xlsx(
            path,
            only_missing=not force,
            limit=limit,
            dry_run=dry_run,
        )
    except Exception as e:
        print(f"\n{RED}Fill HR emails failed: {e}{RESET}")
        return

    if stats["processed"] == 0:
        print(
            f"\n{YELLOW}No rows to process in {path} "
            f"(all have HR email, or no Company name). Use --force to refresh existing emails.{RESET}"
        )
        return

    if dry_run:
        print(f"\n{YELLOW}Dry run — no changes written to {path}.{RESET}")

    print(
        f"\n{GREEN}✅ Sheet update complete.{RESET} "
        f"Processed {stats['processed']} row(s), filled {stats['filled']} "
        f"({stats['verified']} from contact pages, {stats['guessed']} guessed)."
    )
    if stats["not_found"]:
        print(
            f"{YELLOW}  {stats['not_found']} row(s) still have no HR email "
            f"(no contact page match; guesses disabled unless FILL_XLSX_INCLUDE_GUESSES).{RESET}"
        )
    if stats.get("skipped_has_email") and not force:
        print(
            f"{CYAN}  {stats['skipped_has_email']} row(s) already had HR email (use --force to re-fetch).{RESET}"
        )
    if stats["filled"] and not dry_run:
        print(
            f"\n{CYAN}Next: python3 main.py --sync-from-xlsx  "
            f"then  python3 main.py --send-pending [--job \"Your Title\"]{RESET}"
        )


def cmd_clear_db(
    *,
    all_rows: bool = False,
    pending_only: bool = False,
    older_than_days: int = None,
    job_title: str = None,
    yes: bool = False,
):
    """Remove job rows from SQLite (and related email_log entries)."""
    from database import Database

    db = Database()
    before = db.get_stats()

    if all_rows:
        scope = "ALL jobs and email log entries"
        n = before["total"]
    elif pending_only:
        scope = "pending jobs only (keeps sent / follow-up history)"
        n = db.count_jobs(pending_only=True)
    elif older_than_days is not None:
        scope = f"jobs older than {older_than_days} day(s)"
        n = None
    elif job_title:
        scope = f'jobs with job_title "{job_title}"'
        n = None
    else:
        print(
            f"{RED}Specify what to delete: --all, --pending, --older-than N, or --job \"Title\"{RESET}"
        )
        return

    print(f"\n{YELLOW}Will delete {scope} from {db.db_path}.{RESET}")
    print(
        f"  Current DB: {before['total']} job(s), "
        f"{before['applied']} sent, {before['no_email']} pending without email."
    )
    if n is not None:
        print(f"  Rows to remove: ~{n}")

    if not yes:
        confirm = input(f"\n{BOLD}Type 'yes' to confirm deletion: {RESET}").strip().lower()
        if confirm != "yes":
            print(f"{YELLOW}Cancelled — no rows deleted.{RESET}")
            return

    try:
        result = db.delete_jobs(
            all_rows=all_rows,
            pending_only=pending_only,
            older_than_days=older_than_days,
            job_title=job_title,
        )
    except ValueError as e:
        print(f"{RED}{e}{RESET}")
        return

    after = db.get_stats()
    print(
        f"\n{GREEN}✅ Deleted {result['jobs_deleted']} job row(s) and "
        f"{result['log_deleted']} email log row(s).{RESET}"
    )
    print(f"  Remaining in DB: {after['total']} job(s).")


def cmd_sync_xlsx():
    """Two-way sync: job_tracking.xlsx ↔ SQLite (matched by Job URL)."""
    import config
    import job_tracking
    from database import Database

    db = Database()
    path = getattr(config, "JOB_TRACKING_XLSX", "job_tracking.xlsx")
    before = db.get_stats()
    try:
        stats = job_tracking.sync_with_database(db, path)
    except Exception as e:
        print(f"\n{RED}Sync failed: {e}{RESET}")
        return
    after = db.get_stats()
    print(f"\n{GREEN}✅ Synced {path} with {db.db_path}{RESET}")
    print(
        f"  Sheet: {stats['sheet_rows']} row(s) — "
        f"DB +{stats['db_inserted']} inserted, {stats['db_updated']} updated"
    )
    print(f"  Sheet: {stats['xlsx_updated']} row(s) merged from DB, {stats['xlsx_appended']} appended")
    print(f"  Database: {before['total']} → {after['total']} job(s)")
    print(f"{CYAN}Then run: python3 main.py --send-pending [--job \"Your Title\"]{RESET}")


def cmd_sync_from_xlsx():
    """Alias for full two-way sync (same as --sync-xlsx)."""
    cmd_sync_xlsx()


def cmd_harvest_ats(dry_run: bool = False):
    """
    Scan every job URL already collected (SQLite + Excel) for Greenhouse / Lever / Ashby
    board tokens and append the new ones to ATS_TOKENS_FILE.

    Those three boards have no cross-company search, so this is how coverage grows:
    every run that lands an ATS link teaches the next run a new company board.
    """
    import ats_boards
    import config
    from database import Database

    print(f"\n{BOLD}🏛️  Harvesting ATS board tokens{RESET}")

    urls = []
    try:
        db = Database()
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT job_url FROM jobs WHERE job_url IS NOT NULL AND job_url != ''"
            ).fetchall()
        urls.extend(r[0] for r in rows)
        print(f"  → {len(urls)} URL(s) from {db.db_path}")
    except Exception as e:
        print(f"  ⚠ Could not read database: {e}")

    xlsx_path = getattr(config, "JOB_TRACKING_XLSX", "job_tracking.xlsx")
    if os.path.exists(xlsx_path):
        try:
            import openpyxl

            wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
            before = len(urls)
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        if isinstance(cell, str) and cell.startswith("http"):
                            urls.append(cell)
            wb.close()
            print(f"  → {len(urls) - before} URL(s) from {xlsx_path}")
        except Exception as e:
            print(f"  ⚠ Could not read {xlsx_path}: {e}")

    if not urls:
        print(f"{YELLOW}No URLs to scan. Run a search first.{RESET}")
        return

    found = ats_boards.harvest_tokens_from_urls(urls)
    total = sum(len(v) for v in found.values())
    if not total:
        print(
            f"{YELLOW}No Greenhouse/Lever/Ashby links found in {len(urls)} URL(s).{RESET}\n"
            f"{CYAN}These appear once boards like LinkedIn/Indeed link out to company ATS pages.{RESET}"
        )
        return

    for provider, tokens in sorted(found.items()):
        if tokens:
            print(f"\n  {BOLD}{provider}{RESET}: {len(tokens)} token(s)")
            print(f"    {', '.join(sorted(tokens))}")

    if dry_run:
        print(f"\n{YELLOW}[DRY RUN] Nothing written.{RESET}")
        return

    added = ats_boards.save_harvested_tokens(found)
    net = sum(added.values())
    print(
        f"\n{GREEN}✅ {net} new token(s) saved to "
        f"{getattr(config, 'ATS_TOKENS_FILE', 'ats_tokens.json')}{RESET}"
    )
    for provider in ("greenhouse", "lever", "ashby"):
        print(f"  {provider}: +{added.get(provider, 0)} new, {len(ats_boards.board_tokens(provider))} total active")
    print(f"{CYAN}Next search will include them automatically.{RESET}")


def cmd_export_xlsx():
    """Overwrite Excel from SQLite (manual 'Applied on portal' cells may be reset)."""
    import config
    import job_tracking
    from database import Database

    db = Database()
    path = getattr(config, "JOB_TRACKING_XLSX", "job_tracking.xlsx")
    job_tracking.sync_from_database(db, path)
    print(f"\n{GREEN}✅ Wrote {path} from database.{RESET}")
    print(
        f"{YELLOW}Note: this overwrites the sheet from SQLite — re-apply any manual "
        f"\"Applied on portal\" cells if you use them.{RESET}"
    )


# ─── Follow-ups ────────────────────────────────────────────────────────────────

def cmd_followup(dry_run: bool = False):
    from email_sender import send_followups
    from database import Database

    db = Database()
    print(f"\n{BOLD}📬 Checking for pending follow-up emails...{RESET}\n")
    sent = send_followups(db, dry_run=dry_run)

    if sent > 0:
        print(f"\n{GREEN}✅ Sent {sent} follow-up email(s)!{RESET}")
    else:
        print(f"\n{YELLOW}No follow-ups due right now. Check back later.{RESET}")


def cmd_send_pending(job_title: str = None, dry_run: bool = False):
    """Send application emails for DB-pending rows, respecting isEmailed on the tracking sheet."""
    from email_sender import send_applications
    from database import Database

    db = Database()
    scope = f" for \"{job_title}\"" if job_title else " (all job titles)"
    print(f"\n{BOLD}📨 Pending application sends{scope} — skips rows with isEmailed / already marked on the sheet.{RESET}\n")
    sent = send_applications(db, job_title, dry_run=dry_run)
    if sent > 0:
        print(f"\n{GREEN}✅ Sent {sent} application email(s).{RESET}")
    else:
        print(
            f"\n{YELLOW}Nothing sent — no pending rows, or all skipped (tracking sheet, unverified guesses, or invalid email).{RESET}"
        )


def cmd_auth_save(platform: str, start_url: str):
    """Interactive Playwright login; saves storage state for Indeed / Wellfound / Upwork fetches."""
    import config
    from browser_fetch import interactive_save_storage_state

    print(
        f"\n{YELLOW}If 'Continue with Google' fails or SMS codes never arrive, use the site's email/password "
        f"login when offered — Google often blocks automated browsers.{RESET}\n"
    )
    path = config.auth_storage_path(platform)
    interactive_save_storage_state(start_url, path, profile_key=platform)


def cmd_auth_indeed():
    cmd_auth_save("indeed", "https://secure.indeed.com/auth")


def cmd_auth_wellfound():
    cmd_auth_save("wellfound", "https://wellfound.com/login")


def cmd_auth_upwork():
    """Saves session JSON for a future browser-based Upwork search; GraphQL uses OAuth env vars."""
    cmd_auth_save("upwork", "https://www.upwork.com/ab/account-security/login")


# ─── Status dashboard ──────────────────────────────────────────────────────────

def cmd_status():
    from database import Database
    db = Database()
    stats = db.get_stats()

    print(f"\n{BOLD}📊 APPLICATION DASHBOARD{RESET}")
    print("─" * 40)
    print(f"  📁 Total tracked companies   : {stats['total']}")
    print(f"  ✉️  Applications sent          : {stats['applied']}")
    print(f"  📬 Follow-ups sent            : {stats['followed_up']}")
    print(f"  ⏳ Pending follow-ups         : {stats['pending_followup']}")
    print(f"  💬 Replies received           : {stats['replied']}")
    print(f"  ❓ No email found             : {stats['no_email']}")
    print("─" * 40)

    if stats["pending_followup"] > 0:
        print(f"\n{YELLOW}⚡ {stats['pending_followup']} follow-up(s) are due! Run: python3 main.py --followup{RESET}")


# ─── List all applications ─────────────────────────────────────────────────────

def cmd_list(limit: int = 50):
    from database import Database
    db = Database()
    jobs = db.get_all_jobs(limit)

    if not jobs:
        print(f"\n{YELLOW}No applications tracked yet. Run: python3 main.py --job \"Job Title\"{RESET}")
        return

    print(
        f"\n{BOLD}{'#':<4} {'Company':<20} {'Region':<12} {'Plat':<8} "
        f"{'Job URL':<32} {'HR Email':<22} {'St':<8} {'Applied':<12}{RESET}"
    )
    print("─" * 128)

    for i, job in enumerate(jobs, 1):
        email = (job.get("hr_email") or "—")[:20]
        status = job.get("email_status", "pending")
        applied = (job.get("applied_at") or "—")[:10]
        fu_sent = "✅" if job.get("follow_up_sent") else ""
        replied = "💬" if job.get("reply_received") else ""
        jurl = _truncate(job.get("job_url") or "—", 30)
        reg = _truncate(job.get("search_country") or "—", 12)

        # Colour by status
        if status == "sent":
            col = GREEN
        elif status == "pending" and email != "—":
            col = YELLOW
        else:
            col = RESET

        print(
            f"{col}{i:<4} {job['company'][:18]:<20} {reg:<12} {job.get('platform', '')[:8]:<8} "
            f"{jurl:<32} {email:<22} {status:<8} {applied:<12} {fu_sent}{replied}{RESET}"
        )

    print(f"\n{len(jobs)} records shown.")


# ─── Manual email add ──────────────────────────────────────────────────────────

def cmd_add_email():
    from database import Database
    db = Database()

    jobs = db.get_all_jobs(200)
    no_email = [j for j in jobs if not j.get("hr_email")]

    if not no_email:
        print(f"\n{GREEN}All tracked companies already have HR emails!{RESET}")
        return

    print(f"\n{BOLD}Companies missing HR emails ({len(no_email)} total):{RESET}\n")
    for i, job in enumerate(no_email, 1):
        print(f"  {i}. {job['company']} ({job.get('platform','')})")

    print(f"\nEnter job number and HR email (e.g.: 3 hr@company.com) or 'q' to quit.")
    while True:
        inp = input("  → ").strip()
        if inp.lower() in ("q", "quit", ""):
            break
        parts = inp.split()
        if len(parts) == 2:
            try:
                idx   = int(parts[0]) - 1
                email = parts[1]
                job   = no_email[idx]
                db.update_hr_email(job["id"], email)
                print(f"  {GREEN}✅ Updated {job['company']} → {email}{RESET}")
            except (ValueError, IndexError):
                print(f"  {RED}Invalid input. Try again.{RESET}")
        else:
            print(f"  {RED}Format: <number> <email>{RESET}")


# ─── Outreach drafts file ─────────────────────────────────────────────────────

def _truncate(s: str, max_len: int) -> str:
    s = s or ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def write_outreach_drafts(job_title: str, jobs: list, path: str = "outreach_drafts.txt") -> str:
    """Write application + follow-up email drafts per job (uses company/title from search)."""
    import config
    import templates

    if getattr(config, "REMOTE_ONLY", False):
        scope = "Remote-only | Regions: " + ", ".join(getattr(config, "TARGET_COUNTRIES", []) or [])
    else:
        scope = f"Location: {getattr(config, 'JOB_LOCATION', '')}"

    chunks = []
    for i, job in enumerate(jobs, 1):
        company = job.get("company", "")
        title = job.get("title") or job_title
        url = (job.get("url") or "").strip() or "(no URL — search this company on the job board)"
        hr = (job.get("hr_email") or "").strip() or "(not found — verify before sending)"
        app = templates.application_email(title, company)
        fu = templates.followup_email(title, company)
        region = (job.get("search_country") or "").strip() or "—"
        chunks.append(
            f"\n{'=' * 72}\n"
            f"#{i}  {company}\n"
            f"Search region: {region}\n"
            f"Platform: {job.get('platform', '')}\n"
            f"Role title: {title}\n"
            f"Job URL: {url}\n"
            f"HR / target email: {hr}\n"
            f"\n--- Application email ---\n"
            f"Subject: {app['subject']}\n\n{app['body_text']}\n"
            f"\n--- Follow-up email ---\n"
            f"Subject: {fu['subject']}\n\n{fu['body_text']}\n"
        )
    out = (
        f"Job Hunter Pro — outreach drafts for: {job_title}\n"
        f"{scope}\n"
        f"Review addresses before sending. Attach your resume only when emailing for real.\n"
        + "".join(chunks)
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"\n{GREEN}📝 Drafts (application + follow-up + URLs) saved to {path}{RESET}")
    return path


# ─── Pretty results table ──────────────────────────────────────────────────────

def print_results_table(jobs: list):
    print(
        f"\n{BOLD}{'#':<4} {'Company':<22} {'Region':<14} {'Plat':<8} "
        f"{'Job URL':<36} {'HR Email':<22} {'?'}{RESET}"
    )
    print("─" * 118)
    for i, job in enumerate(jobs, 1):
        email = job.get("hr_email", "—") or "—"
        found = f"{GREEN}✓{RESET}" if email != "—" else f"{RED}✗{RESET}"
        company = _truncate(job.get("company", ""), 22)
        region = _truncate((job.get("search_country") or "—"), 14)
        platform = _truncate(job.get("platform", ""), 8)
        url_disp = _truncate((job.get("url") or "—"), 34)
        print(f"{i:<4} {company:<22} {region:<14} {platform:<8} {url_disp:<36} {email[:20]:<22} {found}")


# ─── Interactive menu ──────────────────────────────────────────────────────────

def interactive_menu():
    while True:
        print(f"""
{BOLD}What would you like to do?{RESET}

  {CYAN}1.{RESET} 🚀  Batch run (search → 25 jobs → email → send → update sheet)
  {CYAN}2.{RESET} 📬  Send pending follow-up emails
  {CYAN}3.{RESET} 📊  View application dashboard
  {CYAN}4.{RESET} 📋  List all tracked applications
  {CYAN}5.{RESET} ✏️   Add HR email manually (for companies missing one)
  {CYAN}6.{RESET} 📤  Export job tracking Excel from database
  {CYAN}7.{RESET} 📨  Send pending application emails (no new search)
  {CYAN}8.{RESET} 🔄  Sync HR emails from Excel into database (by Job URL)
  {CYAN}9.{RESET} 📧  Fill HR emails in Excel from company contact pages
  {CYAN}10.{RESET} 🗑️   Clear old records from database
  {CYAN}11.{RESET} 🚪  Exit
""")
        choice = input("Enter choice (1-11): ").strip()

        if choice == "1":
            job_title = input("\n💼 Enter job title or technology (e.g. 'Python Developer', 'React', 'Data Analyst'): ").strip()
            if job_title:
                cmd_run_batch(job_title)
        elif choice == "2":
            cmd_followup()
        elif choice == "3":
            cmd_status()
        elif choice == "4":
            cmd_list()
        elif choice == "5":
            cmd_add_email()
        elif choice == "6":
            cmd_export_xlsx()
        elif choice == "7":
            jt = input(
                "\nOptional: job title to limit sends (leave blank for all pending): "
            ).strip() or None
            cmd_send_pending(job_title=jt, dry_run=False)
        elif choice == "8":
            cmd_sync_xlsx()
        elif choice == "9":
            cmd_fill_hr_emails()
        elif choice == "10":
            print(f"\n{YELLOW}Delete: 1=all  2=pending only  3=older than N days{RESET}")
            sub = input("Choice (1/2/3): ").strip()
            if sub == "1":
                cmd_clear_db(all_rows=True, yes=False)
            elif sub == "2":
                cmd_clear_db(pending_only=True, yes=False)
            elif sub == "3":
                try:
                    days = int(input("Older than how many days? ").strip())
                except ValueError:
                    print(f"{RED}Invalid number.{RESET}")
                else:
                    cmd_clear_db(older_than_days=days, yes=False)
        elif choice == "11":
            print(f"\n{GREEN}Good luck with your job search! 🚀{RESET}\n")
            sys.exit(0)
        else:
            print(f"{RED}Invalid choice. Please enter 1-11.{RESET}")


# ─── Entry point ───────────────────────────────────────────────────────────────

def main():
    banner()

    parser = argparse.ArgumentParser(
        description="Job Hunter Pro — automated job search & email outreach tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py
  python3 main.py --run --job "Python Developer"
  python3 main.py --run --job "React Developer" --limit 10
  python3 main.py --job "Python Developer"
  python3 main.py --followup
  python3 main.py --status
  python3 main.py --list
  python3 main.py --job "React Developer" --dry-run
  python3 main.py --export-xlsx
  python3 main.py --send-pending
  python3 main.py --send-pending --job "React Developer"
  python3 main.py --auth-indeed
  python3 main.py --auth-wellfound
  python3 main.py --auth-upwork
  python3 main.py --sync-xlsx
  python3 main.py --sync-from-xlsx
  python3 main.py --fill-hr-emails
  python3 main.py --fill-hr-emails --limit 20
  python3 main.py --fill-hr-emails --force
  python3 main.py --clear-db --all --yes
  python3 main.py --clear-db --pending --yes
  python3 main.py --clear-db --older-than 30 --yes
        """
    )
    parser.add_argument("--auth-indeed", action="store_true", help="Save Indeed login session for Playwright (headed browser)")
    parser.add_argument("--auth-wellfound", action="store_true", help="Save Wellfound login session for Playwright")
    parser.add_argument("--auth-upwork", action="store_true", help="Save Upwork login session (reserved for browser fetch)")
    parser.add_argument(
        "--run",
        action="store_true",
        help="One-shot batch: search, find emails for up to N jobs (default 25), sync sheet+DB, send, mark applied",
    )
    parser.add_argument("--job",      type=str, help="Job title or technology to search (required with --run)")
    parser.add_argument(
        "--send-pending",
        action="store_true",
        help="Send pending application emails only (no search); optional --job to limit by title",
    )
    parser.add_argument("--followup", action="store_true", help="Send pending follow-up emails")
    parser.add_argument("--status",   action="store_true", help="Show application dashboard")
    parser.add_argument("--list",     action="store_true", help="List all tracked applications")
    parser.add_argument("--add-email",action="store_true", help="Manually add HR emails")
    parser.add_argument("--export-xlsx", action="store_true", help="Export SQLite jobs to Excel tracking sheet")
    parser.add_argument(
        "--sync-xlsx",
        action="store_true",
        help="Two-way sync job_tracking.xlsx with SQLite (by Job URL)",
    )
    parser.add_argument(
        "--sync-from-xlsx",
        action="store_true",
        help="Alias for --sync-xlsx (sheet ↔ database)",
    )
    parser.add_argument(
        "--fill-hr-emails",
        action="store_true",
        help="Scrape company contact pages and fill empty HR email cells in job_tracking.xlsx",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --fill-hr-emails: re-fetch even when HR email column is already filled",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="With --fill-hr-emails: process at most N rows (empty HR email only unless --force)",
    )
    parser.add_argument("--dry-run",  action="store_true", help="Simulate without actually sending emails")
    parser.add_argument(
        "--clear-db",
        action="store_true",
        help="Delete job rows from SQLite (use with --all, --pending, or --older-than)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="With --clear-db: delete every job and email log row",
    )
    parser.add_argument(
        "--pending",
        action="store_true",
        help="With --clear-db: delete only pending (unsent) jobs",
    )
    parser.add_argument(
        "--older-than",
        type=int,
        metavar="DAYS",
        help="With --clear-db: delete jobs created more than N days ago",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt (required for non-interactive --clear-db)",
    )
    parser.add_argument(
        "--harvest-ats",
        action="store_true",
        help="Scan collected job URLs for Greenhouse/Lever/Ashby board tokens and save them",
    )
    args = parser.parse_args()

    # Config check (skip for status/list since those don't send emails)
    if args.run or args.job or args.followup or args.send_pending:
        if not check_config():
            sys.exit(1)

    if args.auth_indeed:
        cmd_auth_indeed()
    elif args.auth_wellfound:
        cmd_auth_wellfound()
    elif args.auth_upwork:
        cmd_auth_upwork()
    elif args.clear_db:
        cmd_clear_db(
            all_rows=args.all,
            pending_only=args.pending,
            older_than_days=args.older_than,
            job_title=args.job,
            yes=args.yes,
        )
    elif args.harvest_ats:
        cmd_harvest_ats(dry_run=args.dry_run)
    elif args.fill_hr_emails:
        cmd_fill_hr_emails(force=args.force, limit=args.limit, dry_run=args.dry_run)
    elif args.sync_xlsx or args.sync_from_xlsx:
        cmd_sync_xlsx()
    elif args.export_xlsx:
        cmd_export_xlsx()
    elif args.send_pending:
        cmd_send_pending(job_title=args.job, dry_run=args.dry_run)
    elif args.run:
        if not args.job:
            print(f"{RED}--run requires --job \"Your Job Title\"{RESET}")
            sys.exit(1)
        cmd_run_batch(args.job, dry_run=args.dry_run, limit=args.limit)
    elif args.job:
        cmd_search_and_apply(args.job, dry_run=args.dry_run)
    elif args.followup:
        cmd_followup(dry_run=args.dry_run)
    elif args.status:
        cmd_status()
    elif args.list:
        cmd_list()
    elif args.add_email:
        cmd_add_email()
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
