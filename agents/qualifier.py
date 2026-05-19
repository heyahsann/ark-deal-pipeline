"""Qualifier agent — scores leads 1-10 against investment thesis.

Cross-verifies founder names by searching "[company] founder" on the web.
Only accepts a founder name if it appears in at least 2 independent search
results. Unverified names are flagged for manual review.
"""

import time

from models import Lead
from agents.base import BaseAgent, extract_json
from search import web_search

INVESTMENT_THESIS = """
INVESTMENT THESIS:
- Stage: Pre-seed or Seed
- Geography: SF Bay Area, NYC, LA, Austin, Seattle (or other major US tech hubs)
- Sectors: AI-native SaaS, AI infrastructure, vertical AI agents, AI-native fintech
- Sweet spot: Founders building with LLMs as core product (not just a feature)

STRONG LEAD SIGNALS:
- Founder actively posting about building
- Product launched or in beta (Product Hunt, GitHub, landing page)
- Team size under 20, company under 2 years old
- Currently raising or about to raise
- Based in a major US tech hub
- Engagement from other founders/investors

DISQUALIFIERS:
- AI wrapping legacy software
- Pure consulting/services
- No technical co-founder
- Outside US / not in a major tech hub

SCORING:
- 1-3: Weak match (missing most criteria, disqualifiers present)
- 4-6: Partial match (some criteria met, no disqualifiers)
- 7-8: Strong match (most criteria met)
- 9-10: Excellent match (all criteria met)
"""

SYSTEM_PROMPT = f"""You are a deal qualifier for an AI startup investment pipeline.
Score each lead 1-10 against this thesis.

{INVESTMENT_THESIS}

Return a JSON array of objects, each with:
- founder_name: string (must match the input exactly)
- score: integer 1-10
- rationale: string (brief explanation, < 2 sentences)

Only return leads with score >= 7. Filter out weak leads."""

VERIFY_PROMPT = """You are a founder name verifier. Given search results for "[company name] founder",
extract the founder name(s) mentioned in each individual search result.

For EVERY search result, identify if a founder name is mentioned.
Founder names usually appear as:
- "X founded Y" or "Y was founded by X"
- "X launched Y" or "X is building Y"
- "X, founder/CEO of Y"
- Article bylines about the company launch/funding

Return a JSON object with a "results" array. Each entry:
- result_index: int (0-based index of the search result)
- founder_names: list of strings (founder names found in THIS result, or empty list if none)

Be thorough — extract names from every result that mentions a person in a founder context.
If a result doesn't mention any founder, its founder_names should be an empty list."""


class Qualifier(BaseAgent):
    default_model = "deepseek-chat"

    def _verify_founder(self, company: str, scanner_name: str = "") -> tuple[str, list[str]]:
        """Verify founder name for a company via web search + LLM.

        Phase 1: searches "[company] founder", extracts names from each result,
        counts occurrences. Only accepts if 2+ independent results agree.

        Phase 2 (fallback): if Phase 1 fails and scanner provided a name,
        searches '"scanner_name" "company"' to confirm the specific pairing.

        Returns (verified_name, all_names_found).
        """
        # Phase 1: Generic search for "[company] founder"
        query = f'"{company}" founder'
        results = web_search(query, max_results=8)
        time.sleep(0.5)

        formatted = "\n\n".join(
            f"--- Result {i} ---\nTitle: {r['title']}\nSnippet: {r.get('snippet', '')}\nURL: {r['url']}"
            for i, r in enumerate(results)
        ) if results else ""

        verified, all_names = self._count_founder_mentions(
            formatted, company,
            extra_context=f"Search query: {query}\n"
        )

        if verified != "Unverified - needs manual check":
            return verified, all_names

        # Phase 2: If generic search failed and scanner gave a name,
        # search for the specific pairing to confirm
        if scanner_name and scanner_name not in ("Unknown", ""):
            specific_query = f'"{scanner_name}" "{company}"'
            specific_results = web_search(specific_query, max_results=6)
            time.sleep(0.5)

            if specific_results:
                specific_fmt = "\n\n".join(
                    f"--- Result {i} ---\nTitle: {r['title']}\nSnippet: {r.get('snippet', '')}\nURL: {r['url']}"
                    for i, r in enumerate(specific_results)
                )
                verified2, all_names2 = self._count_founder_mentions(
                    specific_fmt, company,
                    extra_context=f"Search query: {specific_query}\n"
                )
                all_names.extend(all_names2)
                if verified2 != "Unverified - needs manual check":
                    return verified2, all_names

        return "Unverified - needs manual check", all_names

    def _count_founder_mentions(
        self, formatted: str, company: str,
        extra_context: str = "",
    ) -> tuple[str, list[str]]:
        """Send search results to LLM, count founder name mentions across results.
        Returns (verified_name, all_names_found).
        """
        if not formatted:
            return "Unverified - needs manual check", []

        try:
            response = self._call(
                system=VERIFY_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"Extract founder names from these search results for \"{company}\":\n\n{extra_context}{formatted}",
                    }
                ],
                max_tokens=2048,
            )
        except Exception as e:
            print(f"    [WARN] Founder verification LLM call failed: {e}")
            return "Unverified - needs manual check", []

        try:
            data = extract_json(response)
        except Exception:
            return "Unverified - needs manual check", []

        if isinstance(data, dict):
            data = data.get("results") or [data]
        if not isinstance(data, list):
            return "Unverified - needs manual check", []

        # Count name occurrences across independent results
        name_counts: dict[str, int] = {}
        all_names: set[str] = set()
        for entry in data:
            names = entry.get("founder_names", [])
            if isinstance(names, str):
                names = [names]
            for name in names:
                if isinstance(name, str) and name.strip():
                    clean = name.strip()
                    all_names.add(clean)
                    name_counts[clean] = name_counts.get(clean, 0) + 1

        if not name_counts:
            return "Unverified - needs manual check", list(all_names)

        # Find name(s) appearing in 2+ results
        verified = [n for n, c in name_counts.items() if c >= 2]

        if len(verified) == 1:
            return verified[0], list(all_names)
        elif len(verified) > 1:
            verified.sort(key=lambda n: name_counts[n], reverse=True)
            return verified[0], list(all_names)
        else:
            return "Unverified - needs manual check", list(all_names)

    def qualify(self, leads: list[Lead]) -> list[Lead]:
        if not leads:
            return []

        # -- Phase 1: Cross-verify founder names ----------------------------
        print("  Cross-verifying founder names via web search...")
        for lead in leads:
            company = (lead.company or "").strip()
            if not company or company.lower() == "unknown":
                # No company to search — mark the founder name as unverifiable
                if lead.founder_name and lead.founder_name not in ("Unknown", ""):
                    # If we have a name but no company, flag it
                    lead.founder_name = f"Unverified - needs manual check"
                continue

            old_name = lead.founder_name or ""
            verified_name, all_found = self._verify_founder(company, scanner_name=old_name)

            # Check if the scanner's name matches the verified name
            if verified_name != "Unverified - needs manual check":
                # Check if the scanner's name matches (case-insensitive, partial)
                scanner_match = any(
                    old_name.lower() in v.lower() or v.lower() in old_name.lower()
                    for v in [verified_name] + all_found
                )
                if scanner_match:
                    # Use the verified canonical name
                    lead.founder_name = verified_name
                    if old_name.lower() == verified_name.lower():
                        print(f"    {company}: verified founder = {verified_name}")
                    else:
                        print(f"    {company}: corrected '{old_name}' -> '{verified_name}'")
                else:
                    # Scanner hallucinated -- override with verified or flag
                    if verified_name:
                        lead.founder_name = verified_name
                        print(f"    {company}: corrected '{old_name}' -> '{verified_name}'")
                    else:
                        lead.founder_name = "Unverified - needs manual check"
                        print(f"    {company}: '{old_name}' not verified -> flagged")
            else:
                # Couldn't verify via web search
                lead.founder_name = "Unverified - needs manual check"
                print(f"    {company}: no verified founder found -> flagged (scanner said: {old_name})")

        # ── Phase 2: Scoring ───────────────────────────────────────────────
        payload = [
            {
                "founder_name": l.founder_name,
                "company": l.company,
                "raw_signal": l.raw_signal,
                "source": str(l.source),
            }
            for l in leads
        ]

        response = self._call(
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Score these leads against our thesis:\n\n{payload}",
                }
            ],
        )

        try:
            scored_data = extract_json(response)
        except Exception as e:
            print(f"  [ERROR] Failed to parse qualifier output: {e}")
            return leads

        if isinstance(scored_data, dict):
            scored_data = (
                scored_data.get("leads")
                or scored_data.get("results")
                or [scored_data]
            )
        if not isinstance(scored_data, list):
            return []

        scored_map = {}
        for item in scored_data:
            name = item.get("founder_name", "")
            try:
                score = int(item.get("score", 0))
            except (ValueError, TypeError):
                continue
            rationale = item.get("rationale", "")
            if name and score >= 7:
                scored_map[name] = (score, rationale)

        qualified = []
        for lead in leads:
            if lead.founder_name in scored_map:
                lead.score, lead.score_rationale = scored_map[lead.founder_name]
                qualified.append(lead)

        qualified.sort(key=lambda l: l.score, reverse=True)
        print(f"  Qualified {len(qualified)}/{len(leads)} leads (score >= 7)")
        return qualified
