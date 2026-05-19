"""Job scanner agent — searches the web for VC and fund roles.

Searches LinkedIn and the broader web for investment, operations, deal
sourcing, analyst, and associate roles at VC firms and angel funds.
Saves results to jobs.md and jobs.json.
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

from agents.base import BaseAgent, extract_json
from search import web_search

# Job search queries — LinkedIn
LI_JOB_QUERIES = [
    # Venture capital roles
    'site:linkedin.com "venture capital" "analyst" hiring',
    'site:linkedin.com "venture capital" "associate" hiring',
    'site:linkedin.com "venture capital" "investment" hiring',
    'site:linkedin.com "venture capital" "operations" hiring',
    'site:linkedin.com "venture" "deal sourcing" job',
    'site:linkedin.com "venture" "partner" job',
    'site:linkedin.com "VC" "analyst" hiring',
    'site:linkedin.com "VC" "associate" job',
    'site:linkedin.com "VC" "investment" job',
    'site:linkedin.com "angel fund" "analyst" job',
    'site:linkedin.com "angel fund" "associate" job',
    'site:linkedin.com "venture" "principal" job',
    # More specific
    'site:linkedin.com/jobs "venture capital"',
    'site:linkedin.com/jobs "VC" "associate"',
    'site:linkedin.com/jobs "seed fund"',
]

# General web job queries
WEB_JOB_QUERIES = [
    'site:wellfound.com "venture" jobs',
    'site:wellfound.com "VC" jobs',
    'site:sequoiacap.com careers job',
    'site:a16z.com careers job',
    'site:accel.com careers job',
    'site:benchmark.com careers job',
    'site:greylock.com careers job',
    'site:felicis.com careers job',
    'site:usv.com careers job',
    'site:ycombinator.com jobs venture',
    '"venture capital" "we are hiring" analyst',
    '"venture capital" "job opening" associate',
    '"venture capital" "join our team" analyst',
    '"venture capital" careers associate',
    '"seed fund" hiring analyst job',
    '"early stage VC" hiring associate',
    '"angel investor" "hiring" analyst',
]

SYSTEM_PROMPT = """You are a job scanner for a venture capital deal sourcing pipeline.
You search the web for open roles at VC firms, angel funds, and investment firms.

Given web search results, extract job listings for roles like:
- Investment Analyst
- Investment Associate
- Senior Associate
- Principal
- Partner
- Venture Partner
- Deal Sourcing Associate
- Investment Operations
- Platform / Portfolio Operations
- Fund Operations
- Venture Scout
- Chief of Staff (at VC firms)

Return a JSON array of objects, each with:
- role_title (string — the exact job title, e.g. "Investment Analyst", "Venture Associate")
- firm (string — the VC firm or fund name, e.g. "Sequoia Capital", "a16z", "Y Combinator")
- location (string — the job location, or "Remote" / "Unknown")
- link (string — the direct URL to the job listing)
- date_posted (string — relative date like "Posted 2 weeks ago" or specific date if available, or "Unknown")
- source (string — "LinkedIn" or "Web")

Rules:
- Only include roles at VC firms, angel funds, seed funds, or investment firms
- Do NOT include roles at startups or operating companies (unless they are a VC's portfolio company AND the role is on the VC's investing team)
- Exclude: software engineer roles at VC firms (only investment/ops roles)
- Include: analyst, associate, principal, partner, investment, operations, platform, deal sourcing, scout roles
- If a result is not clearly a VC/fund role, exclude it
- Prioritize recently posted roles"""

JOB_FIELDS = [
    "id", "role_title", "firm", "location", "link", "date_posted",
    "source", "description", "status", "firstFound",
]


def _search_batch(queries: list[str], seen_urls: set[str], label: str) -> list[dict]:
    """Run web searches, deduplicating by URL."""
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
            print(f"    [WARN] Search failed: {e}")
            continue
    if results:
        print(f"    {label}: {len(results)} results")
    return results


class JobScanner(BaseAgent):
    """Scans for VC/fund job listings via web search."""

    default_model = "deepseek-chat"

    def scan(self) -> list[dict]:
        """Search for VC job listings, return structured list."""
        print("  Searching for VC and fund roles...")
        all_results: list[dict] = []
        seen_urls: set[str] = set()

        p1 = _search_batch(LI_JOB_QUERIES, seen_urls, "LinkedIn job queries")
        all_results.extend(p1)

        p2 = _search_batch(WEB_JOB_QUERIES, seen_urls, "Web job queries")
        all_results.extend(p2)

        print(f"  Total: {len(all_results)} job search results")

        if not all_results:
            return []

        formatted = "\n\n".join(
            f"Title: {r['title']}\nSnippet: {r.get('snippet', '')}\nURL: {r['url']}"
            for r in all_results
        )

        response = self._call(
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Extract VC/fund job listings from these search results:\n\n{formatted}",
                }
            ],
        )

        try:
            data = extract_json(response)
        except Exception as e:
            print(f"  [ERROR] Failed to parse job scanner output: {e}")
            return []

        if isinstance(data, dict):
            data = data.get("jobs") or data.get("results") or [data]
        if not isinstance(data, list):
            return []

        # Clean and normalize
        jobs = []
        seen_links: set[str] = set()
        for item in data:
            link = (item.get("link") or "").strip()
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            role = (item.get("role_title") or "").strip()
            firm = (item.get("firm") or "").strip()
            if not role or not firm:
                continue
            jobs.append({
                "id": re.sub(r"[^a-z0-9]+", "-", f"{firm}-{role}".lower()).strip("-"),
                "role_title": role,
                "firm": firm,
                "location": (item.get("location") or "Unknown").strip(),
                "link": link,
                "date_posted": (item.get("date_posted") or "Unknown").strip(),
                "source": (item.get("source") or "Web").strip(),
                "description": "",
                "status": "Active",
                "firstFound": datetime.now().strftime("%Y-%m-%d"),
            })

        # Dedup similar roles at same firm
        jobs_deduped = []
        seen_firm_roles: set[str] = set()
        for j in jobs:
            key = f"{j['firm'].lower()}|{j['role_title'].lower()}"
            if key not in seen_firm_roles:
                seen_firm_roles.add(key)
                jobs_deduped.append(j)

        print(f"  Extracted {len(jobs_deduped)} unique job listings")
        return jobs_deduped

    def write_md(self, jobs: list[dict], path: str = "jobs.md"):
        """Write jobs to a markdown report."""
        if not jobs:
            Path(path).write_text("# VC & Fund Roles\n\nNo jobs found this run.\n", encoding="utf-8")
            return

        now = datetime.now()
        lines = [
            f"# VC & Fund Roles -- {now.strftime('%Y-%m-%d')}",
            "",
            f"**Generated:** {now.strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Total roles:** {len(jobs)}",
            "",
            "---",
            "",
        ]

        for idx, job in enumerate(jobs, 1):
            lines.append(f"## {idx}. {job['role_title']} @ {job['firm']}")
            lines.append("")
            lines.append(f"**Firm:** {job['firm']}")
            lines.append(f"**Location:** {job['location']}")
            lines.append(f"**Posted:** {job['date_posted']}")
            lines.append(f"**Source:** {job['source']}")
            lines.append(f"**Link:** [{job['link']}]({job['link']})")
            lines.append("")
            lines.append("---")
            lines.append("")

        content = "\n".join(lines)
        Path(path).write_text(content, encoding="utf-8")
        print(f"  Written to {path}")

    def write_json(self, jobs: list[dict], path: str = "data/jobs.json"):
        """Write jobs to JSON file matching deals.json format."""
        # Build JSON entries matching the deals.json structure
        entries = []
        for job in jobs:
            slug = re.sub(r"[^a-z0-9]+", "-", f"{job['firm']}-{job['role_title']}".lower()).strip("-")
            entries.append({
                "id": slug,
                "role_title": job["role_title"],
                "firm": job["firm"],
                "location": job["location"],
                "link": job["link"],
                "date_posted": job["date_posted"],
                "source": job["source"],
                "description": job.get("description", ""),
                "status": job.get("status", "Active"),
                "firstFound": job.get("firstFound", datetime.now().strftime("%Y-%m-%d")),
            })

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"  Written to {path}")

    def run(self):
        """Full scan: search, extract, write outputs."""
        print("-" * 50)
        print("JOB SCANNER")
        print("-" * 50)
        jobs = self.scan()
        if jobs:
            self.write_md(jobs)
            self.write_json(jobs)
        print(f"\n  Done. {len(jobs)} jobs found.\n")
        return jobs
