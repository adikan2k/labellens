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

    # Neo4j AuraDB Free
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: SecretStr | None = None

    # Langfuse
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str | None = None

    # Public demo limits
    ask_rate_limit_per_hour: int = 10
    ask_daily_spend_cap_usd: float = 0.50


# US dollars per million input and output tokens at standard rates (the Batch API halves
# them). Used for the printed estimate before any paid run; check against current pricing.
# A constant, not a setting: prices change with the model name, which is set above.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}


def price_per_mtok(model: str) -> tuple[float, float]:
    if model not in MODEL_PRICES:
        raise ValueError(f"No price for {model} in api/app/config.py; add it before a paid run.")
    return MODEL_PRICES[model]


@lru_cache
def get_settings() -> Settings:
    return Settings()
