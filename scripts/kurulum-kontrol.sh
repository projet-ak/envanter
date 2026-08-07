#!/usr/bin/env bash
# Envanter — kurulum sonrası sağlık kontrolü
#
# Güncellemeden sonra her şeyin yerinde olduğunu doğrular. Hiçbir şey
# değiştirmez, yalnızca okur.
#
# Kullanım:
#   cd /www/wwwroot/ernsaha.com.tr/envanter
#   bash scripts/kurulum-kontrol.sh
#
# Dışarıdan erişimi de sınamak için (isteğe bağlı):
#   ADRES=https://ernsaha.com.tr/envanter bash scripts/kurulum-kontrol.sh

set -uo pipefail

PROJE_DIZIN="${PROJE_DIZIN:-$(cd "$(dirname "$0")/.." && pwd)}"
SERVIS="${SERVIS:-envanter}"
ADRES="${ADRES:-}"

# Uygulamanın portu servis tanımından okunur (deploy/envanter.service: 8901),
# elle çalıştırılan uvicorn için 8000'e düşülür. PORT= ile elle de verilebilir.
port_bul() {
    [[ -n "${PORT:-}" ]] && { echo "$PORT"; return; }
    local komut p
    komut="$(systemctl show -p ExecStart --value "$SERVIS" 2>/dev/null)"
    p="$(grep -oE -- '--port[= ]+[0-9]+' <<<"$komut" | grep -oE '[0-9]+' | head -1)"
    [[ -n "$p" ]] && { echo "$p"; return; }
    for aday in 8901 8000; do
        if (exec 3<>"/dev/tcp/127.0.0.1/${aday}") 2>/dev/null; then
            exec 3<&- 3>&-
            echo "$aday"; return
        fi
    done
    echo 8901
}
YEREL="${YEREL:-http://127.0.0.1:$(port_bul)}"

cd "$PROJE_DIZIN" || exit 1

Y='\033[32m'; K='\033[31m'; S='\033[33m'; M='\033[36m'; N='\033[0m'
gecen=0; kalan=0; uyari=0

ok()   { printf "  ${Y}✓${N} %s\n" "$1"; gecen=$((gecen+1)); }
hata() { printf "  ${K}✗${N} %s\n" "$1"; [[ -n "${2:-}" ]] && printf "      → %s\n" "$2"; kalan=$((kalan+1)); }
uyar() { printf "  ${S}!${N} %s\n" "$1"; [[ -n "${2:-}" ]] && printf "      → %s\n" "$2"; uyari=$((uyari+1)); }
baslik() { printf "\n${M}%s${N}\n" "$1"; }

PY="${PROJE_DIZIN}/.venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3)"

# --------------------------------------------------------------------------- #
baslik "1. Kod sürümü"
if [[ -d .git ]]; then
    yerel_surum="$(git rev-parse --short HEAD 2>/dev/null)"
    dal="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
    ok "Dal: ${dal} · commit: ${yerel_surum}"
    git fetch -q origin "$dal" 2>/dev/null
    geride="$(git rev-list --count "HEAD..origin/${dal}" 2>/dev/null || echo 0)"
    if [[ "$geride" == "0" ]]; then
        ok "Son sürüm (uzak depoyla aynı)"
    else
        uyar "${geride} commit geride" "git pull ile güncelle"
    fi
    kirli="$(git status --porcelain | wc -l)"
    [[ "$kirli" == "0" ]] || uyar "${kirli} dosyada yerel değişiklik var"
else
    uyar "Git deposu değil, sürüm kontrolü atlandı"
fi

# --------------------------------------------------------------------------- #
baslik "2. Bağımlılıklar"
for modul in fastapi sqlalchemy alembic reportlab openpyxl qrcode; do
    if "$PY" -c "import ${modul}" 2>/dev/null; then
        ok "${modul}"
    else
        hata "${modul} eksik" "./.venv/bin/pip install -r requirements.txt"
    fi
done
if "$PY" -c "import multipart" 2>/dev/null; then
    ok "python-multipart (dosya yükleme)"
else
    hata "python-multipart eksik" "dosya/görsel yükleme çalışmaz"
fi

# --------------------------------------------------------------------------- #
baslik "3. Veritabanı göçleri"
mevcut="$("$PY" -m alembic current 2>/dev/null | grep -oE '^[0-9a-f]{12}' | head -1)"
head_="$("$PY" -m alembic heads 2>/dev/null | grep -oE '^[0-9a-f]{12}' | head -1)"
if [[ -z "$mevcut" ]]; then
    hata "Göç sürümü okunamadı" "./.venv/bin/python -m alembic upgrade head"
elif [[ "$mevcut" == "$head_" ]]; then
    ok "Şema güncel (${mevcut})"
else
    hata "Şema eski: ${mevcut} (olması gereken ${head_})" \
         "./.venv/bin/python -m alembic upgrade head"
fi

# asset_files tablosu (dosya yükleme göçü)
"$PY" - <<'PYEOF' 2>/dev/null
import sys
sys.path.insert(0, ".")
from sqlalchemy import inspect
from app.database import engine
tablolar = set(inspect(engine).get_table_names())
eksik = {"assets", "users", "asset_files"} - tablolar
sys.exit(1 if eksik else 0)
PYEOF
[[ $? -eq 0 ]] && ok "Tablolar yerinde (asset_files dahil)" \
               || hata "asset_files tablosu yok" "alembic upgrade head çalıştır"

# --------------------------------------------------------------------------- #
baslik "4. Ayarlar (.env)"
if [[ -f .env ]]; then
    ok ".env mevcut"
    izin="$(stat -c '%a' .env)"
    [[ "$izin" == "600" ]] && ok ".env izinleri 600" \
                           || uyar ".env izinleri ${izin}" "chmod 600 .env"
    for anahtar in DATABASE_URL SECRET_KEY; do
        if grep -qE "^${anahtar}=.+" .env; then ok "${anahtar} tanımlı"
        else hata "${anahtar} boş ya da yok"; fi
    done
    org="$(grep -E '^ORG_NAME=' .env | cut -d= -f2- | tr -d '"'"'"'')"
    if [[ -z "$org" || "$org" == "Kurum Adı" ]]; then
        uyar "ORG_NAME ayarlanmamış" "zimmet formu başlığında 'Kurum Adı' yazar"
    else
        ok "ORG_NAME: ${org}"
    fi
    grep -qE '^ROOT_PATH=.+' .env && ok "ROOT_PATH: $(grep -E '^ROOT_PATH=' .env | cut -d= -f2-)" \
                                  || uyar "ROOT_PATH boş" "alt klasörde yayındaysa gerekir"
else
    hata ".env yok" "cp .env.example .env && nano .env"
fi

# --------------------------------------------------------------------------- #
baslik "5. Yükleme klasörü (görseller, imzalı formlar)"
YUK="$(grep -E '^UPLOAD_DIR=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"'')"
YUK="${YUK:-yuklemeler}"
[[ "$YUK" = /* ]] || YUK="${PROJE_DIZIN}/${YUK}"
if [[ -d "$YUK" ]]; then
    ok "Klasör var: ${YUK}"
    sahip="$(stat -c '%U' "$YUK")"
    servis_kul="$(systemctl show -p User --value "$SERVIS" 2>/dev/null)"
    servis_kul="${servis_kul:-www}"
    if sudo -u "$servis_kul" test -w "$YUK" 2>/dev/null; then
        ok "Servis kullanıcısı (${servis_kul}) yazabiliyor"
    else
        uyar "${servis_kul} yazamıyor olabilir (sahip: ${sahip})" \
             "chown -R ${servis_kul}:${servis_kul} ${YUK}"
    fi
    printf "      %s dosya\n" "$(find "$YUK" -type f 2>/dev/null | wc -l)"
else
    uyar "Klasör yok: ${YUK}" "ilk yüklemede kendiliğinden oluşur"
fi

# --------------------------------------------------------------------------- #
baslik "5b. Yedekler"
YED="$(grep -E '^BACKUP_DIR=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"'')"
YED="${YED:-yedekler}"
[[ "$YED" = /* ]] || YED="${PROJE_DIZIN}/${YED}"
if [[ -d "$YED" ]]; then
    adet="$(find "$YED" -maxdepth 1 -type f \( -name 'envanter_*' -o -name 'dosyalar_*' \) 2>/dev/null | wc -l)"
    if [[ "$adet" -gt 0 ]]; then
        ok "${adet} yedek var: ${YED}"
        son="$(find "$YED" -maxdepth 1 -type f -name 'envanter_*' -printf '%T@ %p\n' 2>/dev/null \
               | sort -rn | head -1 | cut -d' ' -f2-)"
        [[ -n "$son" ]] && printf "      son: %s (%s)\n" "$(basename "$son")" \
                                  "$(date -r "$son" '+%d.%m.%Y %H:%M')"
    else
        uyar "Yedek klasörü boş: ${YED}" "Ayarlar → Yedekleme'den yedek alın"
    fi
else
    uyar "Yedek klasörü yok: ${YED}" "ilk yedekte kendiliğinden oluşur"
fi
if crontab -l 2>/dev/null | grep -q 'envanter-yedek'; then
    ok "Otomatik yedek cron işi tanımlı"
else
    uyar "Otomatik yedek kurulmamış" \
         "sudo cp deploy/yedek.sh /usr/local/bin/envanter-yedek && crontab -e"
fi

# --------------------------------------------------------------------------- #
baslik "6. Servis"
if systemctl is-active --quiet "$SERVIS" 2>/dev/null; then
    ok "systemd servisi çalışıyor (${SERVIS})"
    printf "      %s\n" "$(systemctl show -p ActiveEnterTimestamp --value "$SERVIS")"
else
    hata "Servis çalışmıyor" "systemctl status ${SERVIS} · journalctl -u ${SERVIS} -n 50"
fi

# --------------------------------------------------------------------------- #
baslik "7. Uygulama uçları (${YEREL})"
kod() { curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$1" 2>/dev/null; }

saglik="$(kod "${YEREL}/health")"
if [[ "$saglik" == "200" ]]; then
    ok "/health → 200"
    printf "      %s\n" "$(curl -s --max-time 10 "${YEREL}/health")"
else
    hata "/health → ${saglik}" "servis ayakta mı? journalctl -u ${SERVIS} -n 50"
fi

for yol in "/login:Giriş sayfası" "/ui/:Arayüz" "/docs:API dokümanı"; do
    y="${yol%%:*}"; ad="${yol#*:}"
    k="$(kod "${YEREL}${y}")"
    [[ "$k" == "200" ]] && ok "${y} → 200 (${ad})" || hata "${y} → ${k} (${ad})"
done

# Yeni uçlar giriş ister; 401 dönmesi "uç var ve korumalı" demektir
for yol in "/assets/ara:Hızlı arama" "/users/ara:Personel arama" \
           "/users/hesaplar:Hesap yönetimi" "/assets/ozellik-sablonu:Özellik şablonu"; do
    y="${yol%%:*}"; ad="${yol#*:}"
    k="$(kod "${YEREL}${y}")"
    case "$k" in
        401|403) ok "${y} → ${k} (${ad} — var, korumalı)" ;;
        200)     ok "${y} → 200 (${ad})" ;;
        404)     hata "${y} → 404 (${ad} yok)" "eski sürüm çalışıyor: git pull + servisi yeniden başlat" ;;
        *)       hata "${y} → ${k} (${ad})" ;;
    esac
done

# --------------------------------------------------------------------------- #
baslik "8. Veri"
"$PY" - <<'PYEOF' 2>/dev/null
import sys
sys.path.insert(0, ".")
from sqlalchemy import func, select
from app.database import SessionLocal
from app import models

db = SessionLocal()
say = lambda m, *k: db.scalar(select(func.count(m.id)).where(*k)) or 0
print(f"      Cihaz          : {say(models.Asset)}")
print(f"      Personel       : {say(models.User)}")
print(f"      Zimmetli cihaz : {say(models.Asset, models.Asset.assigned_type.is_not(None))}")
print(f"      Lokasyon       : {say(models.Location)}")
print(f"      Yüklenen dosya : {say(models.AssetFile)}")

kodlar = db.execute(
    select(models.Location.proje_kodu, func.count(models.Asset.id))
    .select_from(models.Location)
    .join(models.Asset, models.Asset.location_id == models.Location.id)
    .where(models.Location.proje_kodu.is_not(None))
    .group_by(models.Location.proje_kodu).order_by(models.Location.proje_kodu)
).all()
print(f"      Şantiye        : " + (", ".join(f"{k}({n})" for k, n in kodlar) or "yok"))

yonetici = say(models.User, models.User.role == models.UserRole.admin,
               models.User.active.is_(True), models.User.password_hash.is_not(None))
hesap = say(models.User, models.User.username.is_not(None),
            models.User.password_hash.is_not(None))
print(f"      Giriş yapabilen: {hesap} kullanıcı ({yonetici} yönetici)")
db.close()
sys.exit(0 if yonetici else 2)
PYEOF
durum=$?
case $durum in
    0) ok "Veri okunabiliyor, etkin yönetici var" ;;
    2) hata "Giriş yapabilen yönetici yok" "python scripts/create_admin.py --username admin --password '...'" ;;
    *) hata "Veritabanına bağlanılamadı" "DATABASE_URL doğru mu? bash scripts/env-kontrol.sh" ;;
esac

# --------------------------------------------------------------------------- #
if [[ -n "$ADRES" ]]; then
    baslik "9. Dışarıdan erişim (${ADRES})"
    for yol in /health /login /ui/; do
        k="$(kod "${ADRES}${yol}")"
        [[ "$k" == "200" ]] && ok "${yol} → 200" \
                            || hata "${yol} → ${k}" "Nginx ön ek kırpma kuralını kontrol et"
    done
fi

# --------------------------------------------------------------------------- #
printf "\n${M}Özet${N}\n"
printf "  ${Y}%d başarılı${N}" "$gecen"
[[ $uyari -gt 0 ]] && printf " · ${S}%d uyarı${N}" "$uyari"
[[ $kalan -gt 0 ]] && printf " · ${K}%d hata${N}" "$kalan"
printf "\n"
[[ $kalan -eq 0 ]] && printf "  ${Y}Sistem çalışır durumda.${N}\n" \
                   || printf "  ${K}Yukarıdaki hataları giderin.${N}\n"
exit $(( kalan > 0 ? 1 : 0 ))
