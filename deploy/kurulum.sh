#!/usr/bin/env bash
# Envanter — VPS (aaPanel / Ubuntu) kurulum yardımcısı
#
# Kullanım (sunucuda, proje klasöründe):
#   sudo bash deploy/kurulum.sh
#
# Yaptıkları:
#   1. Sistem paketlerini kurar (python venv, postgresql istemcisi, fontlar)
#   2. Sanal ortam oluşturup bağımlılıkları kurar
#   3. .env yoksa örnekten üretir ve SECRET_KEY'i rastgele doldurur
#   4. Veritabanı göçlerini uygular
#   5. systemd servisini kurar ve başlatır
#
# Script tekrar çalıştırılabilir (idempotent): var olanı bozmaz.

set -euo pipefail

PROJE_DIZIN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVIS_ADI="envanter"
PORT="${PORT:-8901}"
KOK_YOL="${KOK_YOL:-/envanter}"
SERVIS_KULLANICI="${SERVIS_KULLANICI:-www}"

renk() { printf "\033[1;36m%s\033[0m\n" "$*"; }
uyari() { printf "\033[1;33m⚠ %s\033[0m\n" "$*"; }
hata() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || hata "Bu script root olarak çalıştırılmalı: sudo bash deploy/kurulum.sh"

renk "→ Proje dizini: $PROJE_DIZIN"

# --------------------------------------------------------------------------- #
renk "→ 1/5  Sistem paketleri kuruluyor…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python3-venv python3-dev build-essential \
    libpq-dev postgresql-client \
    fonts-dejavu-core \
    >/dev/null
echo "   ✓ paketler hazır (Türkçe PDF için DejaVu fontu dahil)"

# --------------------------------------------------------------------------- #
renk "→ 2/5  Python sanal ortamı ve bağımlılıklar…"
cd "$PROJE_DIZIN"
[[ -d .venv ]] || python3 -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
echo "   ✓ bağımlılıklar kuruldu"

# --------------------------------------------------------------------------- #
renk "→ 3/5  Ayar dosyası (.env)…"
if [[ ! -f .env ]]; then
    cp .env.example .env
    # Güvenli rastgele anahtar üret
    ANAHTAR="$(openssl rand -hex 32)"
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${ANAHTAR}|" .env
    sed -i "s|^ROOT_PATH=.*|ROOT_PATH=${KOK_YOL}|" .env
    grep -q '^ROOT_PATH=' .env || echo "ROOT_PATH=${KOK_YOL}" >> .env
    echo "   ✓ .env oluşturuldu, SECRET_KEY rastgele üretildi"
    uyari "DATABASE_URL, ORG_NAME ve (isteğe bağlı) ANTHROPIC_API_KEY değerlerini .env içinde düzenle!"
else
    echo "   ✓ .env zaten var, dokunulmadı"
fi
chown "${SERVIS_KULLANICI}:${SERVIS_KULLANICI}" .env 2>/dev/null || true
chmod 600 .env

# --------------------------------------------------------------------------- #
renk "→ 4/5  Veritabanı göçleri…"
if ./.venv/bin/alembic upgrade head; then
    echo "   ✓ şema güncel"
else
    hata "Göç başarısız. .env içindeki DATABASE_URL doğru mu? PostgreSQL çalışıyor mu?"
fi

# --------------------------------------------------------------------------- #
renk "→ 5/5  systemd servisi…"
SERVIS_DOSYA="/etc/systemd/system/${SERVIS_ADI}.service"
sed -e "s|/www/wwwroot/ernsaha.com.tr/envanter|${PROJE_DIZIN}|g" \
    -e "s|--port 8901|--port ${PORT}|" \
    -e "s|--root-path /envanter|--root-path ${KOK_YOL}|" \
    -e "s|^User=.*|User=${SERVIS_KULLANICI}|" \
    -e "s|^Group=.*|Group=${SERVIS_KULLANICI}|" \
    "${PROJE_DIZIN}/deploy/envanter.service" > "$SERVIS_DOSYA"

chown -R "${SERVIS_KULLANICI}:${SERVIS_KULLANICI}" "$PROJE_DIZIN" 2>/dev/null || true
systemctl daemon-reload
systemctl enable "$SERVIS_ADI" >/dev/null 2>&1
systemctl restart "$SERVIS_ADI"
sleep 3

if systemctl is-active --quiet "$SERVIS_ADI"; then
    echo "   ✓ servis çalışıyor (port ${PORT})"
else
    hata "Servis başlamadı. Log: journalctl -u ${SERVIS_ADI} -n 50 --no-pager"
fi

# --------------------------------------------------------------------------- #
if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null; then
    renk "✓ KURULUM TAMAM"
else
    uyari "Servis ayakta ama /health yanıt vermedi; logu kontrol et."
fi

cat <<EOF

Sıradaki adımlar:
  1) Yönetici kullanıcı oluştur:
       cd ${PROJE_DIZIN}
       ./.venv/bin/python scripts/create_admin.py --username admin --password 'GucluParola'

  2) aaPanel → Website → ernsaha.com.tr → Config'e şu dosyanın içeriğini ekle:
       ${PROJE_DIZIN}/deploy/nginx-envanter.conf

  3) Tarayıcıdan aç:
       https://ernsaha.com.tr${KOK_YOL}/ui/

Faydalı komutlar:
  systemctl status ${SERVIS_ADI}      # durum
  journalctl -u ${SERVIS_ADI} -f      # canlı log
  systemctl restart ${SERVIS_ADI}     # yeniden başlat
EOF
