"""
Integration tests for the point of the whole feature: the slow HR-email lookup must not
run for jobs we already emailed, or for companies whose address we already know.

Each test asserts on the *call count* of find_hr_email_for_company — the expensive call.
"""

import unittest
from unittest.mock import patch

import config
import email_finder
import main
import outreach_history as oh


def _hist(*rows):
    return oh.OutreachHistory.from_rows(list(rows))


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


def _job(company, title="React Developer", url=None):
    return {
        "company": company,
        "title": title,
        "url": url or f"https://example.com/{company.lower().replace(' ', '-')}",
        "platform": "Test",
        "domain": "",
    }


FOUND = {"hr_email": "found@x.com", "hr_email_verified": True, "domain": "x.com"}


class TestBatchSelectionSkipsLookup(unittest.TestCase):
    @patch.object(email_finder, "find_hr_email_for_company", return_value=dict(FOUND))
    def test_already_emailed_job_never_triggers_lookup(self, mock_find):
        history = _hist(_row("Acme Corp", "React Developer"))
        selected = main._select_jobs_for_batch(
            [_job("Acme Corp")], set(), 5, history=history, search_title="React Developer"
        )
        self.assertEqual(selected, [])
        mock_find.assert_not_called()

    @patch.object(email_finder, "find_hr_email_for_company", return_value=dict(FOUND))
    def test_new_company_still_triggers_lookup(self, mock_find):
        history = _hist(_row("Acme Corp", "React Developer"))
        selected = main._select_jobs_for_batch(
            [_job("Fresh Co")], set(), 5, history=history, search_title="React Developer"
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(mock_find.call_count, 1)

    @patch.object(email_finder, "find_hr_email_for_company", return_value=dict(FOUND))
    def test_known_address_reused_without_lookup(self, mock_find):
        history = _hist(
            _row(
                "Known Co",
                "Some Other Role",
                hr_email="cached@known.com",
                hr_email_verified=1,
                company_domain="known.com",
                email_status="pending",
            )
        )
        selected = main._select_jobs_for_batch(
            [_job("Known Co")], set(), 5, history=history, search_title="React Developer"
        )
        mock_find.assert_not_called()
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["hr_email"], "cached@known.com")
        self.assertEqual(selected[0]["domain"], "known.com")

    @patch.object(email_finder, "find_hr_email_for_company", return_value=dict(FOUND))
    def test_matches_on_listing_title_not_just_search_term(self, mock_find):
        """DB rows synced from Excel store the listing's own title, not the search term."""
        history = _hist(_row("Acme Corp", "Senior React Engineer"))
        selected = main._select_jobs_for_batch(
            [_job("Acme Corp", title="Senior React Engineer")],
            set(),
            5,
            history=history,
            search_title="React Developer",
        )
        self.assertEqual(selected, [])
        mock_find.assert_not_called()

    @patch.object(email_finder, "find_hr_email_for_company", return_value=dict(FOUND))
    def test_company_name_variants_still_skip(self, mock_find):
        history = _hist(_row("Acme Corp.", "React Developer"))
        selected = main._select_jobs_for_batch(
            [_job("ACME Inc")], set(), 5, history=history, search_title="react developer"
        )
        self.assertEqual(selected, [])
        mock_find.assert_not_called()

    @patch.object(email_finder, "find_hr_email_for_company", return_value=dict(FOUND))
    def test_no_history_preserves_old_behaviour(self, mock_find):
        selected = main._select_jobs_for_batch([_job("Anyone")], set(), 5)
        self.assertEqual(len(selected), 1)
        self.assertEqual(mock_find.call_count, 1)

    @patch.object(email_finder, "find_hr_email_for_company", return_value=dict(FOUND))
    def test_mixed_batch_only_looks_up_the_unknown(self, mock_find):
        history = _hist(
            _row("Emailed Co", "React Developer"),
            _row("Cached Co", "Other", hr_email="c@cached.com", hr_email_verified=1),
        )
        selected = main._select_jobs_for_batch(
            [_job("Emailed Co"), _job("Cached Co"), _job("New Co")],
            set(),
            5,
            history=history,
            search_title="React Developer",
        )
        # Emailed Co dropped, Cached Co reused, only New Co pays for a lookup.
        self.assertEqual(mock_find.call_count, 1)
        self.assertEqual([j["company"] for j in selected], ["Cached Co", "New Co"])

    @patch.object(email_finder, "find_hr_email_for_company", return_value=dict(FOUND))
    def test_url_skip_list_still_honoured(self, mock_find):
        import job_tracking

        job = _job("Acme Corp")
        skip = {job_tracking.normalize_job_url(job["url"])}
        selected = main._select_jobs_for_batch(
            [job], skip, 5, history=_hist(), search_title="React Developer"
        )
        self.assertEqual(selected, [])
        mock_find.assert_not_called()

    @patch.object(config, "SKIP_ALREADY_EMAILED_ANY_ROLE", True)
    @patch.object(email_finder, "find_hr_email_for_company", return_value=dict(FOUND))
    def test_any_role_mode_skips_different_role_at_known_company(self, mock_find):
        history = _hist(_row("Acme Corp", "React Developer"))
        selected = main._select_jobs_for_batch(
            [_job("Acme Corp", title="DevOps Engineer")],
            set(),
            5,
            history=history,
            search_title="DevOps Engineer",
        )
        self.assertEqual(selected, [])
        mock_find.assert_not_called()


class TestFindHrEmailsReuse(unittest.TestCase):
    @patch.object(email_finder, "find_hr_email_for_company", return_value=dict(FOUND))
    def test_bulk_path_reuses_known_address(self, mock_find):
        history = _hist(
            _row("Known Co", "X", hr_email="cached@known.com", hr_email_verified=1),
        )
        out = email_finder.find_hr_emails([_job("Known Co")], history=history)
        mock_find.assert_not_called()
        self.assertEqual(out[0]["hr_email"], "cached@known.com")

    @patch.object(email_finder, "find_hr_email_for_company", return_value=dict(FOUND))
    def test_bulk_path_without_history_unchanged(self, mock_find):
        out = email_finder.find_hr_emails([_job("New Co")])
        self.assertEqual(mock_find.call_count, 1)
        self.assertEqual(out[0]["hr_email"], "found@x.com")

    @patch.object(email_finder, "find_hr_email_for_company", return_value={})
    def test_no_domain_candidates_does_not_raise_nameerror(self, mock_find):
        """Regression: `candidates` was referenced but never defined in this scope."""
        out = email_finder.find_hr_emails([_job("Nodomain Co")])
        self.assertEqual(out[0]["hr_email"], "")
        self.assertEqual(out[0]["domain"], "")

    @patch.object(
        email_finder,
        "find_hr_email_for_company",
        return_value={"domain_candidates": ["fallback.com"]},
    )
    def test_falls_back_to_first_domain_candidate(self, mock_find):
        out = email_finder.find_hr_emails([_job("Cand Co")])
        self.assertEqual(out[0]["domain"], "fallback.com")


if __name__ == "__main__":
    unittest.main()
