"""Unit tests for marketplace_boards (mocked HTTP)."""

import unittest
from unittest.mock import patch, MagicMock

import marketplace_boards as mb


class TestFreelancerScrape(unittest.TestCase):
    @patch.object(mb.requests, "get")
    def test_scrape_freelancer_maps_projects(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "result": {
                "projects": [
                    {
                        "title": "React dashboard",
                        "seo_url": "react/React-dashboard",
                        "owner_id": 123,
                    }
                ]
            },
        }
        mock_get.return_value = mock_resp

        jobs = mb.scrape_freelancer("React", max_results=5)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "React dashboard")
        self.assertIn("freelancer.com/projects", jobs[0]["url"])
        self.assertEqual(jobs[0]["platform"], "Freelancer")


if __name__ == "__main__":
    unittest.main()
