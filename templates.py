"""
Email Templates — Application email and follow-up email.
Fully customizable: just edit the strings below.
"""

import config


def application_email(job_title: str, company: str, hr_name: str = "") -> dict:
    """
    Returns { subject, body_text, body_html } for the initial application email.
    """
    greeting = f"Dear {hr_name}," if hr_name else "Dear Hiring Manager,"

    subject = f"Application for {job_title} Position – {config.YOUR_NAME}"

    body_text = f"""\
{greeting}

I hope this message finds you well. I am writing to express my strong interest in the {job_title} role at {company}. With {config.YOUR_EXPERIENCE}+ years of hands-on experience, I am confident in my ability to contribute meaningfully to your team from day one.

Please find my resume attached for your review. I would love the opportunity to discuss how my background aligns with your requirements.

A few highlights from my profile:
  • {config.YOUR_EXPERIENCE}+ years of relevant industry experience
  • Strong problem-solving and collaboration skills
  • Eager to learn and grow within a dynamic team environment

I am available for a call or interview at your convenience. Please feel free to reach me at {config.YOUR_PHONE} or reply to this email.

Thank you for considering my application. I look forward to hearing from you.

Warm regards,
{config.YOUR_NAME}
{config.YOUR_EMAIL}
{config.YOUR_PHONE}
LinkedIn: {config.YOUR_LINKEDIN}
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
    .signature {{ margin-top: 24px; border-top: 1px solid #eee; padding-top: 12px; color: #555; font-size: 13px; text-align: left; }}
    p {{ margin: 0 0 12px 0; text-align: left; }}
    ul {{ margin: 0 0 12px 0; padding-left: 22px; text-align: left; }}
    li {{ margin-bottom: 6px; text-align: left; }}
    a {{ color: #0077b5; text-decoration: none; }}
  </style>
</head>
<body style="margin:0;padding:0;text-align:left;">
<div class="container" style="text-align:left;">
  <p>{greeting}</p>

  <p>I hope this message finds you well. I am writing to express my strong interest in the
  <strong>{job_title}</strong> role at <strong>{company}</strong>. With {config.YOUR_EXPERIENCE}+ years
  of hands-on experience, I am confident in my ability to contribute meaningfully to your team from day one.</p>

  <p>Please find my resume attached for your review. I would love the opportunity to discuss how my
  background aligns with your requirements.</p>

  <p><strong>A few highlights from my profile:</strong></p>
  <ul>
    <li>{config.YOUR_EXPERIENCE}+ years of relevant industry experience</li>
    <li>Strong problem-solving and collaboration skills</li>
    <li>Eager to learn and grow within a dynamic team environment</li>
  </ul>

  <p>I am available for a call or interview at your convenience. Please feel free to reach me at
  <strong>{config.YOUR_PHONE}</strong> or reply to this email.</p>

  <p>Thank you for considering my application. I look forward to hearing from you.</p>

  <div class="signature">
    <strong>{config.YOUR_NAME}</strong><br>
    📧 {config.YOUR_EMAIL}<br>
    📞 {config.YOUR_PHONE}<br>
    🔗 <a href="{config.YOUR_LINKEDIN}">LinkedIn Profile</a>
  </div>
</div>
</body>
</html>
"""
    return {"subject": subject, "body_text": body_text, "body_html": body_html}


def followup_email(job_title: str, company: str, hr_name: str = "") -> dict:
    """
    Returns { subject, body_text, body_html } for the follow-up email.
    """
    greeting = f"Dear {hr_name}," if hr_name else "Dear Hiring Manager,"

    subject = f"Follow-Up: {job_title} Application – {config.YOUR_NAME}"

    body_text = f"""\
{greeting}

I hope you're doing well! I wanted to follow up on the application I submitted for the {job_title} position at {company} a few days ago.

I remain very enthusiastic about this opportunity and would love the chance to discuss how I can contribute to your team. Please let me know if there is any additional information I can provide to assist with your review.

I am happy to hop on a call at a time that works best for you.

Thank you so much for your time and consideration.

Warm regards,
{config.YOUR_NAME}
{config.YOUR_EMAIL}
{config.YOUR_PHONE}
LinkedIn: {config.YOUR_LINKEDIN}
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
    .signature {{ margin-top: 24px; border-top: 1px solid #eee; padding-top: 12px; color: #555; font-size: 13px; text-align: left; }}
    p {{ margin: 0 0 12px 0; text-align: left; }}
    a {{ color: #0077b5; text-decoration: none; }}
  </style>
</head>
<body style="margin:0;padding:0;text-align:left;">
<div class="container" style="text-align:left;">
  <p>{greeting}</p>

  <p>I hope you're doing well! I wanted to follow up on the application I submitted for the
  <strong>{job_title}</strong> position at <strong>{company}</strong> a few days ago.</p>

  <p>I remain very enthusiastic about this opportunity and would love the chance to discuss how I can
  contribute to your team. Please let me know if there is any additional information I can provide to
  assist with your review.</p>

  <p>I am happy to hop on a call at a time that works best for you.</p>

  <p>Thank you so much for your time and consideration.</p>

  <div class="signature">
    <strong>{config.YOUR_NAME}</strong><br>
    📧 {config.YOUR_EMAIL}<br>
    📞 {config.YOUR_PHONE}<br>
    🔗 <a href="{config.YOUR_LINKEDIN}">LinkedIn Profile</a>
  </div>
</div>
</body>
</html>
"""
    return {"subject": subject, "body_text": body_text, "body_html": body_html}
