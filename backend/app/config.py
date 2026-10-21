from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_key: str = ""

    gemini_api_key: str = ""
    tagger_model: str = "gemini-3.5-flash-lite"

    iol_username: str = ""
    iol_password: str = ""
    # Off by default: every order goes to the IOL sandbox unless this is true.
    iol_live_trading: bool = False

    collect_interval_minutes: int = 10
    # Fraction of the portfolio a single stop-out is allowed to lose.
    risk_per_trade: float = 0.01


@lru_cache
def get_settings() -> Settings:
    return Settings()
