#!/usr/bin/env python3
"""aaPanel/Nginx site yapılandırmasına /envanter vekil bloğunu ekler.

aaPanel arayüzünde menü adları sürüme göre değiştiği için, bu script
yapılandırma dosyasını doğrudan bulup düzenler.

Kullanım:
    sudo python3 deploy/nginx-ekle.py                 # otomatik bul ve ekle
    sudo python3 deploy/nginx-ekle.py --alan site.com # alan adını belirt
    sudo python3 deploy/nginx-ekle.py --dosya /yol/site.conf
    sudo python3 deploy/nginx-ekle.py --geri-al       # yedekten geri dön

Güvenli: değişiklikten önce yedek alır, `nginx -t` başarısız olursa
otomatik olarak yedeği geri yükler.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

ISARET = "# >>> ENVANTER BASLANGIC (otomatik eklendi) >>>"
ISARET_SON = "# <<< ENVANTER BITIS <<<"

BLOK = """
{isaret}
location /envanter {{
    rewrite ^/envanter/?(.*)$ /$1 break;
    proxy_pass http://127.0.0.1:8901;

    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /envanter;
    proxy_set_header Upgrade           $http_upgrade;
    proxy_set_header Connection        "upgrade";

    client_max_body_size 12m;
    proxy_connect_timeout 30s;
    proxy_send_timeout    180s;
    proxy_read_timeout    180s;
    proxy_buffering off;
}}

location ~ ^/envanter/.*\\.(pdf|png|csv|jpg|jpeg|gif|svg|ico)$ {{
    rewrite ^/envanter/?(.*)$ /$1 break;
    proxy_pass http://127.0.0.1:8901;

    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /envanter;
    proxy_read_timeout 180s;
}}
{isaret_son}
"""

# aaPanel ve klasik Nginx kurulumlarında site dosyalarının bulunduğu yerler
ARAMA_YOLLARI = [
    "/www/server/panel/vhost/nginx",   # aaPanel
    "/etc/nginx/conf.d",               # klasik
    "/etc/nginx/sites-enabled",        # Debian/Ubuntu
    "/usr/local/nginx/conf/vhost",     # bazı derlemeler
]


def bilgi(m): print(f"\033[1;36m{m}\033[0m")
def basari(m): print(f"\033[1;32m✓ {m}\033[0m")
def uyari(m): print(f"\033[1;33m⚠ {m}\033[0m")
def hata(m): print(f"\033[1;31m✗ {m}\033[0m", file=sys.stderr); sys.exit(1)


def konf_bul(alan: str | None) -> Path:
    """Site yapılandırma dosyasını bulur."""
    adaylar: list[Path] = []
    for dizin in ARAMA_YOLLARI:
        d = Path(dizin)
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.conf")):
            if f.name.startswith(("0.", "phpfpm", "default")):
                continue
            adaylar.append(f)

    if not adaylar:
        hata("Nginx site yapılandırması bulunamadı. --dosya ile yolu belirt.")

    if alan:
        for f in adaylar:
            if alan in f.name or alan in f.read_text(errors="ignore"):
                return f
        hata(f"'{alan}' için yapılandırma bulunamadı. Bulunanlar:\n  " +
             "\n  ".join(str(a) for a in adaylar))

    if len(adaylar) == 1:
        return adaylar[0]

    # Birden fazla site varsa kullanıcıya sor
    print("\nBirden fazla site bulundu:")
    for i, a in enumerate(adaylar, 1):
        print(f"  {i}) {a}")
    secim = input("\nHangisi? (numara): ").strip()
    try:
        return adaylar[int(secim) - 1]
    except (ValueError, IndexError):
        hata("Geçersiz seçim.")


def _server_bloklari(satirlar: list[str]) -> list[tuple[int, int]]:
    """Dosyadaki tüm `server { }` bloklarının (başlangıç, kapanış) satırlarını bulur."""
    bloklar: list[tuple[int, int]] = []
    derinlik = 0
    server_bas: int | None = None
    server_derinlik = 0

    for i, satir in enumerate(satirlar):
        kod = satir.split("#", 1)[0]  # yorumları yok say

        if server_bas is None and kod.strip().startswith("server"):
            server_bas = i
            server_derinlik = derinlik

        for ch in kod:
            if ch == "{":
                derinlik += 1
            elif ch == "}":
                derinlik -= 1
                if server_bas is not None and derinlik == server_derinlik:
                    bloklar.append((server_bas, i))
                    server_bas = None
    return bloklar


def _sadece_yonlendirme(govde: str) -> bool:
    """Blok yalnızca HTTP→HTTPS yönlendirmesi mi yapıyor?

    Sunucu düzeyindeki `return 30x` konum (location) seçiminden ÖNCE çalışır;
    böyle bir bloğa vekil eklemek işe yaramaz.
    """
    derinlik = 0
    for satir in govde.splitlines():
        kod = satir.split("#", 1)[0]
        sade = kod.strip()
        # location gibi iç bloklara girmeden önce sunucu düzeyini incele
        if derinlik == 1 and (
            sade.startswith("return 30")
            or (sade.startswith("rewrite ") and "permanent" in sade)
        ):
            return True
        derinlik += kod.count("{") - kod.count("}")
    return False


def server_bloguna_ekle(icerik: str) -> str:
    """Vekil bloğunu içerik sunan tüm `server { }` bloklarına ekler."""
    satirlar = icerik.splitlines(keepends=True)
    bloklar = _server_bloklari(satirlar)
    if not bloklar:
        return ""

    hedefler = [
        (bas, son) for bas, son in bloklar
        if not _sadece_yonlendirme("".join(satirlar[bas:son + 1]))
    ]
    if not hedefler:  # hepsi yönlendirme ise yine de ilkine ekle
        hedefler = bloklar[:1]

    blok = BLOK.format(isaret=ISARET, isaret_son=ISARET_SON)
    girintili = "\n".join(
        ("    " + s if s.strip() else s) for s in blok.splitlines()
    ) + "\n"

    # Sondan başa doğru ekle ki satır numaraları kaymasın
    for _bas, son in sorted(hedefler, key=lambda x: x[1], reverse=True):
        satirlar.insert(son, girintili)

    return "".join(satirlar)


def nginx_test() -> tuple[bool, str]:
    try:
        p = subprocess.run(["nginx", "-t"], capture_output=True, text=True, timeout=30)
        return p.returncode == 0, (p.stderr or p.stdout)
    except FileNotFoundError:
        return False, "nginx komutu bulunamadı"
    except subprocess.TimeoutExpired:
        return False, "nginx -t zaman aşımı"


def main() -> None:
    ap = argparse.ArgumentParser(description="Nginx'e /envanter vekil bloğunu ekler")
    ap.add_argument("--alan", help="Alan adı (örn. ernsaha.com.tr)")
    ap.add_argument("--dosya", help="Yapılandırma dosyası yolu")
    ap.add_argument("--geri-al", action="store_true", help="Eklenen bloğu kaldır")
    ap.add_argument("--kuru", action="store_true",
                    help="Dosyayı değiştirmeden sonucu göster (deneme)")
    args = ap.parse_args()

    konf = Path(args.dosya) if args.dosya else konf_bul(args.alan)
    if not konf.is_file():
        hata(f"Dosya yok: {konf}")

    bilgi(f"→ Yapılandırma: {konf}")
    icerik = konf.read_text(errors="ignore")

    # ---- Geri alma ----
    if args.geri_al:
        if ISARET not in icerik:
            uyari("Eklenmiş blok bulunamadı, yapacak bir şey yok.")
            return
        bas = icerik.index(ISARET)
        son = icerik.index(ISARET_SON) + len(ISARET_SON)
        konf.write_text(icerik[:bas].rstrip() + "\n" + icerik[son:].lstrip("\n"))
        ok, cikti = nginx_test()
        if ok:
            subprocess.run(["nginx", "-s", "reload"], capture_output=True)
            basari("Blok kaldırıldı ve Nginx yenilendi.")
        else:
            hata(f"nginx -t başarısız:\n{cikti}")
        return

    # ---- Zaten var mı? ----
    if ISARET in icerik:
        basari("Blok zaten ekli, dosya değiştirilmedi.")
        ok, cikti = nginx_test()
        print(cikti.strip())
        return
    if "location /envanter" in icerik:
        uyari("Dosyada zaten bir '/envanter' location bloğu var (elle eklenmiş).")
        uyari("Çakışmayı önlemek için işlem yapılmadı. Kontrol et: " + str(konf))
        return

    # ---- Kuru çalıştırma ----
    if args.kuru:
        yeni = server_bloguna_ekle(icerik)
        if not yeni:
            hata("server { } bloğu bulunamadı.")
        print(yeni)
        return

    # ---- Yedek ----
    damga = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    yedek = konf.with_suffix(konf.suffix + f".envanter-yedek-{damga}")
    shutil.copy2(konf, yedek)
    bilgi(f"→ Yedek alındı: {yedek}")

    # ---- Ekle ----
    yeni = server_bloguna_ekle(icerik)
    if not yeni:
        hata("server { } bloğu bulunamadı. Dosyayı elle düzenlemen gerekiyor:\n"
             f"  {konf}")
    konf.write_text(yeni)
    bilgi("→ Blok eklendi, Nginx yapılandırması test ediliyor…")

    ok, cikti = nginx_test()
    if not ok:
        shutil.copy2(yedek, konf)
        hata(f"nginx -t başarısız — değişiklik GERİ ALINDI.\n{cikti}")

    subprocess.run(["nginx", "-s", "reload"], capture_output=True)
    basari("Nginx yapılandırması eklendi ve yenilendi.")
    print("\n  Şimdi aç:  https://<alan-adin>/envanter/ui/\n")


if __name__ == "__main__":
    main()
