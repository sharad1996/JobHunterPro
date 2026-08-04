"""
Template copy guarantees.

These lock the two failures that made outreach read as mass mail:
  • the headline was lowercased, so every email said "react · next.js · node.js"
  • unmatched roles were topped up with generic filler bullets
"""

import config
import templates


REACT_TITLE = "Senior React Developer"
OFF_TOPIC_TITLE = "Senior CRO Manager Growth Optimization Lead"

HEDGES = (
    "i hope this message finds you well",
    "i hope you're doing well",
    "i am writing to express",
    "i am confident",
    "i would love the opportunity",
    "i look forward to hearing from you",
    "eager to learn",
    "warm regards",
    "dear hiring manager",
)


def _both_bodies(email: dict) -> list:
    return [email["body_text"], email["body_html"]]


def test_headline_keeps_its_capitalisation():
    """React must never appear as 'react' — lowercasing is an automation tell."""
    email = templates.application_email(REACT_TITLE, "Acme")
    for body in _both_bodies(email):
        assert "react ·" not in body
        assert "next.js · node.js" not in body.replace("Next.js · Node.js", "")


def test_no_filler_bullets_for_an_unmatched_role():
    """An off-topic title gets no bullets rather than generic DEFAULT_ACHIEVEMENTS padding."""
    assert templates._relevant_achievements(OFF_TOPIC_TITLE) == [], (
        "title unexpectedly matches an achievement — pick a title with no keyword overlap"
    )
    email = templates.application_email(OFF_TOPIC_TITLE, "Acme")
    for body in _both_bodies(email):
        for filler in config.DEFAULT_ACHIEVEMENTS:
            assert filler not in body, f"filler bullet leaked: {filler!r}"
    assert "<li>" not in email["body_html"]


def test_at_most_two_bullets():
    email = templates.application_email(REACT_TITLE, "Acme")
    assert email["body_text"].count("\n  • ") <= 2
    assert email["body_html"].count("<li>") <= 2


def test_no_hedging_phrases_in_either_email():
    for email in (
        templates.application_email(REACT_TITLE, "Acme", "Priya"),
        templates.followup_email(REACT_TITLE, "Acme", "Priya"),
    ):
        for body in _both_bodies(email):
            low = body.lower()
            for hedge in HEDGES:
                assert hedge not in low, f"hedge {hedge!r} still present"


def test_subject_leads_with_the_role():
    subject = templates.application_email(REACT_TITLE, "Acme")["subject"]
    assert subject.startswith(REACT_TITLE)
    assert config.YOUR_NAME in subject


def test_subject_stack_tag_never_reads_thin_or_bizarre():
    """A single weak keyword match must not become the subject's differentiator."""
    off_topic = templates.application_email(OFF_TOPIC_TITLE, "Acme")["subject"]
    assert "performance optimization" not in off_topic
    # One lone match ("React") falls back to the headline's stated specialty.
    assert "(React/Next.js" in templates.application_email(REACT_TITLE, "Acme")["subject"]


def test_greeting_uses_first_name_when_known():
    email = templates.application_email(REACT_TITLE, "Acme", "Priya Sharma")
    assert "Hi Priya," in email["body_text"]
    assert "Hi Priya," in email["body_html"]


def test_phone_not_in_body_copy():
    """Phone belongs in a signature, not mid-pitch on a remote role."""
    body = templates.application_email(REACT_TITLE, "Acme")["body_text"]
    pitch = body.split("Resume attached")[0]
    assert config.YOUR_PHONE not in pitch


def test_availability_line_present():
    email = templates.application_email(REACT_TITLE, "Acme")
    for body in _both_bodies(email):
        assert "core hours" in body


def test_portfolio_omitted_when_unset(monkeypatch):
    monkeypatch.setattr(config, "YOUR_PORTFOLIO", "")
    email = templates.application_email(REACT_TITLE, "Acme")
    assert "Portfolio" not in email["body_text"]
    assert "href=\"\"" not in email["body_html"]


def test_portfolio_included_when_set(monkeypatch):
    monkeypatch.setattr(config, "YOUR_PORTFOLIO", "https://github.com/sharad")
    email = templates.application_email(REACT_TITLE, "Acme")
    assert "https://github.com/sharad" in email["body_text"]
    assert "https://github.com/sharad" in email["body_html"]
