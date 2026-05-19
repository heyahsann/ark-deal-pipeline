"""LinkedIn monitor agent — watches LinkedIn for founder leads.

Searches DuckDuckGo for LinkedIn posts and engagement from key people
(Hubert Thieblot, Founders Inc., investors), looking for AI-native
founders in SF/NYC/etc. announcing products or raises.
"""

import re
import time

from models import Lead, Source
from agents.base import BaseAgent, extract_json
from search import web_search

# Monitored LinkedIn profiles and keywords
MONITORED_LI_PROFILES = [
    "Hubert Thieblot",
    "Founders Inc",
    "fdotinc",
]

# Phase 1: Search for posts by/about monitored people
LI_PROFILE_QUERIES = [
    'site:linkedin.com/posts "Hubert Thieblot" AI founder',
    'site:linkedin.com/posts "Hubert Thieblot" startup',
    'site:linkedin.com/posts "Hubert Thieblot" raise',
    'site:linkedin.com/posts "Hubert Thieblot" launch',
    'site:linkedin.com/posts "Hubert Thieblot" San Francisco',
    'site:linkedin.com/posts "Founders Inc" AI',
    'site:linkedin.com/posts "Founders Inc" launch',
    'site:linkedin.com/posts "Founders Inc" raise',
    'site:linkedin.com/posts "fdotinc" AI',
    'site:linkedin.com/posts "fdotinc" founder',
    'site:linkedin.com/posts "fdotinc" launch',
    'site:linkedin.com/posts "fdotinc" San Francisco',
]

# Phase 2: Broader founder signal search on LinkedIn
LI_SIGNAL_QUERIES = [
    'site:linkedin.com/posts "just raised" "AI" "seed" "San Francisco"',
    'site:linkedin.com/posts "we raised" "AI" "seed" "San Francisco"',
    'site:linkedin.com/posts "launched" "AI" "founder" "San Francisco"',
    'site:linkedin.com/posts "building" "AI agent" San Francisco',
    'site:linkedin.com/posts "pre-seed" "AI" "San Francisco"',
    'site:linkedin.com/posts "YC" "AI" "founder" San Francisco',
    'site:linkedin.com/posts "we are building" "AI" San Francisco',
    'site:linkedin.com/posts "just launched" "AI" "product" San Francisco',
    'site:linkedin.com/posts "hiring" "AI" "SF" "seed"',
]

LI_SYSTEM_PROMPT = """You are a LinkedIn monitor for an AI startup deal sourcing pipeline.
You analyze LinkedIn posts and engagements from investors and startup community members
(Hubert Thieblot, Founders Inc, fdotinc) and broader founder signal searches.

Your goal: find EARLY-STAGE AI FOUNDERS posting about their startups.

Look for ALL of the following:
- Founders announcing they raised a pre-seed or seed round
- People who just launched an AI product or beta
- Founders based in San Francisco, NYC, Austin, Seattle, or LA
- People posting "we're building" or "just launched" with an AI product
- Founders tagged in posts by investors (Hubert Thieblot, Founders Inc)
- "we got into", "accepted into" accelerator programs
- Team updates: "team of X", "hiring in SF", "two founders"
- "building with Claude", "building with GPT", "AI agent", "vibe coding"

For EVERY post mentioning a person building a company:
- Extract their name from the post content, author name, or handle
- Look for their company name in the post
- Look for a LinkedIn profile URL in the result

Return a JSON array of objects, each with:
- founder_name (string — REQUIRED. The full name of the person building the company)
- company (string, or "Unknown")
- linkedin_url (string — the full LinkedIn profile URL if found, e.g. "https://www.linkedin.com/in/name". Empty if not.)
- location (string — city, state from profile or post. E.g. "San Francisco, CA". Empty if unknown.)
- raw_signal (string — the full post text or snippet)
- source (string: always "LinkedIn")
- links (array of strings — the post URL, any company links, etc.)

Do NOT include generic AI news or established companies.
Focus on early-stage founders building AI-native products."""


def _search_batch(queries: list[str], seen_urls: set[str], label: str) -> list[dict]:
    """Run web searches for each query, deduplicating by URL."""
    results: list[dict] = []
    for query in queries:
        try:
            batch = web_search(query, max_results=5)
            for r in batch:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    results.append(r)
            time.sleep(0.6)
        except Exception as e:
            print(f"    [WARN] Search failed for '{query}': {e}")
            continue
    if results:
        print(f"    {label}: {len(results)} results")
    return results


class LinkedInMonitor(BaseAgent):
    """Monitors LinkedIn for founder signals via DuckDuckGo."""

    default_model = "deepseek-chat"

    def monitor(self) -> list[Lead]:
        """Search LinkedIn posts and engagement for founder leads."""
        print("  Searching LinkedIn for founder signals...")

        all_results: list[dict] = []
        seen_urls: set[str] = set()

        # Phase 1: Posts from/about monitored profiles
        p1 = _search_batch(LI_PROFILE_QUERIES, seen_urls, "Phase 1 — monitored profiles")
        all_results.extend(p1)

        # Phase 2: Broader founder signal searches on LinkedIn
        p2 = _search_batch(LI_SIGNAL_QUERIES, seen_urls, "Phase 2 — signal searches")
        all_results.extend(p2)

        print(f"  Total: {len(all_results)} LinkedIn results")

        if not all_results:
            return []

        formatted = "\n\n".join(
            f"Title: {r['title']}\nSnippet: {r.get('snippet', '')}\nURL: {r['url']}"
            for r in all_results
        )

        response = self._call(
            system=LI_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Find founder leads from these LinkedIn posts:\n\n{formatted}",
                }
            ],
        )

        try:
            data = extract_json(response)
        except Exception as e:
            print(f"  [ERROR] Failed to parse LinkedIn monitor output: {e}")
            return []

        if isinstance(data, dict):
            data = data.get("leads") or data.get("results") or [data]
        if not isinstance(data, list):
            return []

        leads = []
        for item in data:
            try:
                links = item.get("links", [])
                if isinstance(links, str):
                    links = [links]

                li_url = (item.get("linkedin_url") or "").strip()
                if li_url and li_url not in links:
                    links.insert(0, li_url)

                leads.append(
                    Lead(
                        founder_name=item.get("founder_name", "Unknown"),
                        company=item.get("company", "Unknown"),
                        raw_signal=item.get("raw_signal", ""),
                        source=Source.LINKEDIN,
                        links=links,
                        location=item.get("location", "") or "",
                    )
                )
            except Exception as e:
                print(f"  [WARN] Skipping lead: {e}")

        print(f"  Extracted {len(leads)} leads from LinkedIn monitoring")
        return leads

    def demo(self) -> list[Lead]:
        """Return demo leads from LinkedIn monitoring for testing."""
        return [
            Lead(
                founder_name="Rohan Mehta",
                company="KrispAI",
                raw_signal="Just raised $2M pre-seed for AI-native call summarization for sales teams. SF-based, hiring founding engineers.",
                source=Source.LINKEDIN,
                links=["https://www.linkedin.com/in/rohanmehta"],
            ),
            Lead(
                founder_name="Sophia Tran",
                company="GuardianML",
                raw_signal="Building AI guardrails for enterprise LLM deployments. YC W25, team of 3 in NYC. Looking for seed partners.",
                source=Source.LINKEDIN,
                links=["https://www.linkedin.com/in/sophiatran"],
            ),
        ]
