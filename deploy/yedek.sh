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

elif [[ "$DB_URL" == mysql* ]]; then
    command -v mysqldump >/dev/null || command -v mariadb-dump >/dev/null \
        || { echo "✗ mysqldump/mariadb-dump yok. Kur: apt install -y mariadb-client" >&2; exit 1; }
    DUMP="$(command -v mariadb-dump || command -v mysqldump)"
    # URL'i Python ile ayrıştır: parolada '@' veya ':' gibi karakterler
    # olabilir; bash ile bölmek hatalı sonuç verir.
    PY="${PROJE_DIZIN}/.venv/bin/python"
    [[ -x "$PY" ]] || PY="$(command -v python3 || true)"
    [[ -x "$PY" ]] || { echo "✗ python3 bulunamadı" >&2; exit 1; }
    mapfile -t PARCA < <("$PY" - "$DB_URL" <<'PYEOF'
import sys
from urllib.parse import urlsplit, unquote
u = urlsplit(sys.argv[1])
print(unquote(u.username or ""))
print(unquote(u.password or ""))
print(u.hostname or "localhost")
print(u.port or 3306)
print((u.path or "/").lstrip("/"))
PYEOF
)
    KULLANICI="${PARCA[0]}"; PAROLA="${PARCA[1]}"
    SUNUCU="${PARCA[2]}"; PORT="${PARCA[3]}"; VT="${PARCA[4]}"
    [[ -n "$VT" ]] || { echo "✗ DATABASE_URL içinde veritabanı adı yok" >&2; exit 1; }
    DOSYA="${YEDEK_DIZIN}/envanter_${TARIH}.sql"
    # Parola komut satırında görünmesin diye geçici seçenek dosyası kullan
    KONF="$(mktemp)"; chmod 600 "$KONF"
    printf '[client]\nuser=%s\npassword=%s\nhost=%s\nport=%s\n' \
        "$KULLANICI" "$PAROLA" "$SUNUCU" "$PORT" > "$KONF"
    "$DUMP" --defaults-extra-file="$KONF" --single-transaction \
        --default-character-set=utf8mb4 "$VT" > "$DOSYA"
    rm -f "$KONF"

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

# Yüklenen dosyalar (cihaz görselleri, imzalı zimmet formları) veritabanında
# değil diskte durur; veritabanı yedeği bunları içermez.
YUKLEME="$(grep -E '^UPLOAD_DIR=' "${PROJE_DIZIN}/.env" 2>/dev/null \
           | cut -d= -f2- | tr -d '"'"'"'')"
YUKLEME="${YUKLEME:-yuklemeler}"
[[ "$YUKLEME" = /* ]] || YUKLEME="${PROJE_DIZIN}/${YUKLEME}"

if [[ -d "$YUKLEME" ]] && [[ -n "$(ls -A "$YUKLEME" 2>/dev/null)" ]]; then
    DOSYA_ARSIV="${YEDEK_DIZIN}/dosyalar_${TARIH}.tar.gz"
    tar -czf "$DOSYA_ARSIV" -C "$(dirname "$YUKLEME")" "$(basename "$YUKLEME")"
    echo "✓ Dosyalar yedeklendi: ${DOSYA_ARSIV} ($(du -h "$DOSYA_ARSIV" | cut -f1))"
fi

# Eski yedekleri temizle
silinen=$(find "$YEDEK_DIZIN" \( -name 'envanter_*.gz' -o -name 'dosyalar_*.tar.gz' \) \
          -mtime "+${SAKLAMA_GUN}" -print -delete | wc -l)
[[ "$silinen" -gt 0 ]] && echo "  ${silinen} eski yedek silindi (${SAKLAMA_GUN} günden eski)"
exit 0
