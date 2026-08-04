#!/usr/bin/env bash
# Envanter — otomatik veritabanı yedeği
#
# Kurulum (her gece 03:00'te yedek, 30 gün saklama):
#   sudo cp deploy/yedek.sh /usr/local/bin/envanter-yedek
#   sudo chmod +x /usr/local/bin/envanter-yedek
#   sudo crontab -e
#   # şu satırı ekle:
#   0 3 * * * /usr/local/bin/envanter-yedek >> /var/log/envanter-yedek.log 2>&1

set -euo pipefail

PROJE_DIZIN="${PROJE_DIZIN:-/www/wwwroot/ernsaha.com.tr/envanter}"
YEDEK_DIZIN="${YEDEK_DIZIN:-/www/backup/envanter}"
SAKLAMA_GUN="${SAKLAMA_GUN:-30}"

mkdir -p "$YEDEK_DIZIN"

# .env içindeki DATABASE_URL'i oku
if [[ -f "${PROJE_DIZIN}/.env" ]]; then
    # shellcheck disable=SC1090
    DB_URL="$(grep -E '^DATABASE_URL=' "${PROJE_DIZIN}/.env" | cut -d= -f2- | tr -d '"'"'"'')"
else
    echo "✗ .env bulunamadı: ${PROJE_DIZIN}/.env" >&2
    exit 1
fi

TARIH="$(date +%F_%H%M)"
DOSYA="${YEDEK_DIZIN}/envanter_${TARIH}.dump"

if [[ "$DB_URL" == postgresql* ]]; then
    command -v pg_dump >/dev/null \
        || { echo "✗ pg_dump bulunamadı. Kur: apt install -y postgresql-client" >&2; exit 1; }
    # SQLAlchemy URL'ini pg_dump'ın anlayacağı biçime çevir
    PG_URL="${DB_URL/postgresql+psycopg2:/postgresql:}"
    pg_dump -Fc "$PG_URL" > "$DOSYA"

elif [[ "$DB_URL" == sqlite* ]]; then
    SQLITE_YOL="${DB_URL#sqlite:///}"
    [[ "$SQLITE_YOL" = /* ]] || SQLITE_YOL="${PROJE_DIZIN}/${SQLITE_YOL#./}"
    [[ -f "$SQLITE_YOL" ]] || { echo "✗ Veritabanı dosyası yok: $SQLITE_YOL" >&2; exit 1; }
    DOSYA="${YEDEK_DIZIN}/envanter_${TARIH}.sqlite"
    if command -v sqlite3 >/dev/null; then
        sqlite3 "$SQLITE_YOL" ".backup '${DOSYA}'"
    else
        # sqlite3 CLI yoksa Python ile yedekle (uygulama zaten Python)
        PY="${PROJE_DIZIN}/.venv/bin/python"
        [[ -x "$PY" ]] || PY="$(command -v python3 || true)"
        [[ -x "$PY" ]] || { echo "✗ sqlite3 de python3 de yok" >&2; exit 1; }
        "$PY" - "$SQLITE_YOL" "$DOSYA" <<'PYEOF'
import sqlite3, sys
kaynak, hedef = sys.argv[1], sys.argv[2]
with sqlite3.connect(kaynak) as src, sqlite3.connect(hedef) as dst:
    src.backup(dst)
PYEOF
    fi

else
    echo "✗ Desteklenmeyen DATABASE_URL biçimi: ${DB_URL%%:*}" >&2
    exit 1
fi

gzip -f "$DOSYA"
echo "✓ Yedek alındı: ${DOSYA}.gz ($(du -h "${DOSYA}.gz" | cut -f1))"

# Eski yedekleri temizle
silinen=$(find "$YEDEK_DIZIN" -name 'envanter_*.gz' -mtime "+${SAKLAMA_GUN}" -print -delete | wc -l)
[[ "$silinen" -gt 0 ]] && echo "  ${silinen} eski yedek silindi (${SAKLAMA_GUN} günden eski)"
exit 0
