"""Social monitor agent — watches X accounts for founder leads.

Dual-mode: tries X API v2 first (if bearer token is configured), falls back
to DuckDuckGo web search if the X API is unavailable (402 Payment Required).
Extracts AI-native SF founders announcing products or raises.
"""

import re
import time

import httpx

from agents.base import BaseAgent, extract_json
from config import settings
from models import Lead, Source
from search import web_search

MONITORED_HANDLES = ["fdotinc", "hthieblot"]

X_API_BASE = "https://api.twitter.com/2"

# ── DuckDuckGo fallback queries ──────────────────────────────────────────
HTHIEBLOT_POST_QUERIES = [
    "site:x.com hthieblot AI",
    "site:x.com hthieblot founder",
    "site:x.com hthieblot startup",
    "site:x.com hthieblot launch",
    "site:x.com hthieblot raise",
    "site:x.com hthieblot San Francisco",
    "site:x.com hthieblot building",
    "site:x.com hthieblot agent",
]
HTHIEBLOT_MENTION_QUERIES = [
    '"@hthieblot" site:x.com',
    '"Hubert Thieblot" site:x.com',
    '"thank you" "@hthieblot" site:x.com',
    '"we built" "@hthieblot" site:x.com',
    '"just launched" "@hthieblot" site:x.com',
    '"we raised" hthieblot site:x.com',
    '"we''re building" hthieblot site:x.com',
]
HTHIEBLOT_REPLY_QUERIES = [
    '"building" hthieblot site:x.com',
    '"congrats" hthieblot site:x.com',
    '"awesome" hthieblot site:x.com',
    '"proud" hthieblot site:x.com',
]
CONTEXT_QUERIES = [
    '"fdotinc" "Hubert Thieblot" founder site:x.com',
    '"Hubert Thieblot" portfolio startup',
]
FDOTINC_QUERIES = [
    'site:x.com fdotinc AI',
    'site:x.com fdotinc founder',
    'site:x.com fdotinc launch',
    '"@fdotinc" site:x.com',
]
ALL_DDG_QUERIES = [
    *[(q, "@hthieblot") for q in HTHIEBLOT_POST_QUERIES + HTHIEBLOT_MENTION_QUERIES + HTHIEBLOT_REPLY_QUERIES],
    *[(q, "@fdotinc") for q in FDOTINC_QUERIES],
    *[(q, None) for q in CONTEXT_QUERIES],
]

X_POST_URL_RE = re.compile(r'https?://(?:www\.)?(?:x|twitter)\.com/\w+/status/\d+')

SYSTEM_PROMPT = """You are a social monitor for an AI startup deal sourcing pipeline.
You analyze posts, replies, and mentions from known investors and startup community
members (@fdotinc, @hthieblot / Hubert Thieblot).

Your goal: find EARLY-STAGE AI FOUNDERS who interact with or are mentioned by these accounts.

Look for ALL of the following:
- People replying to @hthieblot or @fdotinc announcing they're building something
- Founders announcing they raised a pre-seed or seed round in a reply or post
- People who just launched a product or beta that @hthieblot interacted with
- Founders based in San Francisco or other US tech hubs (NYC, Austin, Seattle, LA)
- @hthieblot replying to founders with encouragement — the person HE replies to is the lead
- Anyone posting about being accepted into an accelerator or incubator
- "we got into", "just got into", "accepted into" + accelerator name
- Team updates: "two founders", "team of X", "hiring in SF"
- "building with Claude", "building with GPT", "AI agent", "just launched",
  "pre-seed", "seed round", "AI-native", "vibe coding", "we raised"

CRITICAL — FOUNDER DETECTION:
When @hthieblot or @fdotinc engages with someone, THAT PERSON is the founder lead.
Look at who is being replied to, who is being congratulated, who says "thank you".

Return a JSON array of objects, each with:
- founder_name (string — REQUIRED. Infer from name, X handle, or bio content.
  Convert @johndoe -> "John Doe". Use "Unknown" only if no name possible.)
- company (string, or "Unknown")
- linkedin_url (string — full LinkedIn profile URL if found. Empty if not.)
- location (string — city, state from bio or post content. E.g. "San Francisco, CA". Empty if unknown.)
- raw_signal (string — the full post text showing product/raise/founder activity)
- source (string: always "Twitter/X")
- links (array of strings — include post URL, any company links found)

Do NOT include @fdotinc or @hthieblot as leads. Focus on the people THEY interact with."""


# ── X API client (primary mode) ──────────────────────────────────────────

class XApiClient:
    """Thin wrapper around X API v2 endpoints using Bearer Token auth."""

    def __init__(self, bearer_token: str):
        self._headers = {"Authorization": f"Bearer {bearer_token}"}
        self._available = True

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        if not self._available:
            return None
        url = f"{X_API_BASE}{path}"
        try:
            resp = httpx.get(url, headers=self._headers, params=params, timeout=15)
            if resp.status_code == 402:
                print("    X API requires payment upgrade — falling back to DuckDuckGo")
                self._available = False
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 402:
                print("    X API requires payment upgrade — falling back to DuckDuckGo")
                self._available = False
            else:
                print(f"    [X API ERROR] {path}: {e}")
            return None
        except Exception as e:
            print(f"    [X API ERROR] {path}: {e}")
            return None

    def resolve_user_id(self, username: str) -> str | None:
        data = self._get(f"/users/by/username/{username}")
        if data and "data" in data:
            return data["data"]["id"]
        return None

    def get_recent_tweets(self, user_id: str, max_results: int = 10) -> list[dict]:
        data = self._get(
            f"/users/{user_id}/tweets",
            params={
                "max_results": max_results,
                "tweet.fields": "created_at,public_metrics,entities",
            },
        )
        if data and "data" in data:
            return data["data"]
        return []

    def search_recent(self, query: str, max_results: int = 10) -> list[dict]:
        data = self._get(
            "/tweets/search/recent",
            params={
                "query": query,
                "max_results": max_results,
                "tweet.fields": "created_at,public_metrics,entities,author_id,conversation_id",
            },
        )
        if data and "data" in data:
            return data["data"]
        return []

    @property
    def is_available(self) -> bool:
        return self._available


# ── DuckDuckGo fallback ──────────────────────────────────────────────────

def _extract_x_post_urls(results: list[dict]) -> list[str]:
    urls: set[str] = set()
    for r in results:
        text = f"{r.get('title', '')} {r.get('snippet', '')} {r.get('url', '')}"
        for m in X_POST_URL_RE.finditer(text):
            urls.add(m.group(0))
    return list(urls)


def _search_ddg(queries: list[str], seen_urls: set[str], label: str) -> list[dict]:
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


def _monitor_via_ddg() -> list[dict]:
    """Fallback: search DuckDuckGo for monitored account activity."""
    print("  Using DuckDuckGo fallback...")
    all_results: list[dict] = []
    seen_urls: set[str] = set()

    p1 = _search_ddg(HTHIEBLOT_POST_QUERIES, seen_urls, "Phase 1 — @hthieblot posts")
    all_results.extend(p1)

    p1b = _search_ddg(FDOTINC_QUERIES, seen_urls, "Phase 1b — @fdotinc posts")
    all_results.extend(p1b)

    p2 = _search_ddg(HTHIEBLOT_MENTION_QUERIES, seen_urls, "Phase 2 — mentions of @hthieblot")
    all_results.extend(p2)

    # Phase 3: extract post URLs, search for replies
    hthieblot_post_urls = _extract_x_post_urls(p1 + p1b)
    if hthieblot_post_urls:
        print(f"    Found {len(hthieblot_post_urls)} @hthieblot post URLs, searching for replies...")
        for pu in hthieblot_post_urls[:5]:
            post_id_match = re.search(r'/status/(\d+)', pu)
            if post_id_match:
                pid = post_id_match.group(1)
                for reply_q in [f'site:x.com "{pid}"', f'"{pid}" x.com']:
                    try:
                        batch = web_search(reply_q, max_results=5)
                        for r in batch:
                            url = r.get("url", "")
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                all_results.append(r)
                        time.sleep(0.4)
                    except Exception:
                        continue

    p4 = _search_ddg(HTHIEBLOT_REPLY_QUERIES, seen_urls, "Phase 4 — @hthieblot replies")
    all_results.extend(p4)

    p5 = _search_ddg(CONTEXT_QUERIES, seen_urls, "Phase 5 — context searches")
    all_results.extend(p5)

    print(f"  Total: {len(all_results)} results from DuckDuckGo")
    return all_results


def _format_for_llm(tweets_or_results: list[dict]) -> str:
    """Format tweets (X API) or search results (DDG) into a uniform text block."""
    lines = []
    for item in tweets_or_results:
        # X API tweet format
        if "text" in item:
            tid = item.get("id", "")
            text = item.get("text", "")
            source = item.get("_source", "")
            handle = item.get("_from_handle", "")
            metrics = item.get("public_metrics", {})
            direction = ""
            if source == "mention":
                direction = f"[Mention of @{handle}]"
            elif source == "own_post":
                direction = f"[Post by @{handle}]"
            elif source == "keyword_signal":
                direction = "[Signal match]"
            post_url = f"https://x.com/{handle}/status/{tid}" if handle else f"https://x.com/i/web/status/{tid}"
            likes = metrics.get("like_count", 0) if isinstance(metrics, dict) else 0
            replies = metrics.get("reply_count", 0) if isinstance(metrics, dict) else 0
            lines.append(
                f"{direction}\nText: {text}\nURL: {post_url}\nLikes: {likes} | Replies: {replies}\n"
            )
        # DuckDuckGo result format
        else:
            lines.append(
                f"[Web Result]\nTitle: {item.get('title', '')}\nSnippet: {item.get('snippet', '')}\nURL: {item.get('url', '')}\n"
            )
    return "\n---\n".join(lines)


# ── Main agent ───────────────────────────────────────────────────────────

class SocialMonitor(BaseAgent):
    """Monitors X accounts for founder signals — X API v2 with DuckDuckGo fallback."""

    default_model = "deepseek-chat"

    def __init__(self, model: str | None = None):
        super().__init__(model)
        self.xapi = XApiClient(settings.X_BEARER_TOKEN) if settings.X_BEARER_TOKEN else None

    def monitor(self) -> list[Lead]:
        """Fetch data from X API (primary) or DuckDuckGo (fallback), extract leads."""
        if not settings.X_BEARER_TOKEN:
            print("  [SKIP] No X_BEARER_TOKEN configured")
            return []

        print("  Fetching data via X API v2...")
        all_items: list[dict] = []
        seen_ids: set[str] = set()

        # ── Try X API v2 ──────────────────────────────────────────────────
        user_map: dict[str, str] = {}
        for handle in MONITORED_HANDLES:
            uid = self.xapi.resolve_user_id(handle) if self.xapi else None
            if uid:
                user_map[handle] = uid
                print(f"    Resolved @{handle} -> ID {uid}")
            else:
                print(f"    Could not resolve @{handle}")

        # If X API worked, fetch tweets
        if self.xapi and (user_map or self.xapi.is_available):
            for handle, uid in user_map.items():
                tweets = self.xapi.get_recent_tweets(uid, max_results=10)
                for t in tweets:
                    tid = t.get("id", "")
                    if tid and tid not in seen_ids:
                        seen_ids.add(tid)
                        t["_from_handle"] = handle
                        t["_source"] = "own_post"
                        all_items.append(t)
                print(f"    Fetched {len(tweets)} tweets from @{handle}")
                time.sleep(0.5)

            if self.xapi and self.xapi.is_available:
                for handle in MONITORED_HANDLES:
                    query = f"@{handle} -from:{handle}"
                    mentions = self.xapi.search_recent(query, max_results=10)
                    for t in mentions:
                        tid = t.get("id", "")
                        if tid and tid not in seen_ids:
                            seen_ids.add(tid)
                            t["_from_handle"] = handle
                            t["_source"] = "mention"
                            all_items.append(t)
                    print(f"    Found {len(mentions)} mentions of @{handle}")
                    time.sleep(0.5)

                signal_queries = [
                    f'"we got into" fdotinc',
                    f'"we raised" fdotinc',
                    f'"just launched" fdotinc',
                    f'"building" hthieblot',
                    f'"fdotinc" "San Francisco" startup',
                    f'"hthieblot" raise OR seed OR pre-seed',
                ]
                for q in signal_queries:
                    results = self.xapi.search_recent(q, max_results=5)
                    for t in results:
                        tid = t.get("id", "")
                        if tid and tid not in seen_ids:
                            seen_ids.add(tid)
                            t["_source"] = "keyword_signal"
                            all_items.append(t)
                    time.sleep(0.3)

        # ── Fall back to DuckDuckGo if X API returned nothing ─────────────
        if not all_items:
            ddg_results = _monitor_via_ddg()
            all_items.extend(ddg_results)

        if not all_items:
            return []

        # ── LLM extraction ────────────────────────────────────────────────
        formatted = _format_for_llm(all_items)

        response = self._call(
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Find founder leads from these social media results:\n\n{formatted}",
                }
            ],
        )

        try:
            data = extract_json(response)
        except Exception as e:
            print(f"  [ERROR] Failed to parse social monitor output: {e}")
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
                        source=Source.X,
                        links=links,
                        location=item.get("location", "") or "",
                    )
                )
            except Exception as e:
                print(f"  [WARN] Skipping lead: {e}")

        print(f"  Extracted {len(leads)} leads from social monitoring")
        return leads

    def demo(self) -> list[Lead]:
        """Return demo leads from social monitoring for testing."""
        return [
            Lead(
                founder_name="David Park",
                company="Agentic",
                raw_signal="David Park replying to @fdotinc: 'building AI agents for sales outreach in SF, launching beta next month'",
                source=Source.X,
                links=["https://x.com/davidpark"],
            ),
            Lead(
                founder_name="Maya Rodriguez",
                company="TruStat",
                raw_signal="@hthieblot liked Maya's post: 'just raised $1.2M pre-seed for AI-native statistical modeling. SF-based, hiring.'",
                source=Source.X,
                links=["https://x.com/mayarodriguez"],
            ),
        ]
