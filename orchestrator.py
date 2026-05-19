"""Pipeline orchestrator -- runs the 4-agent dealflow nightly."""

from datetime import datetime

from config import settings
from models import Lead
from agents.signal_scanner import SignalScanner
from agents.social_monitor import SocialMonitor
from agents.linkedin_monitor import LinkedInMonitor
from agents.qualifier import Qualifier
from agents.enricher import Enricher
from agents.outreach_drafter import OutreachDrafter


class Orchestrator:
    """Orchestrates the nightly dealflow pipeline."""

    def __init__(self):
        self.scanner = SignalScanner(model=settings.SIGNAL_SCANNER_MODEL)
        self.social_monitor = SocialMonitor(model=settings.SIGNAL_SCANNER_MODEL)
        self.linkedin_monitor = LinkedInMonitor(model=settings.SIGNAL_SCANNER_MODEL)
        self.qualifier = Qualifier(model=settings.QUALIFIER_MODEL)
        self.enricher = Enricher(model=settings.ENRICHER_MODEL)
        self.drafter = OutreachDrafter(model=settings.OUTREACH_MODEL)
        self.leads: list[Lead] = []

    def run_demo(self) -> list[Lead]:
        """Run pipeline with fully self-contained demo data (no API calls)."""
        print("=" * 50)
        print("DEALFLOW PIPELINE -- DEMO MODE")
        print("=" * 50)

        # Stage 1: Load demo signals (no API call)
        print("\n[1/6] Signal Scanner (DeepSeek) -- loading demo data")
        raw = self.scanner.demo()
        print(f"  -> {len(raw)} raw signals loaded")

        # Stage 2: Social Monitor demo data
        print("[2/6] Social Monitor (DeepSeek) -- loading demo data")
        social_raw = self.social_monitor.demo()
        print(f"  -> {len(social_raw)} social signals loaded")

        # Stage 3: LinkedIn Monitor demo data
        print("[3/6] LinkedIn Monitor (DeepSeek) -- loading demo data")
        linkedin_raw = self.linkedin_monitor.demo()
        print(f"  -> {len(linkedin_raw)} LinkedIn signals loaded\n")
        raw = raw + social_raw + linkedin_raw

        # Stage 4: Demo scoring (no API call)
        print("[4/6] Qualifier (DeepSeek) -- scoring leads (demo)")
        demo_scores = {
            "Sarah Chen": (9, "YC S24, building AI code review with Claude. Raised $3M seed. Strong sector fit."),
            "Marcus Johnson": (8, "AI-native data tool just launched on Product Hunt. Pre-seed, SF-based, team of 3."),
            "Priya Patel": (8, "Vertical AI agent for DevOps. YC W25, raising seed. Austin-based technical founder."),
            "Alex Kim": (7, "AI fintech in beta with 5k users. NYC-based, pre-seed, team of 2. Strong traction for stage."),
            "Jordan Taylor": (7, "No-code ML platform. SF-based, $1.2M pre-seed, team of 4. Good sector but early."),
            "Emily Zhang": (7, "AI compliance agent. $1.5M pre-seed, female founder in Seattle. Niche but defensible."),
            "Ryan O'Brien": (6, "Prompt management platform. LA-based solo founder. Useful tool but crowded space."),
            "Neha Gupta": (9, "AI medical documentation. YC W24, HIPAA compliant, 10 hospital pilots. Strong traction."),
            "David Park": (8, "Building AI sales agents in SF. Beta launching next month. Strong founder-market fit."),
            "Maya Rodriguez": (8, "AI-native statistical modeling. Raised $1.2M pre-seed. SF-based, hiring. Good sector fit."),
            "Rohan Mehta": (8, "AI-native call summarization for sales. $2M pre-seed, SF-based. Strong traction signal."),
            "Sophia Tran": (7, "AI guardrails for enterprise LLMs. YC W25, NYC-based, team of 3. Good sector but early."),
        }
        qualified = []
        for lead in raw:
            if lead.founder_name in demo_scores:
                lead.score, lead.score_rationale = demo_scores[lead.founder_name]
                if lead.score >= 7:
                    qualified.append(lead)
        qualified.sort(key=lambda l: l.score, reverse=True)
        self.leads = qualified
        print(f"  -> {len(self.leads)} qualified leads\n")

        # Stage 5: Demo enrichment (no API call)
        print("[5/6] Enricher (DeepSeek) -- building one-pagers (demo)")
        demo_enrichments = {
            "Sarah Chen": {
                "description": "Lumos AI is an AI-powered code review platform that integrates with GitHub. Uses Claude to catch bugs, security issues, and style violations before human review.",
                "location": "San Francisco, CA",
                "is_raising": "No",
                "raise_amount": "$3M seed",
                "raise_details": "Raised $3M seed from a16z. Not actively raising.",
                "previous_investors": ["a16z"],
                "traction": "200+ beta users, growing 30% MoM",
                "revenue": "",
                "lois": "",
                "user_growth": "30% MoM",
                "health_indicators": "200+ beta users, invite-only waitlist",
                "why_invest": "Strong founder-market fit — Sarah built the same problem at GitHub Copilot, and the product fills a clear gap between linters and human code review.",
            },
            "Marcus Johnson": {
                "description": "DataWeave is an AI-native data transformation platform with a natural language interface, making ETL accessible to non-technical users.",
                "location": "San Francisco, CA",
                "is_raising": "Yes",
                "raise_amount": "$1.5M pre-seed",
                "raise_details": "Pre-seed, looking to raise $1.5M.",
                "previous_investors": [],
                "traction": "Launched on Product Hunt (#4 product of day), 500+ waitlist signups",
                "revenue": "",
                "lois": "",
                "user_growth": "",
                "health_indicators": "#4 Product Hunt product of the day",
                "why_invest": "Timely wedge into the $10B data transformation market — no-code ETL with AI is underserved and Marcus has deep domain expertise from Stitch.",
            },
            "Priya Patel": {
                "description": "AgentOps is a vertical AI agent that automates incident response and on-call management for DevOps teams.",
                "location": "Austin, TX",
                "is_raising": "Yes",
                "raise_amount": "$2M seed",
                "raise_details": "YC W25, looking for $2M seed.",
                "previous_investors": ["YC"],
                "traction": "Piloting with 5 mid-market companies, $80k ARR",
                "revenue": "$80k ARR",
                "lois": "",
                "user_growth": "",
                "health_indicators": "5 paid pilots with mid-market companies",
                "why_invest": "Vertical AI agent for DevOps has clear ROI story — Priya's SRE background at HashiCorp and the YC network give them distribution advantage in a crowded space.",
            },
            "Alex Kim": {
                "description": "FinChat is an AI-native personal finance assistant that helps users track, budget, and optimize spending via natural language.",
                "location": "New York, NY",
                "is_raising": "Yes",
                "raise_amount": "$1M pre-seed",
                "raise_details": "Pre-seed, raising $1M from angels.",
                "previous_investors": [],
                "traction": "5k users, 40% WoW growth, $15k MRR",
                "revenue": "$15k MRR",
                "lois": "",
                "user_growth": "40% WoW",
                "health_indicators": "5k users on public beta (iOS), strong organic growth",
                "why_invest": "40% WoW growth demonstrates clear product-market fit in AI-native fintech — a massive TAM where incumbents lack conversational UX.",
            },
            "Jordan Taylor": {
                "description": "VibeML is a no-code platform for building and deploying ML models with a drag-and-drop interface and automated infrastructure.",
                "location": "San Francisco, CA",
                "is_raising": "No",
                "raise_amount": "$1.2M pre-seed",
                "raise_details": "Raised $1.2M pre-seed from angels.",
                "previous_investors": ["Angel investors"],
                "traction": "100+ signups since beta, $500k ARR from 10 SMB customers",
                "revenue": "$500k ARR",
                "lois": "",
                "user_growth": "",
                "health_indicators": "10 paying SMB customers with $500k ARR on a pre-seed budget",
                "why_invest": "No-code ML platform has strong unit economics ($50k avg ACV) and Jordan's Meta ML pedigree de-risks the technical execution.",
            },
            "Emily Zhang": {
                "description": "ComplyAI is an AI compliance agent that automates SOC2, HIPAA, and GDPR documentation for startups.",
                "location": "Seattle, WA",
                "is_raising": "No",
                "raise_amount": "$1.5M pre-seed",
                "raise_details": "Raised $1.5M pre-seed from a Berlin-based VC.",
                "previous_investors": ["Berlin-based VC"],
                "traction": "20 paying customers, $300k ARR, 98% retention",
                "revenue": "$300k ARR",
                "lois": "",
                "user_growth": "",
                "health_indicators": "98% customer retention, 20 paying customers",
                "why_invest": "Perfect timing as AI adoption drives compliance needs — 98% retention proves stickiness, and Stripe compliance background gives Emily unique domain authority.",
            },
            "Neha Gupta": {
                "description": "MedSynth is an AI-native medical documentation platform that transcribes and structures clinical notes in real-time, HIPAA compliant.",
                "location": "San Francisco, CA",
                "is_raising": "No",
                "raise_amount": "$2.5M raised",
                "raise_details": "YC W24, Series A inbound, $2.5M raised to date.",
                "previous_investors": ["YC"],
                "traction": "Piloting with 10 hospitals, 50k+ notes processed, HIPAA compliant",
                "revenue": "",
                "lois": "10 hospital pilots",
                "user_growth": "",
                "health_indicators": "50k+ clinical notes processed, enterprise-grade HIPAA compliance",
                "why_invest": "MD/PhD founder + former Epic engineer co-founder is a dream team for healthcare AI — 10 hospital pilots at pre-seed is exceptional traction with deep moats from regulatory compliance.",
            },
            "David Park": {
                "description": "Agentic is building AI-powered sales outreach agents that automate personalized cold email and LinkedIn sequences.",
                "location": "San Francisco, CA",
                "is_raising": "Yes",
                "raise_amount": "$1.5M pre-seed",
                "raise_details": "Pre-seed, looking to raise $1.5M. Beta launching next month.",
                "previous_investors": [],
                "traction": "10 beta users, $50k ARR from early pilot",
                "revenue": "$50k ARR",
                "lois": "",
                "user_growth": "",
                "health_indicators": "Revenue-generating pilot before public launch",
                "why_invest": "Sales outreach AI is a massive market and David's combined Salesforce + ML background is the exact profile needed to execute on the AI sales agent thesis.",
            },
            "Maya Rodriguez": {
                "description": "TruStat is an AI-native statistical modeling platform that lets data scientists describe analyses in natural language.",
                "location": "San Francisco, CA",
                "is_raising": "No",
                "raise_amount": "$1.2M pre-seed",
                "raise_details": "Raised $1.2M pre-seed. Actively hiring SF-based engineers.",
                "previous_investors": ["Angel investors"],
                "traction": "5 enterprise trials active",
                "revenue": "",
                "lois": "",
                "user_growth": "",
                "health_indicators": "5 enterprise trial deployments",
                "why_invest": "PhD-level statistical rigor combined with natural language UX creates a defensible product — replacing SPSS/SAS workflows with AI is a clear wedge into the $5B statistical software market.",
            },
            "Rohan Mehta": {
                "description": "KrispAI is an AI-native call summarization platform for sales teams. Transcribes sales calls, auto-generates CRM notes, and surfaces action items.",
                "location": "San Francisco, CA",
                "is_raising": "No",
                "raise_amount": "$2M pre-seed",
                "raise_details": "Raised $2M pre-seed. Actively hiring founding engineers in SF.",
                "previous_investors": [],
                "traction": "5 design partners in beta",
                "revenue": "",
                "lois": "",
                "user_growth": "",
                "health_indicators": "5 design partners, $2M raised at pre-seed",
                "why_invest": "Gong product background gives Rohan insider understanding of the sales intelligence space — KrispAI is an AI-native rearchitecture of a category Gong proved exists.",
            },
            "Sophia Tran": {
                "description": "GuardianML provides AI guardrails and safety layers for enterprise LLM deployments, monitoring inputs, outputs, and enforcing policy boundaries.",
                "location": "New York, NY",
                "is_raising": "Yes",
                "raise_amount": "Seed round",
                "raise_details": "YC W25 (standard $500k deal). Looking for seed round.",
                "previous_investors": ["YC"],
                "traction": "Early prototype with 2 pilot customers",
                "revenue": "",
                "lois": "",
                "user_growth": "",
                "health_indicators": "2 pilot customers in YC W25 batch",
                "why_invest": "Enterprise LLM guardrails are becoming non-negotiable as AI adoption scales — YC backing and Scale AI pedigree position GuardianML well in the emerging AI safety layer market.",
            },
        }
        for i, lead in enumerate(self.leads, 1):
            print(f"  [{i}/{len(self.leads)}] {lead.founder_name} -- {lead.company}")
            e = demo_enrichments.get(lead.founder_name, {})
            if e:
                lead.description = e.get("description", "")
                lead.summary = e.get("description", "")
                lead.location = e.get("location", "")
                lead.is_raising = e.get("is_raising", "")
                lead.raise_amount = e.get("raise_amount", "")
                lead.raise_details = e.get("raise_details", "")
                lead.previous_investors = e.get("previous_investors", [])
                lead.traction = e.get("traction", "")
                lead.revenue = e.get("revenue", "")
                lead.lois = e.get("lois", "")
                lead.user_growth = e.get("user_growth", "")
                lead.health_indicators = e.get("health_indicators", "")
                lead.why_invest = e.get("why_invest", "")
                lead.enriched_data = (
                    f"Company Overview: {e['description']}\n"
                    f"Location: {e['location']}\n"
                    f"Traction: {e['traction']}\n"
                    f"Revenue: {e['revenue']}\n"
                    f"User Growth: {e['user_growth']}\n"
                    f"Actively Raising: {e['is_raising']}\n"
                    f"Raise Amount: {e['raise_amount']}\n"
                    f"Raise Details: {e['raise_details']}\n"
                    f"Previous Investors: {', '.join(e['previous_investors']) if e['previous_investors'] else 'None'}\n"
                    f"Health Indicators: {e['health_indicators']}\n"
                    f"Why Invest: {e['why_invest']}"
                )
        print(f"  -> {len(self.leads)} leads enriched\n")

        # Stage 6: Demo outreach (no API call)
        print("[6/6] Outreach Drafter (DeepSeek) -- writing messages (demo)")
        demo_outreach = {
            "Sarah Chen": "Hey Sarah, saw Lumos AI is using Claude for code review -- love the approach of catching "
                         "bugs before human review. The 30% MoM growth says you're onto something real. Would love "
                         "to connect -- we back AI-native devtools and I think we could add value beyond just capital. "
                         "Free for a quick chat next week?",
            "Marcus Johnson": "Hey Marcus, DataWeave's PH launch was impressive. The natural language ETL angle is "
                            "something we've been tracking closely -- feels like the right abstraction for modern data teams. "
                            "Would love to hear more about your roadmap. Got time for a brief call?",
            "Priya Patel": "Hey Priya, AgentOps sounds like exactly what the DevOps world needs. Coming from "
                          "HashiCorp, you must have felt the incident response pain firsthand. Would love to chat "
                          "about what you're building and how we might help. Free for coffee in Austin?",
            "Alex Kim": "Alex, FinChat's 40% WoW growth is hard to ignore. The AI-native fintech angle is exactly "
                       "what we look for. Would love to connect and hear about your vision for the product. "
                       "Got 15 minutes this week?",
            "Jordan Taylor": "Hey Jordan, VibeML's no-code ML platform is a solid bet -- making ML accessible is "
                            "the right problem to solve. Would love to learn more about your go-to-market strategy "
                            "and see if we can be helpful. Quick chat sometime?",
            "Emily Zhang": "Emily, ComplyAI is brilliantly timed. Every startup we talk to is dreading SOC2 -- "
                         "automating it is a clear value prop. 98% retention says it all. Would love to connect "
                         "and discuss how we might partner. Free next week?",
            "Neha Gupta": "Neha, MedSynth is tackling one of healthcare's most persistent pain points. The 10-hospital "
                         "pilot pipeline is seriously impressive for this space. Would love to chat about your "
                         "Series A plans and see if there's alignment. Coffee sometime?",
            "David Park": "Hey David, saw you're building AI sales agents in SF — love the focus on outreach automation. "
                         "Beta launching next month is exciting. Would love to connect and hear more about your "
                         "go-to-market plans. Free for a chat?",
            "Maya Rodriguez": "Maya, congrats on the $1.2M pre-seed for TruStat! AI-native statistical modeling is a "
                             "space we're tracking closely. Would love to learn more about what you're building "
                             "and see if there's alignment. Coffee in SF?",
            "Rohan Mehta": "Rohan, saw KrispAI's $2M pre-seed — AI-native call summarization for sales is a smart wedge. "
                          "Your background at Gong makes this a natural fit. Would love to connect and hear about "
                          "your roadmap. Free for a quick chat?",
            "Sophia Tran": "Sophia, GuardianML sounds like exactly what enterprise LLM adopters need right now. "
                          "YC W25 and already piloting with customers — strong signal. Would love to learn more "
                          "about your seed plans. Coffee in NYC?",
        }
        for i, lead in enumerate(self.leads, 1):
            print(f"  [{i}/{len(self.leads)}] {lead.founder_name}")
            msg = demo_outreach.get(lead.founder_name, "")
            if msg:
                lead.outreach_message = msg
        print(f"  -> {len(self.leads)} outreach messages drafted\n")

        return self.leads

    def run(self) -> list[Lead]:
        """Run the full pipeline with live web search and Claude API calls."""
        print("=" * 50)
        print("DEALFLOW PIPELINE -- LIVE MODE")
        print("=" * 50)

        # Stage 1a: Web Signal Scanner
        print("\n[1/6] Signal Scanner (DeepSeek) -- scanning web")
        try:
            web_leads = self.scanner.scan(settings.KEYWORDS)
        except Exception as e:
            print(f"  [ERROR] Signal scanning failed: {e}")
            web_leads = []
        print(f"  -> {len(web_leads)} raw signals from web scan\n")

        # Stage 1b: Social Monitor (targeted X account monitoring)
        print("[2/6] Social Monitor (DeepSeek) -- monitoring @fdotinc and @hthieblot")
        try:
            social_leads = self.social_monitor.monitor()
        except Exception as e:
            print(f"  [ERROR] Social monitoring failed: {e}")
            social_leads = []
        print(f"  -> {len(social_leads)} raw signals from social monitoring\n")

        # Stage 2b: LinkedIn Monitor
        print("[3/6] LinkedIn Monitor (DeepSeek) -- monitoring LinkedIn")
        try:
            linkedin_leads = self.linkedin_monitor.monitor()
        except Exception as e:
            print(f"  [ERROR] LinkedIn monitoring failed: {e}")
            linkedin_leads = []
        print(f"  -> {len(linkedin_leads)} raw signals from LinkedIn\n")

        self.leads = web_leads + social_leads + linkedin_leads

        if not self.leads:
            print("  No leads from web scan or social monitoring. Skipping remaining stages.")
            return self.leads

        # Stage 4: Qualifier
        print("[4/6] Qualifier (DeepSeek) -- scoring leads")
        try:
            self.leads = self.qualifier.qualify(self.leads)
        except Exception as e:
            print(f"  [ERROR] Qualification failed: {e}")
            return self.leads
        print(f"  -> {len(self.leads)} qualified leads\n")

        if not self.leads:
            print("  No qualified leads. Skipping enrichment and outreach.")
            self._write_report()
            return self.leads

        # Stage 5: Enricher
        print("[5/6] Enricher (DeepSeek) -- building one-pagers")
        qualified = self.leads
        for i, lead in enumerate(qualified, 1):
            print(f"  [{i}/{len(qualified)}] {lead.founder_name} -- {lead.company}")
            try:
                lead = self.enricher.enrich(lead)
            except Exception as e:
                print(f"    [ERROR] Enrichment failed: {e}")
        print(f"  -> {len(qualified)} leads enriched\n")

        # Stage 6: Outreach Drafter
        print("[6/6] Outreach Drafter (DeepSeek) -- writing messages")
        for i, lead in enumerate(qualified, 1):
            print(f"  [{i}/{len(qualified)}] {lead.founder_name}")
            try:
                lead = self.drafter.draft(lead)
            except Exception as e:
                print(f"    [ERROR] Outreach drafting failed: {e}")
        print(f"  -> {len(qualified)} outreach messages drafted\n")

        self.leads = qualified
        self.leads.sort(key=lambda l: l.score, reverse=True)
        return self.leads

    def write_report(self):
        """Write leads to leads.md and archive to leads/ directory."""
        self._write_report(settings.MAX_LEADS_PER_RUN)

    def _write_report(self, max_leads: int = 25):
        now = datetime.now()
        lines = [
            f"# Dealflow Report -- {now.strftime('%Y-%m-%d')}",
            "",
            f"**Generated:** {now.strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Pipeline:** 6 agents (Scanner + Social + LinkedIn + Qualifier + Enricher + Drafter), {len(self.leads)} qualified leads",
            "",
            "---",
            "",
        ]

        if not self.leads:
            lines.append("No qualified leads found this run.")
        else:
            for idx, lead in enumerate(self.leads[:max_leads], 1):
                lines.append(f"## {idx}. {lead.founder_name} -- {lead.company} (Score: {lead.score}/10)")
                lines.append("")
                if lead.tagline:
                    lines.append(f"**Tagline:** {lead.tagline}")
                lines.append(f"**Source:** {lead.source.value}")
                if lead.raw_signal:
                    lines.append(f"**Signal:** {lead.raw_signal}")
                if lead.score_rationale:
                    lines.append(f"**Why:** {lead.score_rationale}")
                if lead.description:
                    lines.append(f"**Description:** {lead.description}")
                if lead.links:
                    lines.append("**Links:**")
                    for link in lead.links:
                        lines.append(f"- {link}")
                if lead.location:
                    lines.append(f"**Location:** {lead.location}")
                if lead.is_raising or lead.raise_amount or lead.raise_details or lead.previous_investors:
                    lines.append("**General Information:**")
                    if lead.is_raising:
                        lines.append(f"- Raising: {lead.is_raising}")
                    if lead.raise_amount:
                        lines.append(f"- Amount: {lead.raise_amount}")
                    if lead.raise_details:
                        lines.append(f"- Details: {lead.raise_details}")
                    if lead.previous_investors:
                        lines.append(f"- Previous Investors: {', '.join(lead.previous_investors)}")
                if lead.traction or lead.revenue or lead.lois or lead.user_growth or lead.health_indicators:
                    lines.append("**Metrics:**")
                    if lead.traction:
                        lines.append(f"- Traction: {lead.traction}")
                    if lead.revenue:
                        lines.append(f"- Revenue: {lead.revenue}")
                    if lead.lois:
                        lines.append(f"- LOIs: {lead.lois}")
                    if lead.user_growth:
                        lines.append(f"- User Growth: {lead.user_growth}")
                    if lead.health_indicators:
                        lines.append(f"- Other: {lead.health_indicators}")
                if lead.why_invest:
                    lines.append(f"**Why Invest:** {lead.why_invest}")
                if lead.outreach_message:
                    lines.append("**Outreach:**")
                    lines.append(f"> {lead.outreach_message}")
                lines.append("")
                lines.append("---")
                lines.append("")

        content = "\n".join(lines)

        # Write main file
        with open("leads.md", "w", encoding="utf-8") as f:
            f.write(content)

        # Archive daily
        from pathlib import Path
        archive_dir = Path("leads")
        archive_dir.mkdir(exist_ok=True)
        archive_path = archive_dir / f"leads-{now.strftime('%Y-%m-%d')}.md"
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"\n  Report written to leads.md and {archive_path}")
