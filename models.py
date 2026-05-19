from dataclasses import dataclass, field
from enum import StrEnum


class Source(StrEnum):
    X = "X (Twitter)"
    LINKEDIN = "LinkedIn"
    WEB = "Web"
    DEMO = "Demo"


@dataclass
class Lead:
    founder_name: str = ""
    company: str = ""
    score: int = 0
    tagline: str = ""
    summary: str = ""
    description: str = ""
    links: list[str] = field(default_factory=list)
    outreach_message: str = ""
    source: Source = Source.WEB
    raw_signal: str = ""
    score_rationale: str = ""
    enriched_data: str = ""

    # New fields
    location: str = ""
    is_raising: str = ""          # "Yes" / "No" / "Unknown"
    raise_amount: str = ""        # e.g. "$3M seed"
    raise_details: str = ""       # e.g. "Led by a16z, closed Aug 2025"
    previous_investors: list[str] = field(default_factory=list)

    # Metrics
    traction: str = ""            # e.g. "200+ beta users"
    revenue: str = ""             # e.g. "$50k ARR"
    lois: str = ""                # Letters of intent
    user_growth: str = ""         # e.g. "30% MoM"
    health_indicators: str = ""   # Other health signals

    # Why invest
    why_invest: str = ""          # Defensibility one-liner
