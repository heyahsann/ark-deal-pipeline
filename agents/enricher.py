from models import Lead
from agents.base import BaseAgent, extract_json
from search import web_search

SYSTEM_PROMPT = """You are an enricher for an AI startup deal sourcing pipeline.
Given a lead with basic info, compile a comprehensive one-pager.

Provide structured information about the company including:
- Company overview (what they do, AI-native angle)
- Team background (founders, technical expertise)
- Location (city, state — from LinkedIn, Crunchbase, X profile, or web search)
- Traction signals (users, revenue, partnerships)
- Product stage (idea, beta, launched)
- Fundraising status (are they actively raising? How much? From whom?)
- Previous investors (names of investors/VCs)
- Customer metrics (revenue, LOIs, user growth, other health indicators)
- Why invest / defensibility (one-liner on moat based on tech, team, market timing, and traction)

Return ONLY valid JSON with keys:
- company_overview (string)
- team_background (string)
- location (string, e.g. "San Francisco, CA" — leave empty if unknown)
- traction (string)
- product_stage (string)
- fundraising_is_raising (string: "Yes", "No", or "Unknown")
- fundraising_amount (string, e.g. "$3M seed" — empty if unknown)
- fundraising_details (string, e.g. "Led by a16z, closed Aug 2025" — empty if unknown)
- previous_investors (array of strings, empty if none)
- revenue (string, empty if unknown)
- lois (string, e.g. "5 letters of intent" — empty if unknown)
- user_growth (string, e.g. "30% MoM" — empty if unknown)
- health_indicators (string, e.g. "98% retention" — empty if unknown)
- why_invest (string — one sentence on defensibility: moat, timing, team, traction)
- links (array of strings)

Be concise but specific. Do NOT repeat company_overview anywhere else in the output.
Use web search results to extract the most accurate, verifiable information available."""


class Enricher(BaseAgent):
    default_model = "deepseek-chat"

    def enrich(self, lead: Lead) -> Lead:
        # Search for additional context
        queries = [f"{lead.founder_name} {lead.company} AI startup"]
        if lead.company and lead.company != "Unknown":
            queries.insert(0, lead.company)

        context = f"Founder: {lead.founder_name}\nCompany: {lead.company}\nSignal: {lead.raw_signal}\n"

        results = web_search(queries, max_results=5)
        if results:
            context += "\nSearch Results:\n"
            context += "\n\n".join(
                f"Title: {r['title']}\nSnippet: {r.get('snippet', '')}\nURL: {r['url']}"
                for r in results
            )

        response = self._call(
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Enrich this lead:\n\n{context}",
                }
            ],
        )

        try:
            data = extract_json(response)

            # Build enriched_data as readable text for the report
            summary_parts = []
            for key, label in (
                ("company_overview", "Company Overview"),
                ("team_background", "Team Background"),
                ("location", "Location"),
                ("traction", "Traction"),
                ("product_stage", "Product Stage"),
                ("fundraising_is_raising", "Actively Raising"),
                ("fundraising_amount", "Raise Amount"),
                ("fundraising_details", "Raise Details"),
                ("revenue", "Revenue"),
                ("lois", "LOIs"),
                ("user_growth", "User Growth"),
                ("health_indicators", "Health Indicators"),
                ("why_invest", "Why Invest"),
            ):
                val = data.get(key, "")
                if val and (not isinstance(val, list) or len(val) > 0):
                    if isinstance(val, list):
                        val = ", ".join(val)
                    summary_parts.append(f"{label}: {val}")

            # Populate Lead fields
            links = data.get("links", [])
            if links:
                lead.links = list(set(lead.links + links))

            lead.enriched_data = "\n".join(summary_parts)
            lead.description = data.get("company_overview", "")
            lead.summary = data.get("company_overview", "")
            lead.location = data.get("location", "")
            lead.is_raising = data.get("fundraising_is_raising", "")
            lead.raise_amount = data.get("fundraising_amount", "")
            lead.raise_details = data.get("fundraising_details", "")

            prev_inv = data.get("previous_investors", [])
            if isinstance(prev_inv, list):
                lead.previous_investors = prev_inv
            elif isinstance(prev_inv, str) and prev_inv.strip():
                lead.previous_investors = [prev_inv]

            lead.traction = data.get("traction", "")
            lead.revenue = data.get("revenue", "")
            lead.lois = data.get("lois", "")
            lead.user_growth = data.get("user_growth", "")
            lead.health_indicators = data.get("health_indicators", "")
            lead.why_invest = data.get("why_invest", "")

        except Exception:
            lead.enriched_data = response.strip()

        return lead
