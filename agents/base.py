import json
import re

from openai import OpenAI

from config import settings


def extract_json(text: str) -> dict | list:
    """Extract JSON from model response, stripping markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    return json.loads(text)


class BaseAgent:
    default_model: str = ""

    def __init__(self, model: str | None = None):
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_API_BASE,
        )
        self.model = model or self.default_model

    def _call(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                *messages,
            ],
        )
        return resp.choices[0].message.content
