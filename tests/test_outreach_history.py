"""Unit tests for outreach_history — the already-emailed / known-email index."""

import unittest
from unittest.mock import patch

import config
import outreach_history as oh


def _row(company, job_title, **over):
    row = {
        "company": company,
        "job_title": job_title,
        "hr_email": "",
        "hr_name": "",
        "company_domain": "",
        "hr_email_verified": 0,
        "email_status": "sent",
    }
    row.update(over)
    return row


class TestNormalisation(unittest.TestCase):
    def test_company_case_and_punctuation_insensitive(self):
        self.assertEqual(oh.norm_company("Acme Corp."), oh.norm_company("acme corp"))
        self.assertEqual(oh.norm_company("Foo-Bar!"), oh.norm_company("foo bar"))

    def test_company_legal_suffixes_stripped(self):
        self.assertEqual(oh.norm_company("Acme Inc"), oh.norm_company("Acme"))
        self.assertEqual(oh.norm_company("Acme Pvt Ltd"), oh.norm_company("Acme"))
        self.assertEqual(oh.norm_company("Acme GmbH"), oh.norm_company("Acme"))

    def test_suffix_only_name_not_emptied(self):
        """'Co' alone must survive — stripping every token would collide everything."""
        self.assertEqual(oh.norm_company("Co"), "co")

    def test_stacked_legal_suffixes_stripped(self):
        self.assertEqual(oh.norm_company("Acme Private Limited"), oh.norm_company("Acme"))
        self.assertEqual(oh.norm_company("Acme Pvt Ltd"), oh.norm_company("Acme"))

    def test_descriptive_words_are_not_stripped(self):
        """Regression guard: these are brand words, not legal suffixes.

        Collapsing them would make two unrelated companies share a key and cause a false
        skip — losing a real application, which is far worse than a redundant lookup.
        """
        self.assertNotEqual(oh.norm_company("Tech Solutions"), oh.norm_company("Tech Systems"))
        self.assertNotEqual(oh.norm_company("Data Labs"), oh.norm_company("Data"))
        self.assertNotEqual(oh.norm_company("Acme Studio"), oh.norm_company("Acme Group"))
        self.assertEqual(oh.norm_company("Data Labs"), "data labs")

    def test_distinct_companies_do_not_collide_after_suffix_strip(self):
        h = oh.OutreachHistory.from_rows(
            [_row("Tech Solutions Inc", "React Developer", email_status="sent")]
        )
        self.assertTrue(h.already_emailed("Tech Solutions Ltd", "React Developer"))
        self.assertFalse(h.already_emailed("Tech Systems Ltd", "React Developer"))

    def test_title_normalised(self):
        self.assertEqual(oh.norm_title("Senior  React Developer!"), "senior react developer")
        self.assertEqual(oh.norm_title("Node.js / Backend"), "node js backend")

    def test_title_keeps_plus_and_hash(self):
        self.assertEqual(oh.norm_title("C++ / C# Dev"), "c++ c# dev")

    def test_empty_inputs(self):
        self.assertEqual(oh.norm_company(""), "")
        self.assertEqual(oh.norm_company(None), "")
        self.assertEqual(oh.norm_title(None), "")


class TestAlreadyEmailed(unittest.TestCase):
    def setUp(self):
        self.h = oh.OutreachHistory.from_rows(
            [
                _row("Acme Corp", "React Developer", email_status="sent"),
                _row("Beta Labs", "Node Developer", email_status="pending"),
            ]
        )

    def test_exact_pair_matches(self):
        self.assertTrue(self.h.already_emailed("Acme Corp", "React Developer"))

    def test_match_is_normalised(self):
        self.assertTrue(self.h.already_emailed("ACME  corp.", "react   developer"))
        self.assertTrue(self.h.already_emailed("Acme Inc", "React Developer"))

    def test_different_role_same_company_not_skipped(self):
        """A genuinely different role should still go out."""
        self.assertFalse(self.h.already_emailed("Acme Corp", "Backend Engineer"))

    def test_pending_row_does_not_block(self):
        """Only SENT counts — a pending row still needs its email sent."""
        self.assertFalse(self.h.already_emailed("Beta Labs", "Node Developer"))

    def test_unknown_company(self):
        self.assertFalse(self.h.already_emailed("Nobody", "React Developer"))

    def test_any_of_several_titles_matches(self):
        """Callers pass both the search term and the listing title."""
        self.assertTrue(
            self.h.already_emailed("Acme Corp", "Totally Different", "React Developer")
        )

    def test_blank_company_never_matches(self):
        self.assertFalse(self.h.already_emailed("", "React Developer"))

    @patch.object(config, "SKIP_ALREADY_EMAILED_ANY_ROLE", True)
    def test_any_role_mode_skips_whole_company(self):
        self.assertTrue(self.h.already_emailed("Acme Corp", "Backend Engineer"))

    @patch.object(config, "SKIP_ALREADY_EMAILED_ANY_ROLE", True)
    def test_any_role_mode_ignores_pending_company(self):
        self.assertFalse(self.h.already_emailed("Beta Labs", "Anything"))

    @patch.object(config, "SKIP_ALREADY_EMAILED_SAME_ROLE", False)
    def test_same_role_check_can_be_disabled(self):
        self.assertFalse(self.h.already_emailed("Acme Corp", "React Developer"))


class TestKnownEmail(unittest.TestCase):
    def setUp(self):
        self.h = oh.OutreachHistory.from_rows(
            [
                # NB: not acme.com / company.com — those are placeholder domains and are
                # deliberately screened out of the reuse path.
                _row(
                    "Acme Corp",
                    "React Developer",
                    hr_email="hr@acmecorp.io",
                    hr_name="Jane",
                    company_domain="acmecorp.io",
                    hr_email_verified=1,
                ),
                _row("Guessy Co", "X", hr_email="hr@guessyco.io", hr_email_verified=0),
            ]
        )

    def test_returns_verified_address(self):
        hit = self.h.known_email("Acme Corp")
        self.assertEqual(hit["hr_email"], "hr@acmecorp.io")
        self.assertEqual(hit["hr_name"], "Jane")
        self.assertEqual(hit["domain"], "acmecorp.io")
        self.assertTrue(hit["hr_email_verified"])

    def test_lookup_is_normalised(self):
        self.assertIsNotNone(self.h.known_email("acme inc"))

    def test_guessed_address_withheld_by_default(self):
        self.assertIsNone(self.h.known_email("Guessy Co"))

    @patch.object(config, "REUSE_ONLY_VERIFIED_COMPANY_EMAILS", False)
    def test_guessed_address_allowed_when_configured(self):
        self.assertEqual(self.h.known_email("Guessy Co")["hr_email"], "hr@guessyco.io")

    @patch.object(config, "REUSE_KNOWN_COMPANY_EMAILS", False)
    def test_reuse_can_be_disabled(self):
        self.assertIsNone(self.h.known_email("Acme Corp"))

    def test_unknown_company_returns_none(self):
        self.assertIsNone(self.h.known_email("Nobody"))

    def test_returned_dict_is_a_copy(self):
        """Callers mutate the result into the job dict; the index must not be corrupted."""
        self.h.known_email("Acme Corp")["hr_email"] = "tampered@x.com"
        self.assertEqual(self.h.known_email("Acme Corp")["hr_email"], "hr@acmecorp.io")

    def test_verified_row_wins_over_guessed_for_same_company(self):
        h = oh.OutreachHistory.from_rows(
            [
                _row("Dup Co", "A", hr_email="guess@dupco.io", hr_email_verified=0),
                _row("Dup Co", "B", hr_email="real@dupco.io", hr_email_verified=1),
            ]
        )
        self.assertEqual(h.known_email("Dup Co")["hr_email"], "real@dupco.io")

    def test_rows_without_email_are_not_indexed(self):
        h = oh.OutreachHistory.from_rows([_row("Empty Co", "A", hr_email="")])
        self.assertIsNone(h.known_email("Empty Co"))


class TestPlaceholderAddressesNotReplayed(unittest.TestCase):
    """The DB already holds placeholder addresses saved as 'verified' by older runs.

    Reusing them would keep a dead address alive forever instead of letting a fresh
    lookup find the real one.
    """

    def _known(self, email):
        h = oh.OutreachHistory.from_rows(
            [_row("Ghost Co", "A", hr_email=email, hr_email_verified=1)]
        )
        return h.known_email("Ghost Co")

    def test_documentation_names_rejected(self):
        for bad in (
            "john.doe@company.com",
            "jane.doe@acme.com",
            "john.smith@company.com",
            "fullname@company.com",
            "john@doe.com",
            "yourname@example.com",
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(self._known(bad), f"{bad} should not be replayed")

    def test_noreply_rejected(self):
        self.assertIsNone(self._known("noreply@realcompany.com"))

    def test_real_addresses_still_reused(self):
        for good in (
            "hr@realcompany.com",
            "careers@startup.io",
            "support@micro1.ai",
            "partnercontact@backblaze.com",
            "barbara@consulting.de",
            "foods@grocer.com",
            "sam.barnes@agency.co.uk",
        ):
            with self.subTest(good=good):
                hit = self._known(good)
                self.assertIsNotNone(hit, f"{good} should still be reusable")
                self.assertEqual(hit["hr_email"], good)


class TestRowAccess(unittest.TestCase):
    def test_sqlite_row_shape_supported(self):
        """from_rows must accept sqlite3.Row, which raises IndexError on missing keys."""
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE jobs (company TEXT, job_title TEXT, hr_email TEXT, hr_name TEXT,"
            " company_domain TEXT, hr_email_verified INT, email_status TEXT)"
        )
        conn.execute(
            "INSERT INTO jobs VALUES ('Acme','React Developer','hr@acmecorp.io','','acmecorp.io',1,'sent')"
        )
        rows = conn.execute("SELECT * FROM jobs").fetchall()
        h = oh.OutreachHistory.from_rows(rows)
        self.assertTrue(h.already_emailed("Acme", "React Developer"))
        self.assertIsNotNone(h.known_email("Acme"))

    def test_empty_and_none_input(self):
        self.assertEqual(oh.OutreachHistory.from_rows([]).rows_loaded, 0)
        self.assertEqual(oh.OutreachHistory.from_rows(None).rows_loaded, 0)

    def test_load_survives_broken_db(self):
        class Boom:
            def get_outreach_history_rows(self):
                raise RuntimeError("db gone")

        h = oh.OutreachHistory.load(Boom())
        self.assertEqual(h.rows_loaded, 0)
        self.assertFalse(h.already_emailed("Acme", "React Developer"))


if __name__ == "__main__":
    unittest.main()
