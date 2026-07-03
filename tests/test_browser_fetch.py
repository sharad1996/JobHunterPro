"""Unit tests for browser_fetch (signature + pure parsers, no real browser)."""

import inspect
import unittest

import browser_fetch as bf


class TestFetchUrlSignature(unittest.TestCase):
    def test_fetch_url_accepts_wait_for_selector(self):
        params = inspect.signature(bf.fetch_url).parameters
        self.assertIn("wait_for_selector", params)
        self.assertIsNone(params["wait_for_selector"].default)


if __name__ == "__main__":
    unittest.main()
