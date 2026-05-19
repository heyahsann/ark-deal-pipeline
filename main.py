#!/usr/bin/env python3
"""AI Deal Sourcer -- autonomous nightly dealflow pipeline.

Usage:
    python main.py              # Full pipeline (live web search + Claude API)
    python main.py --demo       # Demo mode (no API keys needed)
    python main.py --demo --dry-run   # Print what would happen (demo only)
"""

import argparse
import sys

from orchestrator import Orchestrator


def main():
    parser = argparse.ArgumentParser(
        description="AI Deal Sourcer -- autonomous nightly dealflow pipeline"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with demo data (no API calls, uses sample leads)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print pipeline plan without executing stages",
    )
    args = parser.parse_args()

    orch = Orchestrator()

    if args.dry_run:
        print("\nPipeline Plan:")
        print("  [1/6] Signal Scanner (DeepSeek) -- scan web for signals")
        print("  [2/6] Social Monitor (DeepSeek) -- monitor @fdotinc and @hthieblot on X for founder leads")
        print("  [3/6] LinkedIn Monitor (DeepSeek) -- monitor LinkedIn for founder signals")
        print("  [4/6] Qualifier (DeepSeek) -- score leads 1-10, filter top 20%")
        print("  [5/6] Enricher (DeepSeek) -- build one-pagers per lead")
        print("  [6/6] Outreach Drafter (DeepSeek) -- write personalized cold outreach")
        print("  Output: leads/leads-YYYY-MM-DD.md + leads.md")
        print()
        return

    try:
        if args.demo:
            leads = orch.run_demo()
        else:
            leads = orch.run()

        orch.write_report()

        print("\n" + "=" * 50)
        print("PIPELINE COMPLETE")
        print("=" * 50)
        print(f"  Qualified leads: {len(leads)}")
        for lead in leads:
            print(f"  - {lead.founder_name:20s} | {lead.company:20s} | Score: {lead.score}/10")
        print()

    except KeyboardInterrupt:
        print("\n\nPipeline cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FATAL] Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
