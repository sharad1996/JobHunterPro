"""Unit tests for community_boards — HN comment parsing (no network)."""

import unittest

import community_boards as cb

# Real-shaped HN comment HTML: entity-escaped, <p> separated, link in an <a href>.
REAL_COMMENT = (
    "SmarterDx | Senior Full-Stack Engineer | Remote (US only) | 150-250k + equity | "
    '<a href="https:&#x2F;&#x2F;smarterdx.com&#x2F;careers" rel="nofollow">'
    "https:&#x2F;&#x2F;smarterdx.com&#x2F;careers</a>"
    "<p>SmarterDx builds clinical AI. We&#x27;re hiring React and Node engineers."
)


class TestStripHtml(unittest.TestCase):
    def test_unescapes_entities_and_breaks_paragraphs(self):
        out = cb._strip_html("A&#x27;s <p>second line &amp; more")
        self.assertIn("A's", out)
        self.assertIn("second line & more", out)
        self.assertEqual(len(out.split("\n")), 2)

    def test_empty_input(self):
        self.assertEqual(cb._strip_html(""), "")
        self.assertEqual(cb._strip_html(None), "")


class TestFirstUrl(unittest.TestCase):
    def test_prefers_href_and_unescapes(self):
        url = cb._first_url(REAL_COMMENT, cb._strip_html(REAL_COMMENT))
        self.assertEqual(url, "https://smarterdx.com/careers")

    def test_skips_internal_hn_links(self):
        raw = '<a href="https://news.ycombinator.com/item?id=1">x</a> <a href="https://real.co">y</a>'
        self.assertEqual(cb._first_url(raw, cb._strip_html(raw)), "https://real.co")

    def test_falls_back_to_bare_url_in_text(self):
        plain = "Acme | Engineer | Remote | apply at https://acme.io/jobs."
        self.assertEqual(cb._first_url("", plain), "https://acme.io/jobs")


class TestParseHnComment(unittest.TestCase):
    def test_parses_real_shaped_comment(self):
        job = cb.parse_hn_comment(REAL_COMMENT, "React")
        self.assertIsNotNone(job)
        self.assertEqual(job["company"], "SmarterDx")
        self.assertEqual(job["title"], "Senior Full-Stack Engineer")
        self.assertEqual(job["search_country"], "Remote (US only)")
        self.assertEqual(job["url"], "https://smarterdx.com/careers")
        self.assertEqual(job["platform"], "HN Who Is Hiring")

    def test_keyword_gate_matches_body_not_just_header(self):
        """Roles are often only in the body, so the gate runs over the whole posting."""
        self.assertIsNotNone(cb.parse_hn_comment(REAL_COMMENT, "Node"))

    def test_keyword_mismatch_rejected(self):
        self.assertIsNone(cb.parse_hn_comment(REAL_COMMENT, "Kubernetes"))

    def test_comment_without_url_rejected(self):
        raw = "Acme Inc | Backend Engineer | Remote | email us"
        self.assertIsNone(cb.parse_hn_comment(raw, "Backend"))

    def test_discussion_prose_rejected(self):
        raw = (
            "I have built something very similar a couple of times before and would be "
            "happy to chat about the payment models. "
            '<a href="https://example.com">link</a>'
        )
        self.assertIsNone(cb.parse_hn_comment(raw, "Engineer"))

    def test_empty_comment_rejected(self):
        self.assertIsNone(cb.parse_hn_comment("", "React"))
        self.assertIsNone(cb.parse_hn_comment(None, "React"))

    def test_header_starting_with_remote_rejected_as_company(self):
        raw = 'REMOTE | React Engineer | <a href="https://x.co">x</a>'
        self.assertIsNone(cb.parse_hn_comment(raw, "React"))

    def test_missing_role_falls_back_to_search_term(self):
        raw = 'Tinyco | Berlin | <a href="https://tinyco.de/jobs">apply</a> React work'
        job = cb.parse_hn_comment(raw, "React Developer")
        self.assertIsNotNone(job)
        self.assertEqual(job["company"], "Tinyco")
        self.assertEqual(job["title"], "React Developer")

    def test_title_is_length_capped(self):
        raw = f'Acme | Senior {"Engineer " * 40} | <a href="https://a.co">x</a>'
        job = cb.parse_hn_comment(raw, "Engineer")
        self.assertLessEqual(len(job["title"]), 150)

    def test_absurdly_long_company_rejected(self):
        raw = f'{"x" * 200} | Engineer | <a href="https://a.co">y</a>'
        self.assertIsNone(cb.parse_hn_comment(raw, "Engineer"))

    def test_url_glued_to_company_is_stripped(self):
        """Regression: 'Snout https://snout.com/ | Role' yielded company 'Snout https://snout.com/'."""
        raw = (
            'Snout <a href="https:&#x2F;&#x2F;snout.com&#x2F;" rel="nofollow">'
            "https:&#x2F;&#x2F;snout.com&#x2F;</a> | React Developer | Remote"
        )
        job = cb.parse_hn_comment(raw, "React")
        self.assertEqual(job["company"], "Snout")
        self.assertEqual(job["url"], "https://snout.com/")

    def test_email_in_company_segment_is_stripped(self):
        raw = 'Acme jobs@acme.io | React Engineer | <a href="https://acme.io">x</a>'
        job = cb.parse_hn_comment(raw, "React")
        self.assertEqual(job["company"], "Acme")


class TestCleanSegment(unittest.TestCase):
    def test_strips_urls_and_bare_www(self):
        self.assertEqual(cb._clean_segment("Snout https://snout.com/"), "Snout")
        self.assertEqual(cb._clean_segment("Acme www.acme.io"), "Acme")

    def test_strips_decorative_punctuation(self):
        self.assertEqual(cb._clean_segment("  — Acme Inc, "), "Acme Inc")


if __name__ == "__main__":
    unittest.main()
