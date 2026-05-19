from models import Lead
from agents.base import BaseAgent, extract_json

SYSTEM_PROMPT = """You are an outreach drafter for an AI deal sourcing pipeline.
Write personalized cold outreach messages to founders.

Requirements:
- Personalized (reference specific details about the founder's work)
- Concise (under 150 words)
- Shows genuine interest in their product/vision
- Includes a specific compliment or observation
- Ends with clear, low-friction call to action
- Warm, professional, knowledgeable tone -- not salesy

Return ONLY valid JSON:
{"outreach_message": "the message text"}

Do NOT use templates. Every message must be unique."""


class OutreachDrafter(BaseAgent):
    default_model = "deepseek-chat"

    def draft(self, lead: Lead) -> Lead:
        context = (
            f"Founder: {lead.founder_name}\n"
            f"Company: {lead.company}\n"
            f"Signal: {lead.raw_signal}\n"
            f"Score: {lead.score}/10\n"
            f"Rationale: {lead.score_rationale}\n"
        )
        if lead.enriched_data:
            context += f"\nEnriched Data:\n{lead.enriched_data[:2000]}\n"

        response = self._call(
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Write a personalized outreach message for:\n\n{context}",
                }
            ],
        )

        try:
            result = extract_json(response)
            msg = result.get("outreach_message", "")
            if msg:
                lead.outreach_message = msg
            else:
                lead.outreach_message = response.strip()
        except Exception:
            lead.outreach_message = response.strip()

        return lead
