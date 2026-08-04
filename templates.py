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


def _relevant_achievements(job_title: str, count: int = 2) -> list:
    """
    Achievements whose keywords actually overlap the title, best match first.

    Deliberately returns FEWER than `count` — or nothing at all — rather than padding with
    config.DEFAULT_ACHIEVEMENTS. Generic bullets ("7+ years of relevant industry experience")
    are the clearest signal of a mass-mailed application, so an unmatched role gets no bullet
    list; an email with two specific claims beats one with two specific claims and a filler.
    An empty return means the role is a poor fit and is worth not sending at all.
    """
    title_toks = _tokens(job_title)
    scored = []
    for ach in config.ACHIEVEMENTS:
        score = sum(1 for kw in ach["keywords"] if kw in title_toks)
        if score:
            scored.append((score, ach["text"]))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in scored[:count]]


def _greeting(hr_name: str) -> str:
    """Use the recipient's first name when we have it, else a neutral opener."""
    first = (hr_name or "").strip().split()[0] if (hr_name or "").strip() else ""
    return f"Hi {first}," if first else "Hello,"


def _stack_tag(job_title: str) -> str:
    """
    Short 'React/Next.js' tag for the subject line.

    Uses role-matched skills only when TWO of them match — one lone match reads thin
    ("React, 7 yrs"), and a single weak match reads bizarre (a CRO role matching
    "performance optimization"). Otherwise falls back to your headline's parenthetical,
    which is a stable statement of specialty rather than an artifact of keyword overlap.
    """
    skills = _matching_skills(job_title, limit=2)
    if len(skills) < 2:
        # "Full-Stack Engineer (React · Next.js · Node.js)" → "React/Next.js"
        inner = re.search(r"\(([^)]*)\)", config.YOUR_HEADLINE or "")
        if not inner:
            return "/".join(skills)
        parts = [p.strip() for p in re.split(r"[·,/]", inner.group(1)) if p.strip()]
        skills = parts[:2]
    return "/".join(skills)


def _pitch() -> str:
    """The one-line pitch. Hand-written in config; never case-mangled."""
    pitch = (getattr(config, "YOUR_PITCH", "") or "").strip()
    if pitch:
        return pitch
    return (
        f"{config.YOUR_EXPERIENCE}+ years shipping production web applications as a "
        f"{config.YOUR_HEADLINE}."
    )


def _availability() -> str:
    return (getattr(config, "AVAILABILITY_LINE", "") or "").strip()


def _portfolio_text_line() -> str:
    return f"Code: {config.YOUR_PORTFOLIO}\n" if config.YOUR_PORTFOLIO else ""


def application_email(job_title: str, company: str, hr_name: str = "") -> dict:
    """
    Returns { subject, body_text, body_html } for the initial application email,
    tailored to `job_title`.
    """
    greeting = _greeting(hr_name)
    achievements = _relevant_achievements(job_title)
    stack = _stack_tag(job_title)

    # Role first — recruiters scan a full inbox by role, and a leading "Application:" wastes
    # the scannable prefix. The stack tag is the differentiator, not the years.
    tag = f" ({stack}, {config.YOUR_EXPERIENCE} yrs)" if stack else ""
    subject = f"{job_title} — {config.YOUR_NAME}{tag}"

    opener = f"Applying for the {job_title} role at {company}."

    # Only written when something genuinely matched — see _relevant_achievements.
    lead_in = (
        "The two most relevant pieces:" if len(achievements) > 1 else "Most relevant:"
    )

    blocks_text = [greeting, "", opener, "", _pitch()]
    if achievements:
        blocks_text += ["", lead_in, ""]
        blocks_text += [f"  • {a}" for a in achievements]
    if _availability():
        blocks_text += ["", _availability()]
    blocks_text += [
        "",
        "Resume attached. Happy to take a short take-home if that's a faster read than a call.",
        "",
    ]
    if _portfolio_text_line():
        blocks_text.append(_portfolio_text_line().rstrip("\n"))
    blocks_text += [
        config.YOUR_NAME,
        f"{config.YOUR_EMAIL} · {config.YOUR_LINKEDIN}",
    ]
    body_text = "\n".join(blocks_text) + "\n"

    bullets_html = "\n".join(f"    <li>{a}</li>" for a in achievements)
    achievements_html = (
        f"  <p>{lead_in}</p>\n  <ul>\n{bullets_html}\n  </ul>\n" if achievements else ""
    )
    availability_html = f"  <p>{_availability()}</p>\n" if _availability() else ""
    portfolio_html = (
        f'    <a href="{config.YOUR_PORTFOLIO}">{config.YOUR_PORTFOLIO}</a><br>\n'
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

  <p>{opener}</p>

  <p>{_pitch()}</p>

{achievements_html}{availability_html}  <p>Resume attached. Happy to take a short take-home if that's a faster read than a call.</p>

  <div class="signature">
    <strong>{config.YOUR_NAME}</strong><br>
    {config.YOUR_EMAIL}<br>
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

    subject = f"Re: {job_title} application — {config.YOUR_NAME}"

    # One job: make replying cheaper than ignoring. No re-pitch, no enthusiasm padding —
    # a second email that restates the first is the one that gets filtered.
    body_text = f"""\
{greeting}

Following up on my application for the {job_title} role at {company}.

Still interested. If it's filled or I'm not the right fit, a one-line reply is all I need — I'll stop chasing.

{config.YOUR_NAME}
{config.YOUR_EMAIL} · {config.YOUR_LINKEDIN}
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
  <strong>{company}</strong>.</p>

  <p>Still interested. If it's filled or I'm not the right fit, a one-line reply is all I
  need — I'll stop chasing.</p>

  <div class="signature">
    <strong>{config.YOUR_NAME}</strong><br>
    {config.YOUR_EMAIL}<br>
    <a href="{config.YOUR_LINKEDIN}">LinkedIn</a>
  </div>
</div>
</body>
</html>
"""
    return {"subject": subject, "body_text": body_text, "body_html": body_html}
