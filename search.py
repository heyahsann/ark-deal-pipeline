"""Web search utility using DuckDuckGo."""

import time

import ddgs as duckduckgo_search
from ddgs import DDGS


def web_search(keywords: str | list[str], max_results: int = 10) -> list[dict]:
    """Search the web for each keyword and return deduplicated results."""
    if isinstance(keywords, str):
        keywords = [keywords]

    seen_urls: set[str] = set()
    results: list[dict] = []

    with DDGS() as ddgs:
        for keyword in keywords:
            try:
                for r in ddgs.text(keyword, max_results=max_results):
                    url = r.get("href", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append(
                            {
                                "title": r.get("title", ""),
                                "snippet": r.get("body", ""),
                                "url": url,
                            }
                        )
                time.sleep(0.7)
            except Exception as e:
                print(f"  [WARN] Search failed for '{keyword}': {e}")
                continue

    return results[:50]
