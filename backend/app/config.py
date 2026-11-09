from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    es_url: str = "http://localhost:9200"
    es_api_key: str | None = None
    organizer_api_key: str
    public_base_url: str = "http://localhost:8000"
    schedule_draft_ttl_hours: int = Field(default=24, ge=1, le=720)
    schedule_max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    openrouter_api_key: str
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_site_url: str = "http://localhost:8000"
    openrouter_app_name: str = "WeMakeDevs2026"
    otel_service_name: str = "wemakedevs2026-backend"


@lru_cache
def get_settings() -> Settings:
    return Settings()
