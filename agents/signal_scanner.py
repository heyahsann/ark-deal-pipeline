import math
import re
import time

from models import Lead, Source
from agents.base import BaseAgent, extract_json
from search import web_search

SYSTEM_PROMPT = """You are a signal scanner for an AI startup deal sourcing pipeline.
Extract early-stage AI startup leads from web search results.

Given search result entries (title + snippet + URL), identify posts/articles about:
- Founders building AI-native products or startups
- Recently launched AI products or betas
- Fundraising announcements (pre-seed, seed rounds)
- Founder posts about building with LLMs (Claude, GPT, etc.)
- Y Combinator companies
- Technical founders in US tech hubs (SF, NYC, Austin, Seattle, LA)

Return a JSON array of objects, each with:
- founder_name (string — REQUIRED. Infer from ANY available context: X handle, Reddit username, YouTube channel name, article byline, Product Hunt maker name, Twitter bio. Use "Unknown" ONLY if absolutely no name can be found.)
- company (string, or "Unknown")
- linkedin_url (string — the full LinkedIn profile URL if found, e.g. "https://linkedin.com/in/sarahchen". Empty string if not found.)
- location (string -- city, state from bio or article. E.g. "San Francisco, CA". Empty if unknown.)
- raw_signal (string, the relevant snippet or text)
- source (string: "Twitter/X", "LinkedIn", or "Web")
- links (array of strings — include company website, X/Twitter, Product Hunt, GitHub as applicable)

CRITICAL: LINKEDIN EXTRACTION
- Search EVERY result snippet for "linkedin.com/in/" — if present, extract the FULL LinkedIn profile URL
- LinkedIn URLs look like: linkedin.com/in/username or linkedin.com/in/username-123
- Always prefer the full https:// linkedin URL
- If a result mentions someone is on LinkedIn but doesn't have the URL, set linkedin_url to empty string — DO NOT fabricate

CRITICAL: FOUNDER NAME EXTRACTION
- If a result mentions an X/Twitter handle like @sarahchen, extract "Sarah Chen" as founder_name
- If a Reddit post has a username, extract name from it
- If an article has an author byline, use that
- If a Product Hunt page has a maker name, use that
- Infer real name from handles where possible

Do NOT include generic AI news or established companies.
Focus on early-stage startups (< 2 years old, small teams, pre-seed/seed)."""


# Regex patterns for name inference
HANDLE_PATTERN = re.compile(r'@(\w[\w.]*)')
LINKEDIN_PATTERN = re.compile(r'https?://(?:www\.)?linkedin\.com/in/[\w-]+')
AUTHOR_PATTERN = re.compile(r'(?:by|author|written by|posted by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', re.IGNORECASE)


def _infer_name_from_handle(handle: str) -> str | None:
    """Try to convert a handle like 'sarahchen' or 'sarah_chen' into 'Sarah Chen'."""
    clean = handle.lstrip('@')
    if not clean:
        return None
    # Replace underscores, dots, hyphens with spaces
    name = re.sub(r'[._-]', ' ', clean)
    # Title case it
    name = name.title().strip()
    # Filter out things that don't look like real names (single word, all lowercase-ish, too short)
    words = name.split()
    if len(words) < 1 or len(name) < 3:
        return None
    if len(words) == 1 and len(words[0]) > 15:
        return None  # looks like a brand/username, not a name
    return name


def _extract_linkedin_urls(results: list[dict]) -> list[str]:
    """Scan search result snippets for LinkedIn profile URLs."""
    urls: set[str] = set()
    for r in results:
        snippet = r.get("snippet", "")
        url = r.get("url", "")
        title = r.get("title", "")
        text = f"{title} {snippet} {url}"
        for match in LINKEDIN_PATTERN.finditer(text):
            found = match.group(0)
            if not found.startswith("http"):
                found = "https://" + found
            urls.add(found)
        # also check the url field directly
        if "linkedin.com/in/" in url:
            urls.add(url)
    return list(urls)


class SignalScanner(BaseAgent):
    default_model = "deepseek-chat"

    def scan(self, keywords: list[str]) -> list[Lead]:
        print("  Searching web for signals...")
        results = web_search(keywords)
        print(f"  Found {len(results)} raw search results")

        if not results:
            print("  No search results to analyze")
            return []

        # Phase 1: Extract LinkedIn URLs from raw results before they go to the model
        raw_linkedin_urls = _extract_linkedin_urls(results)
        if raw_linkedin_urls:
            print(f"  Found {len(raw_linkedin_urls)} LinkedIn profile URLs in search results")

        # Phase 2: Send to LLM for extraction
        formatted = "\n\n".join(
            f"Title: {r['title']}\nSnippet: {r.get('snippet', '')}\nURL: {r['url']}"
            for r in results
        )

        response = self._call(
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Extract startup leads from these search results:\n\n{formatted}",
                }
            ],
        )

        try:
            data = extract_json(response)
        except Exception as e:
            print(f"  [ERROR] Failed to parse scanner output: {e}")
            return []

        if isinstance(data, dict):
            data = data.get("leads") or data.get("results") or [data]
        if not isinstance(data, list):
            return []

        source_map = {
            "x": Source.X,
            "twitter": Source.X,
            "twitter/x": Source.X,
            "linkedin": Source.LINKEDIN,
            "web": Source.WEB,
        }

        leads = []
        for item in data:
            try:
                src = source_map.get(str(item.get("source", "")).strip().lower(), Source.WEB)

                # Collect links from the model output
                links = item.get("links", [])
                if isinstance(links, str):
                    links = [links]

                # Add linkedin_url from the new dedicated field
                li_url = (item.get("linkedin_url") or "").strip()
                if li_url and li_url not in links:
                    links.insert(0, li_url)

                # Fallback: attach any raw LinkedIn URLs that mention the founder name
                founder = (item.get("founder_name") or "").strip()
                if not any("linkedin.com/in/" in u for u in links) and founder != "Unknown":
                    for lu in raw_linkedin_urls:
                        if lu not in links:
                            links.append(lu)

                leads.append(
                    Lead(
                        founder_name=founder or "Unknown",
                        company=item.get("company", "Unknown"),
                        raw_signal=item.get("raw_signal", ""),
                        source=src,
                        links=links,
                        location=item.get("location", "") or "",
                    )
                )
            except Exception as e:
                print(f"  [WARN] Skipping lead: {e}")

        # Phase 3: Post-processing — infer names from handles for "Unknown" founders
        for lead in leads:
            if lead.founder_name in ("Unknown", "") and lead.links:
                for link in lead.links:
                    handle_match = re.search(r'x\.com/(\w+)', link) or re.search(r'twitter\.com/(\w+)', link)
                    if handle_match:
                        inferred = _infer_name_from_handle(handle_match.group(1))
                        if inferred:
                            lead.founder_name = inferred
                            break

        # Phase 4: For leads missing LinkedIn URLs, do a targeted search
        linkedin_needed = [l for l in leads if not any("linkedin.com/in/" in u for u in l.links) and l.founder_name not in ("Unknown", "")]
        if linkedin_needed:
            print(f"  Searching for LinkedIn profiles for {len(linkedin_needed)} leads...")
            for lead in linkedin_needed:
                li_results = web_search(f"{lead.founder_name} {lead.company} LinkedIn", max_results=5)
                for lu in _extract_linkedin_urls(li_results):
                    if lu not in lead.links:
                        lead.links.insert(0, lu)
                        break
                time.sleep(0.3)

        print(f"  Extracted {len(leads)} leads")
        return leads

    def demo(self) -> list[Lead]:
        """Return demo leads for testing without API calls."""
        return [
            Lead(
                founder_name="Sarah Chen",
                company="Lumos AI",
                raw_signal="YC S24 alum building AI-powered code review. Raised $3M seed. Building with Claude.",
                source=Source.DEMO,
                links=["https://x.com/sarahchen"],
            ),
            Lead(
                founder_name="Marcus Johnson",
                company="DataWeave",
                raw_signal="Just launched AI-native data transformation tool on Product Hunt. Pre-seed, team of 3 in SF.",
                source=Source.DEMO,
                links=["https://dataweave.ai", "https://producthunt.com/..."],
            ),
            Lead(
                founder_name="Priya Patel",
                company="AgentOps",
                raw_signal="Building vertical AI agent for DevOps. YC W25. Looking for seed round. Based in Austin.",
                source=Source.DEMO,
                links=["https://linkedin.com/in/priyapatel"],
            ),
            Lead(
                founder_name="Alex Kim",
                company="FinChat",
                raw_signal="AI-native fintech for personal finance. Launched beta, 5k users. Pre-seed, team of 2 in NYC.",
                source=Source.DEMO,
                links=["https://x.com/alexkim"],
            ),
            Lead(
                founder_name="Jordan Taylor",
                company="VibeML",
                raw_signal="Building no-code ML platform. SF-based, team of 4, recently raised $1.2M pre-seed.",
                source=Source.DEMO,
                links=["https://vibeml.com"],
            ),
            Lead(
                founder_name="Emily Zhang",
                company="ComplyAI",
                raw_signal="AI compliance agent for startups. Just raised $1.5M pre-seed. Female founder in Seattle.",
                source=Source.DEMO,
                links=["https://complyai.com"],
            ),
            Lead(
                founder_name="Ryan O'Brien",
                company="PromptHub",
                raw_signal="Enterprise prompt management platform. Posting daily about building with LLMs. LA-based.",
                source=Source.DEMO,
                links=["https://x.com/ryanobrien"],
            ),
            Lead(
                founder_name="Neha Gupta",
                company="MedSynth",
                raw_signal="AI-native medical documentation. YC W24, HIPAA compliant. 10 hospitals piloting. Series A inbound.",
                source=Source.DEMO,
                links=["https://linkedin.com/in/nehagupta"],
            ),
        ]
