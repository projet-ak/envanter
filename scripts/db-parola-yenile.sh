#!/usr/bin/env bash
# Veritabanı parolasını yeniler ve .env ile veritabanını KESİN olarak eşitler.
#
# Kullanım (proje dizininde, root olarak):
#   sudo bash scripts/db-parola-yenile.sh
#
# Yaptıkları:
#   1. .env içindeki bozuk (ANAHTAR=değer olmayan) satırları temizler
#   2. Yeni rastgele parola üretir
#   3. Parolayı hem PostgreSQL'e hem .env'e yazar (böylece asla ayrışamazlar)
#   4. Bağlantıyı doğrular; başarısızsa .env'i eski hâline döndürür
#   5. Servisi yeniden başlatır
#
# Parola hiçbir zaman ekrana yazılmaz.

set -euo pipefail

PROJE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJE"
ENV_DOSYA=".env"
PY="${PROJE}/.venv/bin/python"

renk() { printf "\033[1;36m%s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
hata() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || hata "root gerekli: sudo bash scripts/db-parola-yenile.sh"
[[ -f "$ENV_DOSYA" ]] || hata ".env bulunamadı: $PROJE/$ENV_DOSYA"
[[ -x "$PY" ]] || hata "Sanal ortam yok: $PY"

# --------------------------------------------------------------------------- #
YEDEK="${ENV_DOSYA}.yedek-$(date +%Y%m%d_%H%M%S)"
cp -p "$ENV_DOSYA" "$YEDEK"
renk "→ .env yedeği: $YEDEK"

# 1) Bozuk satırları temizle
TEMIZLENEN="$(awk '
  /^[[:space:]]*$/ { print; next }
  /^[[:space:]]*#/ { print; next }
  {
    n = index($0, "=")
    if (n > 1 && substr($0,1,n-1) ~ /^[A-Za-z_][A-Za-z0-9_]*$/) { print }
    else { atilan++ }
  }
  END { if (atilan > 0) printf("%d", atilan) > "/dev/stderr" }
' "$ENV_DOSYA" 2>/tmp/.atilan_sayi)"
printf '%s\n' "$TEMIZLENEN" > "$ENV_DOSYA"
ATILAN="$(cat /tmp/.atilan_sayi 2>/dev/null || echo 0)"; rm -f /tmp/.atilan_sayi
[[ "${ATILAN:-0}" -gt 0 ]] && ok "${ATILAN} bozuk satır temizlendi" \
                           || echo "   (bozuk satır yoktu)"

# 2) Veritabanı kullanıcı/ad bilgisini .env'den oku
mapfile -t BILGI < <("$PY" - <<'PYEOF'
import pathlib, sys
from urllib.parse import urlsplit, unquote
url = ""
for satir in pathlib.Path(".env").read_text().splitlines():
    if satir.startswith("DATABASE_URL="):
        url = satir.split("=", 1)[1].strip()
        break
if not url:
    sys.exit("DATABASE_URL yok")
u = urlsplit(url)
if not u.scheme.startswith("postgresql"):
    sys.exit(f"Bu script yalnızca PostgreSQL içindir (bulunan: {u.scheme})")
print(unquote(u.username or ""))
print((u.path or "/").lstrip("/"))
PYEOF
) || hata ".env içindeki DATABASE_URL okunamadı"

DB_KULLANICI="${BILGI[0]}"; DB_ADI="${BILGI[1]}"
[[ -n "$DB_KULLANICI" && -n "$DB_ADI" ]] || hata "Kullanıcı/veritabanı adı çözülemedi"
renk "→ Veritabanı: ${DB_ADI} (kullanıcı: ${DB_KULLANICI})"

# 3) Yeni parola üret — yalnızca harf/rakam (kaçış sorunu olmasın)
YENI="$(openssl rand -hex 24)"

# 4) PostgreSQL'e uygula
sudo -u postgres psql -qc \
    "ALTER USER \"${DB_KULLANICI}\" WITH PASSWORD '${YENI}';" \
    || hata "PostgreSQL parolası değiştirilemedi"
ok "PostgreSQL parolası güncellendi"

# 5) Aynı parolayı .env'e yaz (Python ile — kaçış hatası olmaz)
YENI_PAROLA="$YENI" "$PY" - <<'PYEOF'
import os, pathlib
from urllib.parse import urlsplit, urlunsplit, quote
yeni = os.environ["YENI_PAROLA"]
p = pathlib.Path(".env")
satirlar = p.read_text().splitlines()
for i, s in enumerate(satirlar):
    if s.startswith("DATABASE_URL="):
        u = urlsplit(s.split("=", 1)[1].strip())
        yetki = f"{u.username}:{quote(yeni, safe='')}@{u.hostname}"
        if u.port:
            yetki += f":{u.port}"
        satirlar[i] = "DATABASE_URL=" + urlunsplit(
            (u.scheme, yetki, u.path, u.query, u.fragment))
        break
p.write_text("\n".join(satirlar) + "\n")
PYEOF
ok ".env güncellendi"
chmod 600 "$ENV_DOSYA"
chown www:www "$ENV_DOSYA" 2>/dev/null || true

# 6) Doğrula
if "$PY" - <<'PYEOF'
import pathlib, sys
from sqlalchemy import create_engine, text
url = next(s.split("=", 1)[1].strip()
           for s in pathlib.Path(".env").read_text().splitlines()
           if s.startswith("DATABASE_URL="))
try:
    with create_engine(url).connect() as c:
        c.execute(text("SELECT 1"))
except Exception as exc:
    print(f"   {type(exc).__name__}", file=sys.stderr)
    sys.exit(1)
PYEOF
then
    ok "Bağlantı doğrulandı"
else
    cp -p "$YEDEK" "$ENV_DOSYA"
    hata "Bağlantı kurulamadı — .env yedekten geri yüklendi ($YEDEK)"
fi

# 7) Servisi yenile
systemctl restart envanter 2>/dev/null && ok "Servis yeniden başlatıldı" \
    || echo "   (servis bulunamadı, atlandı)"

echo ""
ok "TAMAM — parola yenilendi, .env ile veritabanı eşitlendi"
echo "   Parola ekrana yazılmadı; .env içinde saklanıyor."
