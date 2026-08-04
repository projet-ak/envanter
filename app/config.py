"""Uygulama ayarları — ortam değişkenlerinden (.env) okunur."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Veritabanı
    database_url: str = "sqlite:///./envanter.db"

    # Kurum bilgileri (zimmet fişi / raporlarda görünür)
    org_name: str = "Kurum Adı"

    # Alt klasörde yayınlanıyorsa (örn. https://site.com/envanet/) buraya
    # "/envanet" yaz. Kök dizinde çalışıyorsa boş bırak.
    root_path: str = ""

    # Kimlik doğrulama (JWT)
    # ÜRETİMDE mutlaka değiştir! (örn: `openssl rand -hex 32`)
    secret_key: str = "dev-insecure-change-me-0123456789abcdef-please-set-SECRET_KEY"
    access_token_expire_minutes: int = 480  # 8 saat
    jwt_algorithm: str = "HS256"

    # Claude / Anthropic
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"

    # Snipe-IT içe aktarım
    snipeit_url: str | None = None
    snipeit_token: str | None = None


settings = Settings()
