"""Uygulama ayarları — ortam değişkenlerinden (.env) okunur."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Veritabanı
    database_url: str = "sqlite:///./envanter.db"

    # Kurum bilgileri (zimmet fişi / raporlarda görünür)
    org_name: str = "Kurum Adı"

    # Alt klasörde yayınlanıyorsa (örn. https://site.com/envanter/) buraya
    # "/envanter" yaz. Kök dizinde çalışıyorsa boş bırak.
    root_path: str = ""

    # Yüklenen dosyalar (cihaz görselleri, imzalı zimmet formları).
    # Veritabanında değil diskte tutulur; yedeklemede bu klasörü de al.
    upload_dir: str = "yuklemeler"
    max_upload_mb: int = 20

    # Yedekler (Ayarlar → Yedekleme ve deploy/yedek.sh aynı klasörü kullanır)
    backup_dir: str = "yedekler"
    backup_keep_days: int = 30

    # Kimlik doğrulama (JWT)
    # ÜRETİMDE mutlaka değiştir! (örn: `openssl rand -hex 32`)
    secret_key: str = "dev-insecure-change-me-0123456789abcdef-please-set-SECRET_KEY"
    access_token_expire_minutes: int = 480  # 8 saat
    jwt_algorithm: str = "HS256"

    # Kaba kuvvet koruması: art arda bu kadar hatalı denemeden sonra hesap
    # belirtilen süre boyunca kilitlenir (doğru parola da kabul edilmez).
    max_login_attempts: int = 3
    lockout_minutes: int = 15

    # Claude / Anthropic
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"

    # Snipe-IT içe aktarım
    snipeit_url: str | None = None
    snipeit_token: str | None = None


settings = Settings()
