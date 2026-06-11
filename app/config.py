"""Uygulama ayarları — ortam değişkenlerinden (.env) okunur."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Veritabanı
    database_url: str = "sqlite:///./envanter.db"

    # Claude / Anthropic
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"

    # Snipe-IT içe aktarım
    snipeit_url: str | None = None
    snipeit_token: str | None = None


settings = Settings()
