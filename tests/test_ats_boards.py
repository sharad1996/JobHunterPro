"""Unit tests for ats_boards — pure parsers and token extraction (no network)."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import ats_boards as ab
import config


def _iso_recent():
    """An ISO timestamp inside any sane posting window."""
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()


def _ms_recent():
    from datetime import datetime, timedelta, timezone

    dt = datetime.now(timezone.utc) - timedelta(days=2)
    return int(dt.timestamp() * 1000)


class TestTokenExtraction(unittest.TestCase):
    def test_greenhouse_job_board_url(self):
        self.assertEqual(
            ab.extract_ats_token("https://job-boards.greenhouse.io/vercel/jobs/5999792004"),
            ("greenhouse", "vercel"),
        )

    def test_greenhouse_legacy_boards_host(self):
        self.assertEqual(
            ab.extract_ats_token("https://boards.greenhouse.io/anthropic/jobs/123"),
            ("greenhouse", "anthropic"),
        )

    def test_greenhouse_embed_query_param(self):
        self.assertEqual(
            ab.extract_ats_token("https://boards.greenhouse.io/embed/job_board?for=mercury&t=1"),
            ("greenhouse", "mercury"),
        )

    def test_lever_url_skips_uuid(self):
        self.assertEqual(
            ab.extract_ats_token(
                "https://jobs.lever.co/shieldai/d2698861-180c-4645-8641-0e7725ce96f1"
            ),
            ("lever", "shieldai"),
        )

    def test_ashby_url(self):
        self.assertEqual(
            ab.extract_ats_token(
                "https://jobs.ashbyhq.com/ramp/7458d4e9-da2e-47bd-98cb-adfda43d42b2"
            ),
            ("ashby", "ramp"),
        )

    def test_non_ats_url_returns_none(self):
        self.assertIsNone(ab.extract_ats_token("https://www.linkedin.com/jobs/view/123"))
        self.assertIsNone(ab.extract_ats_token(""))
        self.assertIsNone(ab.extract_ats_token(None))

    def test_vendor_marketing_site_is_not_a_board(self):
        """Regression: ashbyhq.com/blog/... harvested 'blog' as a board token."""
        self.assertIsNone(
            ab.extract_ats_token("https://www.ashbyhq.com/blog/engineering/ai-ashby")
        )
        self.assertIsNone(ab.extract_ats_token("https://www.greenhouse.io/pricing"))
        self.assertIsNone(ab.extract_ats_token("https://www.lever.co/customers"))

    def test_eu_board_hosts_supported(self):
        self.assertEqual(
            ab.extract_ats_token("https://boards.eu.greenhouse.io/acme/jobs/1"),
            ("greenhouse", "acme"),
        )

    def test_host_with_port_still_matches(self):
        self.assertEqual(
            ab.extract_ats_token("https://jobs.ashbyhq.com:443/oneleet/uuid"),
            ("ashby", "oneleet"),
        )

    def test_hyphenated_token_preserved(self):
        self.assertEqual(
            ab.extract_ats_token("https://jobs.ashbyhq.com/duck-duck-go/a447e823"),
            ("ashby", "duck-duck-go"),
        )

    def test_harvest_groups_by_provider(self):
        found = ab.harvest_tokens_from_urls(
            [
                "https://job-boards.greenhouse.io/vercel/jobs/1",
                "https://job-boards.greenhouse.io/vercel/jobs/2",
                "https://jobs.lever.co/shieldai/abc",
                "https://jobs.ashbyhq.com/ramp/def",
                "https://indeed.com/viewjob?jk=9",
            ]
        )
        self.assertEqual(found["greenhouse"], {"vercel"})
        self.assertEqual(found["lever"], {"shieldai"})
        self.assertEqual(found["ashby"], {"ramp"})


class TestGreenhouseParser(unittest.TestCase):
    def _payload(self, **over):
        job = {
            "title": "Senior React Developer",
            "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
            "company_name": "Acme Corp",
            "location": {"name": "Remote - India"},
            "first_published": _iso_recent(),
        }
        job.update(over)
        return {"jobs": [job]}

    def test_parses_company_from_api(self):
        jobs = ab.parse_greenhouse_jobs(self._payload(), "acme", "React", 10)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Acme Corp")
        self.assertEqual(jobs[0]["platform"], "Greenhouse")
        self.assertEqual(jobs[0]["search_country"], "Remote - India")

    def test_falls_back_to_token_name(self):
        jobs = ab.parse_greenhouse_jobs(self._payload(company_name=""), "ribbon-health", "React", 10)
        self.assertEqual(jobs[0]["company"], "Ribbon Health")

    def test_keyword_filter_excludes_mismatch(self):
        jobs = ab.parse_greenhouse_jobs(self._payload(), "acme", "Kubernetes", 10)
        self.assertEqual(jobs, [])

    def test_drops_stale_posting(self):
        jobs = ab.parse_greenhouse_jobs(
            self._payload(first_published="2019-01-01T00:00:00+00:00"), "acme", "React", 10
        )
        self.assertEqual(jobs, [])

    @patch.object(config, "REMOTE_ONLY", True)
    def test_remote_only_drops_onsite(self):
        jobs = ab.parse_greenhouse_jobs(
            self._payload(location={"name": "London, UK"}), "acme", "React", 10
        )
        self.assertEqual(jobs, [])

    @patch.object(config, "REMOTE_ONLY", True)
    def test_remote_only_keeps_remote(self):
        jobs = ab.parse_greenhouse_jobs(self._payload(), "acme", "React", 10)
        self.assertEqual(len(jobs), 1)

    def test_respects_max_results(self):
        payload = {"jobs": [self._payload()["jobs"][0] for _ in range(9)]}
        self.assertEqual(len(ab.parse_greenhouse_jobs(payload, "acme", "React", 4)), 4)

    def test_skips_job_without_url(self):
        self.assertEqual(ab.parse_greenhouse_jobs(self._payload(absolute_url=""), "a", "React", 5), [])


class TestLeverParser(unittest.TestCase):
    def _payload(self, **over):
        job = {
            "text": "Staff Node.js Engineer",
            "hostedUrl": "https://jobs.lever.co/shieldai/uuid-1",
            "createdAt": _ms_recent(),
            "categories": {"location": "Remote"},
            "workplaceType": "remote",
        }
        job.update(over)
        return [job]

    def test_company_derived_from_config_override(self):
        jobs = ab.parse_lever_jobs(self._payload(), "shieldai", "Node", 10)
        self.assertEqual(len(jobs), 1)
        # config.ATS_COMPANY_NAMES maps shieldai → "Shield AI"
        self.assertEqual(jobs[0]["company"], "Shield AI")
        self.assertEqual(jobs[0]["title"], "Staff Node.js Engineer")
        self.assertEqual(jobs[0]["platform"], "Lever")

    def test_created_at_millis_converted_not_treated_as_seconds(self):
        """A ms epoch read as seconds lands in the year ~58,500 and would never expire."""
        jobs = ab.parse_lever_jobs(self._payload(), "shieldai", "Node", 10)
        from job_filters import parse_posted_at

        dt = parse_posted_at(jobs[0]["posted_at"])
        self.assertLess(abs((dt.year) - 2026), 3)

    def test_stale_millis_dropped(self):
        jobs = ab.parse_lever_jobs(self._payload(createdAt=1262304000000), "shieldai", "Node", 10)
        self.assertEqual(jobs, [])

    @patch.object(config, "REMOTE_ONLY", True)
    def test_remote_only_drops_onsite_workplace(self):
        jobs = ab.parse_lever_jobs(
            self._payload(workplaceType="onsite", categories={"location": "Austin, TX"}),
            "shieldai",
            "Node",
            10,
        )
        self.assertEqual(jobs, [])

    def test_falls_back_to_apply_url(self):
        jobs = ab.parse_lever_jobs(
            self._payload(hostedUrl="", applyUrl="https://jobs.lever.co/x/y/apply"), "x", "Node", 10
        )
        self.assertEqual(len(jobs), 1)

    def test_ignores_non_dict_entries(self):
        self.assertEqual(ab.parse_lever_jobs(["nope", None], "x", "Node", 10), [])


class TestAshbyParser(unittest.TestCase):
    def _payload(self, **over):
        job = {
            "title": "Backend Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/ramp/uuid-1",
            "location": "Remote - US",
            "publishedAt": _iso_recent(),
            "isRemote": True,
            "isListed": True,
            "department": "Engineering",
        }
        job.update(over)
        return {"jobs": [job]}

    def test_parses_basic_job(self):
        jobs = ab.parse_ashby_jobs(self._payload(), "ramp", "Backend", 10)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Ramp")
        self.assertEqual(jobs[0]["platform"], "Ashby")

    def test_unlisted_job_skipped(self):
        self.assertEqual(ab.parse_ashby_jobs(self._payload(isListed=False), "ramp", "Backend", 10), [])

    @patch.object(config, "REMOTE_ONLY", True)
    def test_remote_only_drops_non_remote(self):
        jobs = ab.parse_ashby_jobs(
            self._payload(isRemote=False, location="New York", workplaceType="Onsite"),
            "ramp",
            "Backend",
            10,
        )
        self.assertEqual(jobs, [])

    def test_matches_on_department_too(self):
        jobs = ab.parse_ashby_jobs(self._payload(title="Generalist"), "ramp", "Engineering", 10)
        self.assertEqual(len(jobs), 1)


class TestTokenRegistry(unittest.TestCase):
    def test_board_tokens_merges_config_and_harvested(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "toks.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"greenhouse": ["harvested-co"]}, fh)
            with patch.object(config, "ATS_TOKENS_FILE", path), patch.object(
                config, "GREENHOUSE_BOARDS", ["seed-co"]
            ):
                tokens = ab.board_tokens("greenhouse")
        self.assertIn("seed-co", tokens)
        self.assertIn("harvested-co", tokens)

    def test_board_tokens_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "toks.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"lever": ["dup"]}, fh)
            with patch.object(config, "ATS_TOKENS_FILE", path), patch.object(
                config, "LEVER_BOARDS", ["dup"]
            ):
                self.assertEqual(ab.board_tokens("lever").count("dup"), 1)

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "toks.json")
            with patch.object(config, "ATS_TOKENS_FILE", path), patch.object(
                config, "ASHBY_BOARDS", []
            ):
                added = ab.save_harvested_tokens({"ashby": {"newco", "othernew"}})
                self.assertEqual(added["ashby"], 2)
                self.assertEqual(set(ab.load_harvested_tokens()["ashby"]), {"newco", "othernew"})
                # re-saving the same tokens adds nothing
                self.assertEqual(ab.save_harvested_tokens({"ashby": {"newco"}})["ashby"], 0)

    def test_missing_token_file_is_not_an_error(self):
        with patch.object(config, "ATS_TOKENS_FILE", "/nonexistent/nope.json"):
            self.assertEqual(ab.load_harvested_tokens(), {})

    def test_no_tokens_returns_empty_without_network(self):
        with patch.object(config, "GREENHOUSE_BOARDS", []), patch.object(
            config, "ATS_TOKENS_FILE", "/nonexistent/nope.json"
        ):
            self.assertEqual(ab.scrape_greenhouse("React", 10), [])


class TestTokenToName(unittest.TestCase):
    def test_slug_title_cased(self):
        self.assertEqual(ab._token_to_name("ribbon-health"), "Ribbon Health")

    def test_config_override_wins(self):
        self.assertEqual(ab._token_to_name("openai"), "OpenAI")


if __name__ == "__main__":
    unittest.main()
