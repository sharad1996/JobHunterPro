"""
Email Templates — role-aware application & follow-up emails.

Each email tailors itself to the JOB TITLE (the only role signal that reaches us):
  • the opening line names the role + company,
  • the highlighted bullets are the achievements whose keywords match the title,
  • the surfaced skills are the ones from your profile that match the title.

Tune the wording here; tune WHAT gets said (skills / achievements) in config.py.
"""

import re

import config


def _tokens(text: str) -> set:
    """Lowercase word/skill tokens from a string (keeps + . # for c++, node.js, c#)."""
    return set(re.findall(r"[a-z0-9][a-z0-9\+\.#-]*", (text or "").lower()))


def _matching_skills(job_title: str, limit: int = 6) -> list:
    """Skills from config.YOUR_SKILLS whose tokens appear in the job title."""
    title_toks = _tokens(job_title)
    matched = [s for s in config.YOUR_SKILLS if _tokens(s) & title_toks]
    return matched[:limit]


def _relevant_achievements(job_title: str, count: int = 3) -> list:
    """Top achievements by keyword overlap with the title; falls back to defaults."""
    title_toks = _tokens(job_title)
    scored = []
    for ach in config.ACHIEVEMENTS:
        score = sum(1 for kw in ach["keywords"] if kw in title_toks)
        if score:
            scored.append((score, ach["text"]))
    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [text for _, text in scored[:count]]
    if len(picked) < count:
        # Top up with defaults we haven't already used.
        for text in config.DEFAULT_ACHIEVEMENTS:
            if text not in picked:
                picked.append(text)
            if len(picked) >= count:
                break
    return picked[:count]


def _greeting(hr_name: str) -> str:
    """Use the recipient's first name when we have it, else a neutral opener."""
    first = (hr_name or "").strip().split()[0] if (hr_name or "").strip() else ""
    return f"Hi {first}," if first else "Hello,"


def _skills_clause(job_title: str) -> str:
    """A short 'my X, Y, Z line up with this role' clause, or '' if no match."""
    skills = _matching_skills(job_title)
    if not skills:
        return ""
    if len(skills) == 1:
        joined = skills[0]
    elif len(skills) == 2:
        joined = f"{skills[0]} and {skills[1]}"
    else:
        joined = ", ".join(skills[:-1]) + f", and {skills[-1]}"
    return f"My work with {joined} lines up closely with what you're hiring for."


def _portfolio_text_line() -> str:
    return f"Portfolio / code: {config.YOUR_PORTFOLIO}\n" if config.YOUR_PORTFOLIO else ""


def application_email(job_title: str, company: str, hr_name: str = "") -> dict:
    """
    Returns { subject, body_text, body_html } for the initial application email,
    tailored to `job_title`.
    """
    greeting = _greeting(hr_name)
    achievements = _relevant_achievements(job_title)
    skills_clause = _skills_clause(job_title)

    subject = f"Application: {job_title} — {config.YOUR_NAME} ({config.YOUR_EXPERIENCE}+ yrs)"

    intro = (
        f"I'm applying for the {job_title} role at {company}. I'm a "
        f"{config.YOUR_HEADLINE.lower()} with {config.YOUR_EXPERIENCE}+ years shipping "
        f"production web applications."
    )
    if skills_clause:
        intro += " " + skills_clause

    bullets_text = "\n".join(f"  • {a}" for a in achievements)

    body_text = f"""\
{greeting}

{intro}

A few relevant things I've done:
{bullets_text}

My resume is attached. I'd welcome a short call to see if it's a fit — you can reach me at {config.YOUR_PHONE} or reply here.
{_portfolio_text_line()}
Thanks for your time,
{config.YOUR_NAME}
{config.YOUR_EMAIL} · {config.YOUR_PHONE}
LinkedIn: {config.YOUR_LINKEDIN}
"""

    bullets_html = "\n".join(f"    <li>{a}</li>" for a in achievements)
    portfolio_html = (
        f'    🔗 <a href="{config.YOUR_PORTFOLIO}">{config.YOUR_PORTFOLIO}</a><br>\n'
        if config.YOUR_PORTFOLIO
        else ""
    )

    body_html = f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    html, body {{ margin: 0; padding: 0; text-align: left; direction: ltr; }}
    body {{ font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #333; line-height: 1.6; }}
    .container {{ max-width: 100%; margin: 0; padding: 0; text-align: left; }}
    .signature {{ margin-top: 20px; border-top: 1px solid #eee; padding-top: 10px; color: #555; font-size: 13px; }}
    p {{ margin: 0 0 12px 0; }}
    ul {{ margin: 0 0 12px 0; padding-left: 22px; }}
    li {{ margin-bottom: 6px; }}
    a {{ color: #0077b5; text-decoration: none; }}
  </style>
</head>
<body style="margin:0;padding:0;text-align:left;">
<div class="container">
  <p>{greeting}</p>

  <p>{intro}</p>

  <p><strong>A few relevant things I've done:</strong></p>
  <ul>
{bullets_html}
  </ul>

  <p>My resume is attached. I'd welcome a short call to see if it's a fit — you can reach me at
  <strong>{config.YOUR_PHONE}</strong> or reply to this email.</p>

  <div class="signature">
    <strong>{config.YOUR_NAME}</strong><br>
    {config.YOUR_EMAIL} · {config.YOUR_PHONE}<br>
{portfolio_html}    <a href="{config.YOUR_LINKEDIN}">LinkedIn</a>
  </div>
</div>
</body>
</html>
"""
    return {"subject": subject, "body_text": body_text, "body_html": body_html}


def followup_email(job_title: str, company: str, hr_name: str = "") -> dict:
    """
    Returns { subject, body_text, body_html } for a short, non-pushy follow-up.
    """
    greeting = _greeting(hr_name)
    skills_clause = _skills_clause(job_title)
    nudge = (
        f" {skills_clause}"
        if skills_clause
        else " I'd still love the chance to show how I can contribute."
    )

    subject = f"Re: {job_title} application — {config.YOUR_NAME}"

    body_text = f"""\
{greeting}

Following up on my application for the {job_title} role at {company}.{nudge}

Happy to share more detail or hop on a quick call whenever it's convenient. If the role is filled, a quick note is appreciated so I can plan accordingly.

Thanks again,
{config.YOUR_NAME}
{config.YOUR_EMAIL} · {config.YOUR_PHONE}
"""

    body_html = f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    html, body {{ margin: 0; padding: 0; text-align: left; direction: ltr; }}
    body {{ font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #333; line-height: 1.6; }}
    .container {{ max-width: 100%; margin: 0; padding: 0; text-align: left; }}
    .signature {{ margin-top: 20px; border-top: 1px solid #eee; padding-top: 10px; color: #555; font-size: 13px; }}
    p {{ margin: 0 0 12px 0; }}
    a {{ color: #0077b5; text-decoration: none; }}
  </style>
</head>
<body style="margin:0;padding:0;text-align:left;">
<div class="container">
  <p>{greeting}</p>

  <p>Following up on my application for the <strong>{job_title}</strong> role at
  <strong>{company}</strong>.{nudge}</p>

  <p>Happy to share more detail or hop on a quick call whenever it's convenient. If the role is
  already filled, a quick note is appreciated so I can plan accordingly.</p>

  <div class="signature">
    <strong>{config.YOUR_NAME}</strong><br>
    {config.YOUR_EMAIL} · {config.YOUR_PHONE}<br>
    <a href="{config.YOUR_LINKEDIN}">LinkedIn</a>
  </div>
</div>
</body>
</html>
"""
    return {"subject": subject, "body_text": body_text, "body_html": body_html}
