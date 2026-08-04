#!/usr/bin/env bash
# Envanter — sıfırdan tam kurulum (tek komut)
#
# Sunucuda çalıştır:
#   curl -fsSL <RAW_URL>/deploy/tek-komut.sh | sudo bash
# veya repoyu klonladıysan:
#   sudo bash deploy/tek-komut.sh
#
# Yaptıkları: git+paketler → repo → PostgreSQL veritabanı → .env →
#             kurulum.sh → admin kullanıcı → Nginx notu
# Tekrar çalıştırılabilir; var olanı bozmaz.

set -euo pipefail

REPO="${REPO:-https://github.com/projet-ak/envanter.git}"
BRANCH="${BRANCH:-claude/modest-dirac-vhosqy}"
HEDEF="${HEDEF:-/www/wwwroot/ernsaha.com.tr/envanter}"
KOK_YOL="${KOK_YOL:-/envanter}"
DB_ADI="${DB_ADI:-envanter}"
DB_KULLANICI="${DB_KULLANICI:-envanter}"
ADMIN_KULLANICI="${ADMIN_KULLANICI:-admin}"
KURUM="${KURUM:-Ernsaha}"

renk() { printf "\033[1;36m\n%s\033[0m\n" "$*"; }
hata() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || hata "root gerekli: sudo bash deploy/tek-komut.sh"

# --------------------------------------------------------------------------- #
renk "→ 1/6  Gerekli paketler"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl openssl postgresql postgresql-contrib >/dev/null
systemctl enable --now postgresql >/dev/null 2>&1 || true
echo "   ✓ git, PostgreSQL hazır"

# --------------------------------------------------------------------------- #
renk "→ 2/6  Proje dosyaları"
# Dizin servis kullanıcısına ait olabilir; git'in "dubious ownership"
# hatası vermemesi için güvenli listeye ekle.
git config --global --add safe.directory "$HEDEF" 2>/dev/null || true
if [[ -d "$HEDEF/.git" ]]; then
    git -C "$HEDEF" fetch --quiet origin "$BRANCH"
    git -C "$HEDEF" checkout --quiet "$BRANCH"
    git -C "$HEDEF" reset --hard --quiet "origin/$BRANCH"
    echo "   ✓ mevcut kurulum güncellendi"
else
    mkdir -p "$(dirname "$HEDEF")"
    git clone --quiet --branch "$BRANCH" "$REPO" "$HEDEF" \
        || hata "Repo klonlanamadı. Özel repo ise: git clone https://KULLANICI:TOKEN@github.com/... "
    echo "   ✓ repo klonlandı: $HEDEF"
fi

# --------------------------------------------------------------------------- #
renk "→ 3/6  Veritabanı"
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_ADI}'" | grep -q 1; then
    echo "   ✓ '${DB_ADI}' veritabanı zaten var"
    DB_PAROLA="$(grep -oP '(?<=://'"${DB_KULLANICI}"':)[^@]+' "${HEDEF}/.env" 2>/dev/null || true)"
    [[ -n "${DB_PAROLA:-}" ]] || { DB_PAROLA="$(openssl rand -hex 16)"
        sudo -u postgres psql -qc "ALTER USER ${DB_KULLANICI} WITH PASSWORD '${DB_PAROLA}';"
        echo "   ✓ parola yenilendi"; }
else
    DB_PAROLA="$(openssl rand -hex 16)"
    sudo -u postgres psql -qc "CREATE USER ${DB_KULLANICI} WITH PASSWORD '${DB_PAROLA}';" 2>/dev/null || \
        sudo -u postgres psql -qc "ALTER USER ${DB_KULLANICI} WITH PASSWORD '${DB_PAROLA}';"
    sudo -u postgres psql -qc "CREATE DATABASE ${DB_ADI} OWNER ${DB_KULLANICI};"
    echo "   ✓ '${DB_ADI}' veritabanı oluşturuldu"
fi

# --------------------------------------------------------------------------- #
renk "→ 4/6  Ayarlar (.env)"
cd "$HEDEF"
if [[ ! -f .env ]]; then
    cp .env.example .env
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg2://${DB_KULLANICI}:${DB_PAROLA}@localhost:5432/${DB_ADI}|" .env
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" .env
    sed -i "s|^ROOT_PATH=.*|ROOT_PATH=${KOK_YOL}|" .env
    sed -i "s|^ORG_NAME=.*|ORG_NAME=${KURUM}|" .env
    echo "   ✓ .env oluşturuldu (veritabanı + güvenlik anahtarı otomatik)"
else
    echo "   ✓ .env zaten var, korundu"
fi
chmod 600 .env

# --------------------------------------------------------------------------- #
renk "→ 5/6  Uygulama kurulumu"
KOK_YOL="$KOK_YOL" bash deploy/kurulum.sh

# --------------------------------------------------------------------------- #
renk "→ 6/6  Yönetici kullanıcı"
if ./.venv/bin/python - <<PY
import sys
sys.path.insert(0, ".")
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User
with SessionLocal() as db:
    sys.exit(0 if db.scalar(select(User).where(User.username == "${ADMIN_KULLANICI}")) else 1)
PY
then
    echo "   ✓ '${ADMIN_KULLANICI}' zaten var, parolası değiştirilmedi"
    ADMIN_PAROLA="(mevcut parolan)"
else
    ADMIN_PAROLA="$(openssl rand -base64 12 | tr -d '/+=' | head -c 14)"
    ./.venv/bin/python scripts/create_admin.py \
        --username "$ADMIN_KULLANICI" --password "$ADMIN_PAROLA" >/dev/null
    echo "   ✓ yönetici oluşturuldu"
fi

# --------------------------------------------------------------------------- #
NGINX_KONF="${HEDEF}/deploy/nginx-envanter.conf"
printf "\033[1;32m\n╔══════════════════════════════════════════════════════════╗\n"
printf "║                   KURULUM TAMAMLANDI                     ║\n"
printf "╚══════════════════════════════════════════════════════════╝\033[0m\n\n"
cat <<EOF
GİRİŞ BİLGİLERİ  (bir yere kaydet, bu ekran bir daha gösterilmez)
  Kullanıcı : ${ADMIN_KULLANICI}
  Parola    : ${ADMIN_PAROLA}

SON ADIM — Nginx (aaPanel):
  aaPanel → Website → ernsaha.com.tr → Config
  Şu dosyanın içeriğini server { } bloğunun içine yapıştır → Save:

    ${NGINX_KONF}

  (İçeriği görmek için:  cat ${NGINX_KONF} )

  Sonra:  nginx -t && systemctl reload nginx

ARDINDAN AÇ:
  https://ernsaha.com.tr${KOK_YOL}/ui/

KOMUTLAR:
  systemctl status envanter        # durum
  journalctl -u envanter -f        # canlı log
  systemctl restart envanter       # yeniden başlat
EOF
