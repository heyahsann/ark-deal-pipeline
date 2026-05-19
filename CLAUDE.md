# CLAUDE.md

## Mission
Source AI-native startup deals across X (Twitter), LinkedIn, and the web. Run autonomously every night and deliver a ranked shortlist of warm leads every morning.

## Investment Thesis
- Stage: Pre-seed and Seed
- Geography: San Francisco Bay Area and across the United States (SF, NYC, LA, Austin, Seattle)
- Sectors: AI-native SaaS, AI infrastructure, vertical AI agents, AI-native fintech
- Sweet spot: Founders building with LLMs as core product (not just a feature)
- Disqualify: AI-enabled legacy software, pure consulting, no technical co-founder

## What Makes a Strong Lead
- Founder actively posting about building on X or LinkedIn
- Product launched or in beta (Product Hunt, GitHub, landing page)
- Team size under 20, company under 2 years old
- Raising or about to raise ("we're growing", "looking for partners", "we raised")
- Based in SF, NYC, Austin, Seattle or other major US tech hubs
- Engagement from other founders or investors in their posts

## Agent Roles
- Signal Scanner (DeepSeek): scans X and LinkedIn for raw signals using keywords
- Social Monitor (DeepSeek): monitors @fdotinc and @hthieblot on X for founder leads in interactions
- LinkedIn Monitor (DeepSeek): monitors LinkedIn for founder signals from key people and signals
- Qualifier (DeepSeek): scores leads 1-10 against thesis, filters top 20%
- Enricher (DeepSeek): builds one-pager per lead -- team, product, traction, links
- Outreach Drafter (DeepSeek): writes personalized cold outreach per founder

## Keywords to Monitor
"building with Claude", "building with GPT", "AI agent", "just launched", "pre-seed", "seed round", "AI-native", "vibe coding", "we raised", "LLM", "San Francisco", "YC", "Y Combinator", "we're hiring"

## Output Format
Save results to leads.md with:
- Founder name
- Company
- Score (1-10)
- Summary
- Links
- Draft outreach message

## Commands

```bash
# Setup
cp .env.example .env     # then add DEEPSEEK_API_KEY
uv venv                  # create virtual env
uv pip install -r requirements.txt

# Run pipeline
uv run python main.py --demo            # fully self-contained demo (no API key needed)
uv run python main.py                   # live mode (needs DEEPSEEK_API_KEY in .env)
uv run python main.py --demo --dry-run  # print pipeline plan without executing

# Job scanner (standalone)
uv run python -c "from agents.job_scanner import JobScanner; JobScanner().run()"

# Sync to GitHub
uv run python sync_to_github.py --push --no-dry-run        # push deals.json
uv run python sync_jobs_to_github.py --push --no-dry-run   # push jobs.json + jobs.html
```

## Project Architecture

```
main.py                  # CLI entry point with --demo / --dry-run flags
orchestrator.py          # Pipeline orchestrator (6-stage agent workflow)
config.py                # Settings via pydantic-settings + .env
models.py                # Lead dataclass, Source enum
search.py                # Web search via DuckDuckGo (used by scanner + enricher)
agents/
  base.py                # BaseAgent (OpenAI-compatible client wrapper), extract_json helper
  signal_scanner.py      # DeepSeek -- extracts leads from web search results (or demo data)
  social_monitor.py      # DeepSeek -- monitors @fdotinc and @hthieblot on X for founder signals
  linkedin_monitor.py    # DeepSeek -- monitors LinkedIn for founder signals
  qualifier.py           # DeepSeek -- scores 1-10 against thesis, keeps >= 7
  enricher.py            # DeepSeek -- builds one-pagers per lead via search + enrichment
  outreach_drafter.py    # DeepSeek -- writes personalized cold outreach
leads.md                 # Latest report (overwritten each run)
leads/                   # Archived daily reports (leads-YYYY-MM-DD.md)
```

## Pipeline Flow
1. **Signal Scanner** runs web searches for each keyword, passes results to DeepSeek for extraction
2. **Social Monitor** searches for recent activity from @fdotinc and @hthieblot on X, extracts founder leads
3. **LinkedIn Monitor** searches LinkedIn for founder signals from key people and signal searches
4. **Qualifier** sends raw leads to DeepSeek for 1-10 scoring against thesis, filters to score >= 7
5. **Enricher** searches the web for each qualified lead, uses DeepSeek to compile a one-pager
6. **Outreach Drafter** uses DeepSeek to write personalized cold outreach per founder
7. Report written to leads.md and archived to leads/leads-YYYY-MM-DD.md

## Anti-Hallucination Rules
- Never fabricate leads — every lead must correspond to a real person and company verified via web search results
- Every lead must include at least one real, clickable URL to a verifiable source (X post, LinkedIn profile, company page, Product Hunt, article)
- If web search returns no results for a keyword, output empty results for that query — do not invent signals
- All scores (1-10) must cite specific evidence from real sources; a score without a cited source is invalid
- No inference of fundraising, traction, or team size without a direct source stating it
- In `--demo` mode, clearly label all data as simulated; never mix demo data with real-looking output

## Key Design Decisions
- DuckDuckGo for web search (no API key required), can be swapped for SerpAPI/Tavily
- Models configured via .env but default to `deepseek-chat`
- `--demo` mode uses fully self-contained mock data (no API calls of any kind)
- Live mode handles partial failures gracefully (one agent can fail without crashing the pipeline)