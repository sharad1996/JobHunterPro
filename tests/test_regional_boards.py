"""Unit tests for regional_boards (mocked HTTP)."""

import unittest
from unittest.mock import patch, MagicMock

import regional_boards as rb


class TestTokyoDevScrape(unittest.TestCase):
    @patch.object(rb.requests, "get")
    def test_scrape_tokyodev_parses_company_job_links(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html><body>
          <h3>Treasure AI</h3>
          <h4><a href="/companies/treasure/jobs/senior-python-engineer">Senior Python Engineer</a></h4>
        </body></html>
        """
        mock_get.return_value = mock_resp

        jobs = rb.scrape_tokyodev("Python", max_results=5)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Treasure AI")
        self.assertEqual(jobs[0]["platform"], "TokyoDev")
        self.assertIn("tokyodev.com", jobs[0]["url"])


class TestJapanDevScrape(unittest.TestCase):
    @patch.object(rb.requests, "get")
    def test_scrape_japan_dev_parses_job_paths(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html><body>
          <a href="/jobs/acme/acme-backend-engineer-abc123">Backend Engineer</a>
        </body></html>
        """
        mock_get.return_value = mock_resp

        jobs = rb.scrape_japan_dev("Backend", max_results=5)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Backend Engineer")
        self.assertEqual(jobs[0]["platform"], "Japan Dev")


class TestBaytRegion(unittest.TestCase):
    def test_bayt_region_maps_dubai_to_uae(self):
        self.assertEqual(rb._bayt_region("Dubai"), "uae")
        self.assertEqual(rb._bayt_region("Singapore"), "international")


if __name__ == "__main__":
    unittest.main()
