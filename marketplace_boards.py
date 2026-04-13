"""
Marketplace / gig boards with official or public read APIs.

Secrets: use environment variables (never commit tokens to config.py).

  UPWORK_ACCESS_TOKEN — OAuth2 bearer from https://www.upwork.com/developer/
  Freelancer.com search uses the public projects API (no key for basic read).
"""

import os
import json
import random
import time
from typing import Any, Dict, List

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _pause():
    time.sleep(random.uniform(0.8, 1.6))


def scrape_freelancer(job_title: str, max_results: int = 30) -> List[Dict[str, Any]]:
    """Freelancer.com active projects search (public read API)."""
    results: List[Dict[str, Any]] = []
    print("  → Searching Freelancer (public API)...")
    try:
        r = requests.get(
            "https://www.freelancer.com/api/projects/0.1/projects/active/",
            headers=HEADERS,
            params={"query": job_title, "limit": min(max_results, 100)},
            timeout=25,
        )
        if r.status_code != 200:
            print(f"  ✗ Freelancer: HTTP {r.status_code}")
            return results
        data = r.json()
        projects = (data.get("result") or {}).get("projects") or []
        for p in projects:
            seo = (p.get("seo_url") or "").strip()
            if not seo:
                continue
            title = (p.get("title") or "").strip() or job_title
            url = f"https://www.freelancer.com/projects/{seo}"
            owner = p.get("owner_id")
            company = f"Freelancer client #{owner}" if owner else "Freelancer"
            results.append(
                {
                    "company": company,
                    "title": title,
                    "url": url,
                    "platform": "Freelancer",
                    "domain": "",
                    "search_country": "Global",
                }
            )
            if len(results) >= max_results:
                break
        print(f"  ✓ Freelancer: {len(results)} results")
    except Exception as e:
        print(f"  ✗ Freelancer error: {e}")
    _pause()
    return results


def scrape_upwork(job_title: str, max_results: int = 30) -> List[Dict[str, Any]]:
    """
    Upwork GraphQL (OAuth2 bearer). Set env UPWORK_ACCESS_TOKEN.
    Query shape may need adjustment as Upwork evolves — errors print a short hint.
    """
    results: List[Dict[str, Any]] = []
    token = (os.environ.get("UPWORK_ACCESS_TOKEN") or "").strip()
    if not token:
        print(
            "  → Upwork: skipped — set env UPWORK_ACCESS_TOKEN (OAuth bearer; "
            "see INTEGRATIONS.md)"
        )
        return results

    print("  → Searching Upwork (GraphQL API)...")
    endpoint = "https://api.upwork.com/graphql"
    # Broad search query; Upwork may require specific permission on the key.
    query = """
    query JobSearch($q: String!, $first: Int!) {
      marketplaceJobPostingsSearch(
        marketplaceJobPostingsSearchRequest: { query: $q }
      ) {
        totalCount
        edges {
          node {
            id
            title
            ciphertext
          }
        }
      }
    }
    """
    try:
        r = requests.post(
            endpoint,
            headers={
                **HEADERS,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(
                {
                    "query": query,
                    "variables": {"q": job_title, "first": min(max_results, 50)},
                }
            ),
            timeout=30,
        )
        if r.status_code != 200:
            print(f"  ✗ Upwork: HTTP {r.status_code} — {r.text[:200]}")
            return results
        payload = r.json()
        if payload.get("errors"):
            print(f"  ✗ Upwork GraphQL: {payload.get('errors')[:1]}")
            return results
        data = (((payload.get("data") or {}).get("marketplaceJobPostingsSearch")) or {})
        edges = data.get("edges") or []
        for edge in edges:
            node = (edge or {}).get("node") or {}
            cid = (node.get("ciphertext") or node.get("id") or "").strip()
            title = (node.get("title") or "").strip() or job_title
            if not cid:
                continue
            url = f"https://www.upwork.com/jobs/~{cid}/"
            results.append(
                {
                    "company": "Upwork client",
                    "title": title,
                    "url": url,
                    "platform": "Upwork",
                    "domain": "",
                    "search_country": "Global",
                }
            )
            if len(results) >= max_results:
                break
        print(f"  ✓ Upwork: {len(results)} results")
    except Exception as e:
        print(f"  ✗ Upwork error: {e}")
    _pause()
    return results
