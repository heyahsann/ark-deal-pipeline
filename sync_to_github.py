#!/usr/bin/env python3
"""Sync pipeline leads to ark-deal-pipeline deals.json.

Merges new leads from leads.md into the GitHub repo's existing deals.json,
deduplicating by company name (case-insensitive) and preserving manual entries.

Usage:
    python sync_to_github.py                   # show merge preview (dry-run)
    python sync_to_github.py --out data/deals.json  # write to local file
    python sync_to_github.py --push             # push to GitHub via API
    python sync_to_github.py --push --no-dry-run   # force push without preview
"""

import argparse
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from config import settings

DEALS_RAW_URL = f"https://raw.githubusercontent.com/{settings.GITHUB_REPO}/{settings.GITHUB_BRANCH}/data/deals.json"
DEALS_API_URL = f"https://api.github.com/repos/{settings.GITHUB_REPO}/contents/data/deals.json"
LEADS_MD_PATH = "leads.md"

# Fields present in the new deals.json schema
DEAL_FIELDS = [
    "id", "company", "tagline", "description", "stage", "status",
    "conviction", "category", "location", "founders", "website",
    "linkedin", "email", "source", "firstContact",
    "nextAction", "accelerator", "watchouts", "currentStatus",
    "generalInfo", "metrics", "whyInvest",
]


# ---------------------------------------------------------------------------
# Fetch existing deals
# ---------------------------------------------------------------------------

def fetch_deals(url: str = DEALS_RAW_URL) -> list[dict]:
    """Fetch current deals.json from GitHub raw URL."""
    req = urllib.request.Request(url, headers={"User-Agent": "ai-deal-sourcer"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  [ERROR] HTTP {e.code} fetching deals: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"  [ERROR] Network error fetching deals: {e.reason}", file=sys.stderr)
        sys.exit(1)


def load_local_deals(path: str) -> list[dict]:
    """Load deals.json from a local file."""
    p = Path(path)
    if not p.exists():
        print(f"  [WARN] {path} not found, starting fresh", file=sys.stderr)
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Parse leads.md
# ---------------------------------------------------------------------------

def parse_leads_md(path: str = LEADS_MD_PATH) -> list[dict]:
    """Parse leads.md into structured lead dicts."""
    p = Path(path)
    if not p.exists():
        print(f"  [ERROR] {path} not found -- run the pipeline first", file=sys.stderr)
        sys.exit(1)

    with open(p, encoding="utf-8") as f:
        content = f.read()

    # Split into sections by ---
    raw_sections = re.split(r"\n---\n", content)
    sections = []
    for s in raw_sections:
        s = s.strip()
        if not s:
            continue
        if re.search(r"^##\s+\d+\.", s, re.MULTILINE):
            sections.append(s)

    leads = []
    for section in sections:
        m = re.match(
            r"^##\s+\d+\.\s+(.+?)\s+--\s+(.+?)\s+\(Score:\s+(\d+)/10\)",
            section,
            re.MULTILINE,
        )
        if not m:
            continue

        lead = {
            "founder_name": m.group(1).strip(),
            "company": m.group(2).strip(),
            "score": int(m.group(3)),
        }

        def extract(label: str) -> str | None:
            p = re.compile(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", re.IGNORECASE)
            match = p.search(section)
            return match.group(1).strip() if match else None

        lead["source_label"] = extract("Source")
        lead["raw_signal"] = extract("Signal") or ""
        lead["score_rationale"] = extract("Why") or ""
        lead["tagline"] = extract("Tagline") or ""
        lead["description"] = extract("Description") or ""
        lead["location"] = extract("Location") or ""
        lead["why_invest"] = extract("Why Invest") or ""

        # Links (lines starting with "- http" within the section)
        links_m = re.findall(r"^- (https?://\S+)", section, re.MULTILINE)
        lead["links"] = links_m

        # General Information block
        gi_section = re.search(
            r"\*\*General Information:\*\*\s*(.+?)(?:\n\*\*Metrics:|$)",
            section, re.DOTALL
        )
        if gi_section:
            gi_text = gi_section.group(1)
            lead["is_raising"] = _extract_bullet(gi_text, "Raising")
            lead["raise_amount"] = _extract_bullet(gi_text, "Amount") or ""
            lead["raise_details"] = _extract_bullet(gi_text, "Details") or ""
            inv_text = _extract_bullet(gi_text, "Previous Investors") or ""
            lead["previous_investors"] = [x.strip() for x in inv_text.split(",") if x.strip()] if inv_text else []
        else:
            lead["is_raising"] = ""
            lead["raise_amount"] = ""
            lead["raise_details"] = ""
            lead["previous_investors"] = []

        # Metrics block
        metrics_section = re.search(
            r"\*\*Metrics:\*\*\s*(.+?)(?:\n\*\*Why Invest:|$)",
            section, re.DOTALL
        )
        if metrics_section:
            mtext = metrics_section.group(1)
            lead["traction"] = _extract_bullet(mtext, "Traction") or ""
            lead["revenue"] = _extract_bullet(mtext, "Revenue") or ""
            lead["lois"] = _extract_bullet(mtext, "LOIs") or ""
            lead["user_growth"] = _extract_bullet(mtext, "User Growth") or ""
            lead["health_indicators"] = _extract_bullet(mtext, "Other") or ""
        else:
            lead["traction"] = ""
            lead["revenue"] = ""
            lead["lois"] = ""
            lead["user_growth"] = ""
            lead["health_indicators"] = ""

        # Outreach block
        outreach_m = re.search(r"\*\*Outreach:\*\*\s*>\s*(.+)", section, re.DOTALL)
        lead["outreach_message"] = outreach_m.group(1).strip() if outreach_m else ""

        leads.append(lead)

    return leads


def _extract_bullet(text: str, label: str) -> str | None:
    """Extract text after a bullet label like '- Label: value'."""
    p = re.compile(rf"- {re.escape(label)}:\s*(.+)", re.IGNORECASE)
    match = p.search(text)
    return match.group(1).strip() if match else None


# ---------------------------------------------------------------------------
# Convert pipeline lead to deals.json entry
# ---------------------------------------------------------------------------

def lead_to_deal(lead: dict) -> dict:
    """Transform a pipeline lead dict into the ark-deal-pipeline format."""
    company = lead.get("company", "Unknown")
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    score = lead.get("score", 0)

    # Score -> conviction
    if score >= 9:
        conviction = "High"
    elif score >= 7:
        conviction = "Medium"
    else:
        conviction = "Watch"

    # Extract website and linkedin from links
    links = lead.get("links", [])
    website = ""
    linkedin = ""
    for link in links:
        lower = link.lower()
        if "linkedin.com" in lower:
            linkedin = link
        elif "x.com" in lower or "twitter.com" in lower:
            pass
        elif not website:
            website = link

    # Use description from pipeline (no duplication)
    description = lead.get("description", "") or ""
    if len(description) > 800:
        description = description[:797] + "..."

    # General Information
    is_raising = lead.get("is_raising", "")
    raise_amount = lead.get("raise_amount", "")
    raise_details = lead.get("raise_details", "")
    prev_inv = lead.get("previous_investors", [])

    general_info = {}
    if is_raising:
        general_info["isRaising"] = is_raising
    if raise_amount:
        general_info["raiseAmount"] = raise_amount
    if raise_details:
        general_info["raiseDetails"] = raise_details
    if prev_inv:
        general_info["previousInvestors"] = prev_inv if isinstance(prev_inv, list) else [prev_inv]

    # Metrics
    metrics = {}
    for key, label in (
        ("traction", "traction"),
        ("revenue", "revenue"),
        ("lois", "lois"),
        ("user_growth", "userGrowth"),
        ("health_indicators", "healthIndicators"),
    ):
        val = lead.get(key, "")
        if val:
            metrics[label] = val

    entry = {
        "id": slug,
        "company": company,
        "tagline": (lead.get("raw_signal", "") or "")[:120],
        "description": description,
        "stage": "Pre-seed",
        "status": "Tracking",
        "conviction": conviction,
        "category": ["AI Agents"],
        "location": lead.get("location", "") or "",
        "founders": [{"name": lead.get("founder_name", ""), "role": "Founder & CEO"}],
        "website": website,
        "linkedin": linkedin,
        "email": "",
        "source": f"ai-deal-sourcer pipeline ({lead.get('founder_name', '?')}/{company}, score: {score}/10)",
        "firstContact": datetime.now().strftime("%Y-%m"),
        "nextAction": "Initial outreach drafted via pipeline",
        "generalInfo": general_info,
        "metrics": metrics,
        "whyInvest": lead.get("why_invest", "") or "",
    }

    return entry


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

def merge_deals(
    existing: list[dict], new_leads: list[dict]
) -> tuple[list[dict], int, int, int]:
    """Merge new leads into existing deals.

    Deduplicates by company name (case-insensitive).
    Returns (merged_list, added_count, skipped_count, updated_count).
    """
    existing_map: dict[str, dict] = {}
    for d in existing:
        key = (d.get("company") or "").strip().lower()
        if key:
            existing_map[key] = d

    added = 0
    skipped = 0
    updated = 0

    # Start with existing and preserve their full data (including manual entries)
    merged = list(existing)

    for lead in new_leads:
        company = (lead.get("company") or "").strip()
        if not company:
            skipped += 1
            continue

        key = company.lower()
        if key in existing_map:
            skipped += 1
        else:
            merged.append(lead_to_deal(lead))
            existing_map[key] = merged[-1]
            added += 1

    return merged, added, skipped, updated


# ---------------------------------------------------------------------------
# Push to GitHub
# ---------------------------------------------------------------------------

def push_to_github(deals: list[dict], token: str) -> None:
    """Push updated deals.json to GitHub via the Contents API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "ai-deal-sourcer",
        "Accept": "application/vnd.github+json",
    }

    # Get current file SHA
    req = urllib.request.Request(DEALS_API_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            current = json.loads(resp.read().decode())
            sha = current["sha"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  [ERROR] Failed to get current file: HTTP {e.code}", file=sys.stderr)
        print(f"  Response: {body}", file=sys.stderr)
        sys.exit(1)

    # Prepare new content
    new_content = json.dumps(deals, indent=2, ensure_ascii=False) + "\n"
    encoded = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")

    payload = json.dumps({
        "message": "Sync new leads from ai-deal-sourcer pipeline",
        "content": encoded,
        "sha": sha,
        "branch": settings.GITHUB_BRANCH,
    }).encode("utf-8")

    req = urllib.request.Request(
        DEALS_API_URL,
        data=payload,
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            print(f"  Pushed to {settings.GITHUB_REPO}@{settings.GITHUB_BRANCH}")
            print(f"  Commit: {result['commit']['sha']}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  [ERROR] Push failed: HTTP {e.code}", file=sys.stderr)
        print(f"  Response: {body}", file=sys.stderr)
        sys.exit(1)


def push_file_to_github(local_path: str, commit_message: str, token: str) -> None:
    """Push any local file to the GitHub repo root via Contents API."""
    repo = settings.GITHUB_REPO
    branch = settings.GITHUB_BRANCH
    api_url = f"https://api.github.com/repos/{repo}/contents/{local_path}"

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "ai-deal-sourcer",
        "Accept": "application/vnd.github+json",
    }

    with open(local_path, "rb") as f:
        content_bytes = f.read()
    encoded = base64.b64encode(content_bytes).decode("utf-8")

    # Try to get SHA of existing file
    sha = None
    req = urllib.request.Request(api_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            current = json.loads(resp.read().decode())
            sha = current["sha"]
    except urllib.error.HTTPError:
        pass  # File doesn't exist yet, that's fine

    payload: dict = {
        "message": commit_message,
        "content": encoded,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=data,
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            print(f"  Pushed {local_path} to {repo}@{branch}")
            print(f"  Commit: {result['commit']['sha']}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  [ERROR] Push failed for {local_path}: HTTP {e.code}", file=sys.stderr)
        print(f"  Response: {body}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sync pipeline leads to ark-deal-pipeline deals.json"
    )
    parser.add_argument(
        "--out",
        help="Write merged deals.json to local path (e.g. data/deals.json)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push merged deals.json to GitHub via API (uses GITHUB_TOKEN from .env)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Skip the preview prompt and execute immediately",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Use a specific leads.md path instead of the default",
    )
    parser.add_argument(
        "--local",
        help="Read existing deals from a local file instead of fetching from GitHub",
    )
    args = parser.parse_args()

    # Prevent accidental pushes
    if args.push and not args.no_dry_run:
        print("DRY RUN -- pass --no-dry-run to actually push\n")

    # 1. Fetch existing deals
    if args.local:
        print(f"Reading existing deals from {args.local}...")
        existing = load_local_deals(args.local)
    else:
        print("Fetching current deals.json from GitHub...")
        existing = fetch_deals()
    print(f"  {len(existing)} existing deals\n")

    # 2. Parse leads.md
    leads_path = args.source or LEADS_MD_PATH
    leads = parse_leads_md(leads_path)
    print(f"Parsed {len(leads)} leads from {leads_path}\n")

    if not leads:
        print("No leads to sync. Exiting.")
        return

    # 3. Merge
    merged, added, skipped, updated = merge_deals(existing, leads)
    print(f"Merge results:")
    print(f"  Added:   {added}")
    print(f"  Skipped: {skipped} (already present)")
    print(f"  Total:   {len(merged)}")

    # Show what would be added
    if added > 0:
        added_deals = merged[-added:]
        print(f"\nNew deals to be added:")
        for d in added_deals:
            founder = d["founders"][0]["name"] if d["founders"] else "?"
            print(f"  + {d['company']:20s} | {d['conviction']:6s} | {founder}")

    if skipped > 0:
        skipped_names = []
        for lead in leads:
            key = (lead.get("company") or "").strip().lower()
            if key in {d.get("company", "").lower() for d in existing}:
                skipped_names.append(lead.get("company", ""))
        if skipped_names:
            print(f"\nSkipped (already in pipeline):")
            for name in skipped_names:
                print(f"  ~ {name}")

    # 4. Write / push
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"\nWritten to {out_path}")

    if args.push:
        token = settings.GITHUB_TOKEN
        if not token:
            print(
                "\n  [ERROR] GITHUB_TOKEN not set in .env",
                file=sys.stderr,
            )
            sys.exit(1)

        if args.no_dry_run:
            print("\nPushing deals.json to GitHub...")
            push_to_github(merged, token)
            print("\nPushing index.html to GitHub...")
            push_file_to_github(
                "index.html",
                "Update GitHub Pages site with new deal pipeline schema",
                token,
            )
        else:
            print(
                "\nPass --no-dry-run to push to GitHub, or --out <path> for local write"
            )

    if not args.out and not args.push:
        print(
            f"\nUse --out <path> to write locally, or --push to push to GitHub"
        )


if __name__ == "__main__":
    main()
