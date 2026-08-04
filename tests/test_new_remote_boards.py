"""Unit tests for the Arbeitnow and Jobicy scrapers (mocked HTTP)."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import config
import remote_boards as rb


def _epoch_recent():
    return int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp())


def _iso_recent():
    return (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()


def _resp(payload, status=200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload
    return m


class TestArbeitnow(unittest.TestCase):
    def _job(self, **over):
        j = {
            "company_name": "Bitpanda",
            "title": "Senior React Engineer",
            "url": "https://www.arbeitnow.com/jobs/companies/bitpanda/senior-react-1",
            "location": "Berlin, Berlin",
            "remote": True,
            "tags": ["Engineering"],
            "job_types": ["full_time"],
            "created_at": _epoch_recent(),
        }
        j.update(over)
        return j

    @patch.object(config, "ARBEITNOW_MAX_PAGES", 1)
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_parses_job(self, mock_get):
        mock_get.return_value = _resp({"data": [self._job()]})
        jobs = rb.scrape_arbeitnow("React", max_results=10)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Bitpanda")
        self.assertEqual(jobs[0]["platform"], "Arbeitnow")
        self.assertEqual(jobs[0]["search_country"], "Berlin, Berlin")

    @patch.object(config, "ARBEITNOW_MAX_PAGES", 1)
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_keyword_mismatch_excluded(self, mock_get):
        mock_get.return_value = _resp({"data": [self._job()]})
        self.assertEqual(rb.scrape_arbeitnow("Kubernetes", max_results=10), [])

    @patch.object(config, "ARBEITNOW_MAX_PAGES", 1)
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_stale_job_dropped(self, mock_get):
        mock_get.return_value = _resp({"data": [self._job(created_at=1262304000)]})
        self.assertEqual(rb.scrape_arbeitnow("React", max_results=10), [])

    @patch.object(config, "REMOTE_ONLY", True)
    @patch.object(config, "ARBEITNOW_MAX_PAGES", 1)
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_remote_only_drops_onsite(self, mock_get):
        mock_get.return_value = _resp(
            {"data": [self._job(remote=False, location="Berlin", title="React Dev")]}
        )
        self.assertEqual(rb.scrape_arbeitnow("React", max_results=10), [])

    @patch.object(config, "REMOTE_ONLY", True)
    @patch.object(config, "ARBEITNOW_MAX_PAGES", 1)
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_remote_only_keeps_remote_in_title(self, mock_get):
        mock_get.return_value = _resp(
            {"data": [self._job(remote=False, title="React Engineer (Remote)")]}
        )
        self.assertEqual(len(rb.scrape_arbeitnow("React", max_results=10)), 1)

    @patch.object(config, "ARBEITNOW_MAX_PAGES", 1)
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_dedupes_repeated_url(self, mock_get):
        mock_get.return_value = _resp({"data": [self._job(), self._job()]})
        self.assertEqual(len(rb.scrape_arbeitnow("React", max_results=10)), 1)

    @patch.object(config, "ARBEITNOW_MAX_PAGES", 1)
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_http_error_returns_empty(self, mock_get):
        mock_get.return_value = _resp({}, status=503)
        self.assertEqual(rb.scrape_arbeitnow("React", max_results=10), [])


class TestJobicy(unittest.TestCase):
    def _job(self, **over):
        j = {
            "companyName": "Nebius",
            "jobTitle": "Senior React Engineer",
            "url": "https://jobicy.com/jobs/150137-senior-react",
            "jobGeo": "India",
            "jobIndustry": ["Software Engineering"],
            "pubDate": _iso_recent(),
        }
        j.update(over)
        return j

    @patch.object(config, "TARGET_COUNTRIES", ["India"])
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_parses_job(self, mock_get):
        mock_get.return_value = _resp({"jobs": [self._job()]})
        jobs = rb.scrape_jobicy("React", max_results=10)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Nebius")
        self.assertEqual(jobs[0]["platform"], "Jobicy")

    @patch.object(config, "TARGET_COUNTRIES", ["Germany", "Canada"])
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_dedupes_across_geo_sweeps(self, mock_get):
        """germany + canada + unfiltered = 3 calls; the same job must appear once."""
        mock_get.return_value = _resp({"jobs": [self._job()]})
        jobs = rb.scrape_jobicy("React", max_results=10)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(mock_get.call_count, 3)

    @patch.object(config, "TARGET_COUNTRIES", ["Germany"])
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_maps_known_country_to_geo_slug(self, mock_get):
        mock_get.return_value = _resp({"jobs": []})
        rb.scrape_jobicy("React", max_results=10)
        geos = [c.kwargs["params"].get("geo") for c in mock_get.call_args_list]
        self.assertIn("germany", geos)

    @patch.object(config, "TARGET_COUNTRIES", ["India", "Dubai", "Vietnam"])
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_unsupported_countries_never_sent_as_geo(self, mock_get):
        """Regression: geo=india / geo=emea are invalid and return HTTP 400.

        Unmapped countries must fall through to the single unfiltered sweep instead.
        """
        mock_get.return_value = _resp({"jobs": []})
        rb.scrape_jobicy("React", max_results=10)
        geos = [c.kwargs["params"].get("geo") for c in mock_get.call_args_list]
        self.assertEqual(geos, [None])

    def test_every_mapped_geo_is_a_verified_slug(self):
        """Guards against re-introducing an invented slug; these 14 were verified live."""
        valid = {
            "germany", "usa", "uk", "canada", "australia", "europe", "singapore",
            "japan", "france", "spain", "netherlands", "poland", "ukraine", "philippines",
        }
        self.assertTrue(set(rb._JOBICY_GEOS.values()) <= valid)

    @patch.object(config, "TARGET_COUNTRIES", [])
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_unknown_countries_still_sweep_unfiltered(self, mock_get):
        mock_get.return_value = _resp({"jobs": [self._job()]})
        jobs = rb.scrape_jobicy("React", max_results=10)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(mock_get.call_count, 1)

    @patch.object(config, "TARGET_COUNTRIES", ["India"])
    @patch.object(rb, "_pause", lambda: None)
    @patch.object(rb.requests, "get")
    def test_stale_job_dropped(self, mock_get):
        mock_get.return_value = _resp({"jobs": [self._job(pubDate="2019-01-01T00:00:00+00:00")]})
        self.assertEqual(rb.scrape_jobicy("React", max_results=10), [])


if __name__ == "__main__":
    unittest.main()
