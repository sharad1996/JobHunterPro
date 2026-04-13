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

def cmd_search_and_apply(job_title: str, dry_run: bool = False):
    import config
    import job_tracking
    from job_filters import filter_job_list
    from scrapers import search_all_platforms
    from email_finder import find_hr_emails
    from email_sender import send_applications
    from database import Database

    db = Database()

    if getattr(config, "REMOTE_ONLY", False):
        cc = ", ".join(getattr(config, "TARGET_COUNTRIES", []) or [])
        print(
            f"\n{BOLD}🔍 Remote-only search for '{job_title}' — regions: {cc}{RESET}\n"
        )
    else:
        loc = getattr(config, "JOB_LOCATION", "")
        print(f"\n{BOLD}🔍 Searching for '{job_title}' (location: {loc})...{RESET}\n")

    jobs = search_all_platforms(job_title)

    if not jobs:
        print(f"{RED}No jobs found. Try a different job title or check your internet connection.{RESET}")
        return

    print(f"\n{GREEN}✅ Raw listings from boards: {len(jobs)}{RESET}")

    try:
        job_tracking.ensure_workbook()
        skip_urls = job_tracking.load_skip_url_set()
        for raw in db.get_sent_job_urls():
            nu = job_tracking.normalize_job_url(raw)
            if nu:
                skip_urls.add(nu)
        jobs, _skipped_tr = job_tracking.filter_jobs_not_skipped(jobs, skip_urls)
    except Exception as e:
        print(f"{YELLOW}⚠️  Excel tracking unavailable ({e}). Install: pip install openpyxl{RESET}")

    jobs = filter_job_list(jobs)

    if not jobs:
        print(f"{RED}No jobs left after filters / skip list. Adjust config or your tracking sheet.{RESET}")
        return

    print(f"\n{GREEN}✅ {len(jobs)} listing(s) after filters & skip rules{RESET}")

    # Enrich with HR emails
    jobs_enriched = find_hr_emails(jobs)

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

    # Print results table
    print_results_table(jobs_enriched)

    guessed = sum(
        1
        for j in jobs_enriched
        if j.get("hr_email") and j.get("hr_email_verified") is False
    )
    if guessed:
        print(
            f"\n{YELLOW}⚠️  {guessed} address(es) are unverified pattern guesses (hr@, careers@…). "
            f"Confirm on the company site or LinkedIn before sending.{RESET}"
        )

    # Save per-job application + follow-up drafts (includes job URLs for manual outreach)
    draft_path = write_outreach_drafts(job_title, jobs_enriched)

    # Ask to edit emails manually before sending
    print(f"\n{YELLOW}Tip: HR guesses often need verification. Edit drafts in {draft_path} or run --add-email.{RESET}")

    # Prompt to send — must match DB pending rows, not in-memory count (duplicates / already-sent differ)
    has_email = sum(1 for j in jobs_enriched if j.get("hr_email"))
    if has_email == 0:
        print(
            f"{RED}\nNo HR emails found via Hunter/guessing. "
            f"Use job URLs in {draft_path} to apply on the site or find contacts, then add emails with --add-email.{RESET}"
        )
        return

    pending_ready = len(db.get_pending_applications(job_title))
    if pending_ready == 0:
        print(
            f"{RED}\nNo pending application emails for job title \"{job_title}\" in the database "
            f"(all matching rows may already be marked sent, or rows were not saved).{RESET}"
        )
        return
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
            print(f"\n{CYAN}Emails saved. Run 'python3 main.py --list' to review before sending.{RESET}")
            return

    sent = send_applications(db, job_title, dry_run=dry_run)
    print(f"\n{GREEN}✅ Successfully sent {sent} application emails!{RESET}")
    print(f"{CYAN}📅 Follow-up emails will be sent automatically in {config.FOLLOW_UP_DAYS} days.{RESET}")
    print(f"{CYAN}   Run 'python3 main.py --followup' any time to send due follow-ups.{RESET}")
    print(f"{CYAN}   Tracking sheet: {getattr(config, 'JOB_TRACKING_XLSX', 'job_tracking.xlsx')}{RESET}")


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
        print(f"\n{YELLOW}Nothing sent — no pending rows, or all skipped by the tracking sheet.{RESET}")


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

  {CYAN}1.{RESET} 🔍  Search jobs & send application emails
  {CYAN}2.{RESET} 📬  Send pending follow-up emails
  {CYAN}3.{RESET} 📊  View application dashboard
  {CYAN}4.{RESET} 📋  List all tracked applications
  {CYAN}5.{RESET} ✏️   Add HR email manually (for companies missing one)
  {CYAN}6.{RESET} 📤  Export job tracking Excel from database
  {CYAN}7.{RESET} 📨  Send pending application emails (no new search)
  {CYAN}8.{RESET} 🚪  Exit
""")
        choice = input("Enter choice (1-8): ").strip()

        if choice == "1":
            job_title = input("\n💼 Enter job title or technology (e.g. 'Python Developer', 'React', 'Data Analyst'): ").strip()
            if job_title:
                cmd_search_and_apply(job_title)
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
            print(f"\n{GREEN}Good luck with your job search! 🚀{RESET}\n")
            sys.exit(0)
        else:
            print(f"{RED}Invalid choice. Please enter 1-8.{RESET}")


# ─── Entry point ───────────────────────────────────────────────────────────────

def main():
    banner()

    parser = argparse.ArgumentParser(
        description="Job Hunter Pro — automated job search & email outreach tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py
  python3 main.py --job "Python Developer"
  python3 main.py --followup
  python3 main.py --status
  python3 main.py --list
  python3 main.py --job "React Developer" --dry-run
  python3 main.py --export-xlsx
  python3 main.py --send-pending
  python3 main.py --send-pending --job "React Developer"
        """
    )
    parser.add_argument("--job",      type=str, help="Job title or technology to search")
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
    parser.add_argument("--dry-run",  action="store_true", help="Simulate without actually sending emails")
    args = parser.parse_args()

    # Config check (skip for status/list since those don't send emails)
    if args.job or args.followup or args.send_pending:
        if not check_config():
            sys.exit(1)

    if args.export_xlsx:
        cmd_export_xlsx()
    elif args.send_pending:
        cmd_send_pending(job_title=args.job, dry_run=args.dry_run)
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
