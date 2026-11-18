"""Runtime settings.

Every secret, endpoint and model name comes from environment variables (see `.env.example`).
Model names live here and nowhere else in the code.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Models
    anthropic_api_key: SecretStr | None = None
    model_default: str = "claude-haiku-5-5"
    model_eval: str = "claude-sonnet-5-5"
    # Embeddings (see docs/decisions/0001-embeddings.md)
    embeddings_api_key: SecretStr | None = None
    embeddings_model: str = "voyage-4-lite"

    # Neon Postgres
    database_url: SecretStr | None = None
    database_url_readonly: SecretStr | None = None
    # Seconds to wait for a pooled connection. Neon wakes from idle in about a second.
    db_pool_timeout: float = 8.0

    # API: comma-separated browser origins allowed to call it
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # The website, for links from MCP tool results and the card to product pages
    public_web_url: str = "http://localhost:3000"

    # Neo4j AuraDB Free
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: SecretStr | None = None

    # Langfuse
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str | None = None

    # Public demo limits
    ask_rate_limit_per_hour: int = 10
    ask_daily_spend_cap_usd: float = 0.50
    # A run stops here; Cloud Run's request timeout (60 s) leaves room to send the error.
    ask_timeout_seconds: float = 45.0
    # MCP requests per client per minute, per instance (in memory; decision 0008)
    mcp_rate_limit_per_minute: int = 60


# US dollars per million input and output tokens at standard rates (the Batch API halves
# them). Used for the printed estimate before any paid run; check against current pricing.
# A constant, not a setting: prices change with the model name, which is set above.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}


# Prompt caching, as multiples of the model's input price. A cache read costs a tenth of it on
# Haiku 5.5 and a twentieth on Sonnet 5.5 ($0.10 against $2.00); a write with the default
# 5-minute TTL costs 1.25 times it on both. Check against current pricing.
CACHE_READ_MULTIPLIERS: dict[str, float] = {
    "claude-haiku-5-5": 0.10,
    "claude-sonnet-5-5": 0.05,
}
CACHE_WRITE_MULTIPLIER = 1.25


# US dollars per million tokens for the embeddings model (decision 0001).
EMBEDDING_PRICES: dict[str, float] = {"voyage-4-lite": 0.02}


def embedding_price_per_mtok(model: str) -> float:
    if model not in EMBEDDING_PRICES:
        raise ValueError(f"No price for {model} in api/app/config.py; add it before a paid run.")
    return EMBEDDING_PRICES[model]


def price_per_mtok(model: str) -> tuple[float, float]:
    if model not in MODEL_PRICES:
        raise ValueError(f"No price for {model} in api/app/config.py; add it before a paid run.")
    return MODEL_PRICES[model]


def input_cost_usd(model: str, uncached: int, cache_read: int = 0, cache_write: int = 0) -> float:
    """US dollars for a request's input tokens: uncached at the input price, cache reads and
    writes at their multiples of it."""
    price_in, _ = price_per_mtok(model)
    if model not in CACHE_READ_MULTIPLIERS:
        raise ValueError(f"No cache price for {model} in api/app/config.py; add it.")
    weighted = (
        uncached + cache_read * CACHE_READ_MULTIPLIERS[model] + cache_write * CACHE_WRITE_MULTIPLIER
    )
    return weighted * price_in / 1e6


@lru_cache
def get_settings() -> Settings:
    return Settings()
