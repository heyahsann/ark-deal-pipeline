from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    VERIFY_SSL: bool = True

    # Model routing
    SIGNAL_SCANNER_MODEL: str = "deepseek-chat"
    QUALIFIER_MODEL: str = "deepseek-chat"
    ENRICHER_MODEL: str = "deepseek-chat"
    OUTREACH_MODEL: str = "deepseek-chat"

    # Pipeline config
    MAX_LEADS_PER_RUN: int = 25
    QUALIFIER_TOP_PCT: float = 0.2

    # X (Twitter) API config
    X_BEARER_TOKEN: str = ""

    # GitHub sync config
    GITHUB_TOKEN: str = ""
    GITHUB_REPO: str = "heyahsann/ark-deal-pipeline"
    GITHUB_BRANCH: str = "main"

    # Keywords to monitor across sources
    KEYWORDS: list[str] = [
        "building with Claude",
        "building with GPT",
        "AI agent",
        "just launched",
        "pre-seed",
        "seed round",
        "AI-native",
        "vibe coding",
        "we raised",
        "LLM",
        "San Francisco",
        "YC",
        "Y Combinator",
        "we're hiring",
    ]


settings = Settings()
