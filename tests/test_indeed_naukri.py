"""Unit tests for Indeed + Naukri parse functions (pure, no network)."""

import unittest

import browser_fetch as bf


INDEED_HTML = """
<html><body>
  <div id="mosaic-provider-jobcards">
    <div class="job_seen_beacon">
      <h2 class="jobTitle"><a data-jk="abc123"><span title="Senior React Engineer">Senior React Engineer</span></a></h2>
      <span data-testid="company-name">Acme Labs</span>
      <span data-testid="myJobsStateDate">Posted 2 days ago</span>
    </div>
  </div>
</body></html>
"""


class TestParseIndeed(unittest.TestCase):
    def test_extracts_company_title_url_and_posted(self):
        jobs = bf.parse_indeed_like_html(
            INDEED_HTML, "https://in.indeed.com", "React Developer", "India", 10
        )
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["company"], "Acme Labs")
        # Real title, NOT the query term "React Developer"
        self.assertEqual(job["title"], "Senior React Engineer")
        self.assertEqual(job["platform"], "Indeed")
        self.assertEqual(job["search_country"], "India")
        self.assertEqual(job["posted_at"], "Posted 2 days ago")


if __name__ == "__main__":
    unittest.main()
