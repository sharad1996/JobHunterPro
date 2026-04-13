"""
Email Sender — sends application + follow-up emails via Gmail SMTP.
Uses App Password authentication (no OAuth needed).
"""

import os
import smtplib
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import config
import templates
from database import Database


def _tracking_upsert(job_row: dict, job_title: str, **kwargs):
    try:
        import job_tracking

        jr = dict(job_row)
        jr["url"] = jr.get("job_url") or jr.get("url") or ""
        jr["title"] = jr.get("job_title") or job_title
        job_tracking.upsert_row(jr, job_title, **kwargs)
    except Exception:
        pass


def _guess_attachment_subtype(path: str) -> tuple:
    """Return (maintype, subtype) for add_attachment."""
    lower = path.lower()
    if lower.endswith(".pdf"):
        return "application", "pdf"
    return "application", "octet-stream"


def _send_email(to_email: str, subject: str, body_text: str, body_html: str,
                attachment_path: str = None) -> bool:
    """
    Send one message via Gmail SMTP (plain + HTML + optional attachment).
    Uses EmailMessage so each send has its own Message-ID (better for bulk sends).
    """
    to_email = (to_email or "").strip()
    if not to_email:
        print("\n  ❌ Empty recipient address")
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{config.YOUR_NAME} <{config.GMAIL_EMAIL}>"
        msg["To"] = to_email
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=config.GMAIL_EMAIL.split("@")[-1])

        msg.set_content(body_text, charset="utf-8")
        msg.add_alternative(body_html, subtype="html", charset="utf-8")

        if attachment_path and os.path.exists(attachment_path):
            filename = os.path.basename(attachment_path)
            maintype, subtype = _guess_attachment_subtype(attachment_path)
            with open(attachment_path, "rb") as f:
                data = f.read()
            msg.add_attachment(
                data,
                maintype=maintype,
                subtype=subtype,
                filename=filename,
            )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(config.GMAIL_EMAIL, config.GMAIL_PASSWORD)
            server.send_message(msg, from_addr=config.GMAIL_EMAIL, to_addrs=[to_email])

        return True

    except smtplib.SMTPAuthenticationError:
        print("\n  ❌ Gmail authentication failed!")
        print("     → Use a 16-character App Password (not your normal password)")
        return False
    except smtplib.SMTPRecipientsRefused as e:
        print(f"\n  ❌ Email refused for {to_email}: {e}")
        return False
    except smtplib.SMTPServerDisconnected as e:
        print(f"\n  ❌ SMTP disconnected (try again): {e}")
        return False
    except Exception as e:
        print(f"\n  ❌ Send error: {e}")
        return False


# ─── Application emails ────────────────────────────────────────────────────────

def send_applications(db: Database, job_title: str, dry_run: bool = False) -> int:
    """
    Send one application email per pending row (each recipient gets its own message).
    Skips rows whose Job URL is marked isEmailed / Application email sent / Applied on portal in the tracking sheet.
    """
    pending = db.get_pending_applications(job_title)

    if not pending:
        print("\n  No pending applications to send.")
        return 0

    jt = None
    try:
        import job_tracking as jt
    except Exception:
        jt = None

    if jt is not None:
        block_urls = jt.load_skip_url_set()
        kept = []
        skipped = 0
        for j in pending:
            u = jt.normalize_job_url(j.get("job_url") or "")
            if u and u in block_urls:
                skipped += 1
                continue
            kept.append(j)
        pending = kept
        if skipped:
            print(
                f"\n  ⏭️  Skipped {skipped} row(s): tracking sheet has isEmailed / application already marked."
            )

    if not pending:
        print("\n  No pending applications left after tracking-sheet rules.")
        return 0

    print(f"\n📨 Sending {len(pending)} separate application email(s) (one per job row)…\n")
    sent_count = 0
    failed = 0

    for idx, job in enumerate(pending, start=1):
        company = job["company"]
        hr_email = job["hr_email"]
        hr_name = job.get("hr_name", "")
        job_id = job["id"]
        actual_title = job.get("job_title", job_title)

        email_data = templates.application_email(actual_title, company, hr_name)

        print(f"  [{idx}/{len(pending)}] {company[:40]:<42} {hr_email}")

        if dry_run:
            print(f"     [DRY RUN] Would send: {email_data['subject']}")
            sent_count += 1
            continue

        success = _send_email(
            to_email=hr_email,
            subject=email_data["subject"],
            body_text=email_data["body_text"],
            body_html=email_data["body_html"],
            attachment_path=config.RESUME_PATH,
        )

        if success:
            db.update_email_status(job_id, "sent")
            db.log_email(job_id, "application", hr_email, "sent")
            _tracking_upsert(
                dict(job),
                actual_title,
                application_email_sent="Y",
                hr_email=hr_email,
            )
            print("     ✅ Sent!")
            sent_count += 1
        else:
            db.log_email(job_id, "application", hr_email, "failed")
            print("     ❌ Failed")
            failed += 1

        time.sleep(2)

    if failed:
        print(f"\n  ⚠️  {failed} message(s) failed; those rows stay pending — fix errors and run again.")
    return sent_count


# ─── Follow-up emails ──────────────────────────────────────────────────────────

def send_followups(db: Database, dry_run: bool = False) -> int:
    """Send one follow-up per due job row. Skips URLs marked isFollowed / follow-up sent on the tracking sheet."""
    due = db.get_pending_followups()

    if not due:
        print("  No follow-ups due right now.")
        return 0

    jt = None
    try:
        import job_tracking as jt
    except Exception:
        jt = None

    if jt is not None:
        fu_skip = jt.load_followup_skip_urls()
        kept = []
        skipped = 0
        for j in due:
            u = jt.normalize_job_url(j.get("job_url") or "")
            if u and u in fu_skip:
                skipped += 1
                continue
            kept.append(j)
        due = kept
        if skipped:
            print(
                f"\n  ⏭️  Skipped {skipped} row(s): tracking sheet has isFollowed / follow-up already marked."
            )

    if not due:
        print("  No follow-ups left to send after tracking-sheet rules.")
        return 0

    print(f"\n📬 Sending {len(due)} follow-up email(s)…\n")
    sent_count = 0

    for idx, job in enumerate(due, start=1):
        company = job["company"]
        hr_email = job["hr_email"]
        hr_name = job.get("hr_name", "")
        job_id = job["id"]
        job_title = job["job_title"]

        email_data = templates.followup_email(job_title, company, hr_name)

        print(f"  [{idx}/{len(due)}] {company[:40]:<42} {hr_email}")

        if dry_run:
            print(f"     [DRY RUN] Would send follow-up: {email_data['subject']}")
            sent_count += 1
            continue

        success = _send_email(
            to_email=hr_email,
            subject=email_data["subject"],
            body_text=email_data["body_text"],
            body_html=email_data["body_html"],
        )

        if success:
            db.mark_followup_sent(job_id)
            db.log_email(job_id, "followup", hr_email, "sent")
            _tracking_upsert(
                dict(job),
                job_title,
                followup_sent="Y",
                hr_email=hr_email,
            )
            print("     ✅ Follow-up sent!")
            sent_count += 1
        else:
            db.log_email(job_id, "followup", hr_email, "failed")
            print("     ❌ Failed")

        time.sleep(2)

    return sent_count
