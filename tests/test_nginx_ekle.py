"""deploy/nginx-ekle.py — Nginx yapılandırmasına blok ekleme testleri.

Bu script sunucudaki canlı Nginx yapılandırmasını düzenlediği için
davranışının doğrulanması kritik: yanlış yere eklenen bir blok siteyi
çökertebilir veya uygulamanın hiç çalışmamasına yol açabilir.
"""

import importlib.util
from pathlib import Path

import pytest

# deploy/ bir paket olmadığı için modülü doğrudan yükle
_YOL = Path(__file__).resolve().parent.parent / "deploy" / "nginx-ekle.py"
_spec = importlib.util.spec_from_file_location("nginx_ekle", _YOL)
nginx_ekle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nginx_ekle)


TEK_SERVER = """server
{
    listen 80;
    listen 443 ssl http2;
    server_name ernsaha.com.tr;
    root /www/wwwroot/ernsaha.com.tr;

    #SSL-START
    ssl_certificate /www/server/panel/vhost/cert/ernsaha.com.tr/fullchain.pem;
    #SSL-END

    location ~ .*\\.(gif|jpg|png)$
    {
        expires 30d;
    }

    access_log /www/wwwlogs/ernsaha.com.tr.log;
}
"""

CIFT_SERVER = """server {
    listen 80;
    server_name ernsaha.com.tr;
    return 301 https://$host$request_uri;
}

server
{
    listen 443 ssl http2;
    server_name ernsaha.com.tr;
    root /www/wwwroot/ernsaha.com.tr;
    location / {
        try_files $uri $uri/ /index.php;
    }
}
"""


def _denge(metin: str) -> int:
    """Yorumları atarak süslü parantez dengesini hesaplar."""
    d = 0
    for satir in metin.splitlines():
        kod = satir.split("#", 1)[0]
        d += kod.count("{") - kod.count("}")
    return d


def test_tek_server_blogu_icine_eklenir():
    sonuc = nginx_ekle.server_bloguna_ekle(TEK_SERVER)
    assert sonuc, "Ekleme başarısız"
    assert sonuc.count(nginx_ekle.ISARET) == 1
    assert _denge(sonuc) == 0, "Parantez dengesi bozuldu"
    # Blok kapanış parantezinden ÖNCE olmalı (yani server içinde)
    assert sonuc.index(nginx_ekle.ISARET_SON) < sonuc.rstrip().rfind("\n}")


def test_orijinal_yapilandirma_korunur():
    sonuc = nginx_ekle.server_bloguna_ekle(TEK_SERVER)
    for parca in ["ssl_certificate", "access_log", "server_name ernsaha.com.tr",
                  "expires 30d"]:
        assert parca in sonuc, f"Kaybolan satır: {parca}"


def test_yonlendirme_bloguna_eklenmez():
    """HTTP→HTTPS yönlendiren bloğa eklenirse uygulama hiç çalışmaz.

    Sunucu düzeyindeki `return 301` location seçiminden önce çalışır.
    """
    sonuc = nginx_ekle.server_bloguna_ekle(CIFT_SERVER)
    assert sonuc.count(nginx_ekle.ISARET) == 1, "Tam olarak bir bloğa eklenmeli"

    yonlendirme_sonu = sonuc.index("return 301")
    isaret_yeri = sonuc.index(nginx_ekle.ISARET)
    assert isaret_yeri > yonlendirme_sonu, "Blok yönlendirme bloğuna eklenmiş!"
    # HTTPS bloğunun içinde olmalı
    https_bas = sonuc.index("listen 443")
    assert isaret_yeri > https_bas
    assert _denge(sonuc) == 0


def test_server_blogu_yoksa_bos_doner():
    assert nginx_ekle.server_bloguna_ekle("# yalnızca yorum\n") == ""


def test_sadece_yonlendirme_tespiti():
    assert nginx_ekle._sadece_yonlendirme(
        "server {\n  listen 80;\n  return 301 https://$host$request_uri;\n}"
    )
    assert not nginx_ekle._sadece_yonlendirme(
        "server {\n  listen 443;\n  root /var/www;\n}"
    )
    # location içindeki return yönlendirme sayılmaz
    assert not nginx_ekle._sadece_yonlendirme(
        "server {\n  listen 443;\n  location /eski {\n    return 301 /yeni;\n  }\n}"
    )


def test_blok_gerekli_ayarlari_icerir():
    sonuc = nginx_ekle.server_bloguna_ekle(TEK_SERVER)
    assert "proxy_pass http://127.0.0.1:8901;" in sonuc
    assert "X-Forwarded-Prefix /envanter" in sonuc
    assert "client_max_body_size 12m" in sonuc


def test_onek_kirpiliyor():
    """/envanter ön eki uygulamaya iletilmeden ÖNCE kırpılmalı.

    Uygulama --root-path /envanter ile çalışsa bile kendi yolları /ui/,
    /assets şeklindedir; ön ek kırpılmazsa her istek 404 döner.
    (Bu davranış uvicorn üzerinde ölçülerek doğrulanmıştır.)
    """
    sonuc = nginx_ekle.server_bloguna_ekle(TEK_SERVER)
    assert sonuc.count("rewrite ^/envanter/?(.*)$ /$1 break;") == 2, \
        "Hem prefix hem regex location'da ön ek kırpılmalı"


def test_statik_uzantilar_vekile_yonlenir():
    """QR (.png), etiket/tutanak (.pdf) ve dışa aktarım (.csv) uygulamadan gelir.

    aaPanel'in `location ~ .*\\.(png|jpg)$` gibi regex kuralları prefix
    location'dan önce eşleşir; bu blok olmazsa üretilen dosyalar 404 olur.
    """
    sonuc = nginx_ekle.server_bloguna_ekle(TEK_SERVER)
    regex_satiri = next(
        s for s in sonuc.splitlines() if s.strip().startswith("location ~ ^/envanter/")
    )
    for uzanti in ("pdf", "png", "csv"):
        assert uzanti in regex_satiri, f"{uzanti} regex bloğunda yok"


def test_regex_location_proxy_pass_uri_icermez():
    """Nginx, regex location'da URI'li proxy_pass'i reddeder.

    `proxy_pass http://host/;` (sondaki eğik çizgi) regex location'da
    "cannot have URI part" hatası verir; bu yüzden kırpma rewrite ile yapılır.
    """
    sonuc = nginx_ekle.server_bloguna_ekle(TEK_SERVER)
    assert "proxy_pass http://127.0.0.1:8901/;" not in sonuc, \
        "Regex location'da URI'li proxy_pass nginx -t hatası verir"


@pytest.mark.parametrize("konf", [TEK_SERVER, CIFT_SERVER])
def test_ekleme_tekrarlanabilir_degil(konf):
    """İkinci kez eklenmemeli (script zaten var kontrolü yapıyor)."""
    bir = nginx_ekle.server_bloguna_ekle(konf)
    assert nginx_ekle.ISARET in bir
    # Script çağrı katmanında "zaten ekli" kontrolü var; burada işaret sayısı
    # tek olmalı ki o kontrol çalışsın.
    assert bir.count(nginx_ekle.ISARET) == 1
