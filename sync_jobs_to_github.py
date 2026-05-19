#!/usr/bin/env python3
"""Sync job listings to ark-deal-pipeline data/jobs.json + jobs.html.

Pushes both the JSON data and HTML page to the GitHub repo via API.

Usage:
    python sync_jobs_to_github.py                    # preview
    python sync_jobs_to_github.py --out data/jobs.json  # local write
    python sync_jobs_to_github.py --push --no-dry-run     # push to GitHub
"""

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request

from config import settings

GITHUB_REPO = settings.GITHUB_REPO
GITHUB_BRANCH = settings.GITHUB_BRANCH
GITHUB_TOKEN = settings.GITHUB_TOKEN

JOBS_JSON_PATH = "data/jobs.json"
JOBS_HTML_PATH = "jobs.html"

JOBS_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/data/jobs.json"
HTML_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/jobs.html"


def push_file(api_url: str, content: str, message: str, token: str):
    """Push a file to GitHub via the Contents API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "ai-deal-sourcer",
        "Accept": "application/vnd.github+json",
    }

    # Try to get current file SHA
    sha = None
    req = urllib.request.Request(api_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            current = json.loads(resp.read().decode())
            sha = current["sha"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            body = e.read().decode()
            print(f"  [WARN] Could not get current file: HTTP {e.code}", file=sys.stderr)

    # Push new content
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = json.dumps({
        "message": message,
        "content": encoded,
        "branch": GITHUB_BRANCH,
    })
    if sha:
        payload_obj = json.loads(payload)
        payload_obj["sha"] = sha
        payload = json.dumps(payload_obj)

    req = urllib.request.Request(
        api_url,
        data=payload.encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            print(f"  Pushed to {GITHUB_REPO}@{GITHUB_BRANCH}")
            print(f"  Commit: {result['commit']['sha']}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  [ERROR] Push failed: HTTP {e.code}", file=sys.stderr)
        print(f"  Response: {body}", file=sys.stderr)
        return False


def load_jobs(path: str = JOBS_JSON_PATH) -> list[dict]:
    """Load jobs from local JSON file."""
    import json as j
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        print(f"  [ERROR] {path} not found", file=sys.stderr)
        sys.exit(1)
    with open(p, encoding="utf-8") as f:
        return j.load(f)


def build_jobs_html(jobs: list[dict]) -> str:
    """Build an HTML page displaying jobs in a clean dashboard style."""
    rows = ""
    for job in jobs:
        role = job.get("role_title", "Unknown")
        firm = job.get("firm", "Unknown")
        location = job.get("location", "Unknown")
        date_posted = job.get("date_posted", "Unknown")
        link = job.get("link", "#")
        source = job.get("source", "Web")
        status = job.get("status", "Active")

        rows += f"""
        <div class="job-card">
            <div class="job-header">
                <h3>{role}</h3>
                <span class="badge badge-{status.lower()}">{status}</span>
            </div>
            <div class="job-meta">
                <span class="meta-item"><strong>{firm}</strong></span>
                <span class="meta-item">{location}</span>
                <span class="meta-item">Posted: {date_posted}</span>
                <span class="meta-item source-tag">{source}</span>
            </div>
            <a href="{link}" target="_blank" class="job-link">View Listing &rarr;</a>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VC & Fund Roles | Ark Pipeline</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0a0a0f;
    color: #e0e0e0;
    min-height: 100vh;
  }}
  .app {{
    display: flex;
    min-height: 100vh;
  }}
  .sidebar {{
    width: 240px;
    background: #111118;
    border-right: 1px solid #1e1e2a;
    padding: 24px 16px;
    flex-shrink: 0;
  }}
  .sidebar h1 {{
    font-size: 18px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 4px;
  }}
  .sidebar .subtitle {{
    font-size: 12px;
    color: #666;
    margin-bottom: 24px;
  }}
  .nav-item {{
    display: block;
    padding: 10px 12px;
    border-radius: 8px;
    color: #888;
    text-decoration: none;
    font-size: 14px;
    margin-bottom: 4px;
    transition: all 0.15s;
  }}
  .nav-item:hover {{ background: #1a1a25; color: #fff; }}
  .nav-item.active {{ background: #1e3a5f; color: #5b9aff; font-weight: 600; }}
  .main {{
    flex: 1;
    padding: 32px 40px;
  }}
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 28px;
  }}
  .header h2 {{
    font-size: 22px;
    font-weight: 600;
    color: #fff;
  }}
  .header .count {{
    background: #1e1e2a;
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 13px;
    color: #aaa;
  }}
  .job-card {{
    background: #14141e;
    border: 1px solid #1e1e2a;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 12px;
    transition: border-color 0.15s;
  }}
  .job-card:hover {{ border-color: #2a2a3e; }}
  .job-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 12px;
  }}
  .job-header h3 {{
    font-size: 16px;
    font-weight: 600;
    color: #fff;
    flex: 1;
    margin-right: 12px;
  }}
  .badge {{
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 12px;
    font-weight: 600;
    white-space: nowrap;
  }}
  .badge-active {{ background: #0d2b1d; color: #4ade80; }}
  .badge-closed {{ background: #2b0d0d; color: #f87171; }}
  .job-meta {{
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 12px;
    font-size: 13px;
    color: #999;
  }}
  .meta-item {{}}
  .source-tag {{
    background: #1e1e2a;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    color: #666;
  }}
  .job-link {{
    display: inline-block;
    font-size: 13px;
    color: #5b9aff;
    text-decoration: none;
    font-weight: 500;
  }}
  .job-link:hover {{ text-decoration: underline; }}
  .footer {{
    text-align: center;
    padding: 24px;
    color: #444;
    font-size: 12px;
  }}
</style>
</head>
<body>
<div class="app">
  <nav class="sidebar">
    <h1>Ark Pipeline</h1>
    <div class="subtitle">Dealflow Dashboard</div>
    <a href="index.html" class="nav-item">Deals</a>
    <a href="jobs.html" class="nav-item active">VC Jobs</a>
  </nav>
  <main class="main">
    <div class="header">
      <h2>VC & Fund Roles</h2>
      <span class="count">{len(jobs)} open roles</span>
    </div>
    {rows}
  </main>
</div>
<div class="footer">Updated {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M UTC')} &middot; ai-deal-sourcer</div>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Sync job listings to GitHub")
    parser.add_argument("--out", help="Write jobs.json locally (path)")
    parser.add_argument("--push", action="store_true", help="Push to GitHub via API")
    parser.add_argument("--no-dry-run", action="store_true", help="Skip preview prompt")
    args = parser.parse_args()

    if args.push and not args.no_dry_run:
        print("DRY RUN -- pass --no-dry-run to actually push\n")

    # Load jobs
    jobs = load_jobs()
    print(f"Loaded {len(jobs)} jobs from {JOBS_JSON_PATH}\n")

    if not jobs:
        print("No jobs to sync.")
        return

    # Show preview
    print("Jobs to push:")
    for j in jobs:
        print(f"  + {j['role_title']:40s} @ {j['firm']}")
    print()

    # Write locally
    if args.out:
        import json as j
        from pathlib import Path
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(j.dumps(jobs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Written to {args.out}")

    # Push to GitHub
    if args.push:
        token = GITHUB_TOKEN
        if not token:
            print("  [ERROR] GITHUB_TOKEN not set in .env", file=sys.stderr)
            sys.exit(1)

        if args.no_dry_run:
            print("\nPushing data/jobs.json...")
            jobs_json = json.dumps(jobs, indent=2, ensure_ascii=False) + "\n"
            ok = push_file(
                JOBS_API_URL,
                jobs_json,
                "Sync VC/fund job listings from ai-deal-sourcer",
                token,
            )

            if ok:
                print("\nPushing jobs.html...")
                html = build_jobs_html(jobs)
                push_file(
                    HTML_API_URL,
                    html,
                    "Add jobs.html dashboard page",
                    token,
                )
        else:
            print("\nPass --no-dry-run to push to GitHub")

    if not args.out and not args.push:
        print("Use --out <path> or --push to write/push")


if __name__ == "__main__":
    main()
