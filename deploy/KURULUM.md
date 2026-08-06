# Sunucu Kurulumu — aaPanel / Ubuntu VPS

Hedef: uygulamayı **https://ernsaha.com.tr/envanter/** adresinde yayınlamak.

Ortam: Ubuntu 26.04 LTS, Python 3.12, aaPanel, 16 GB RAM, 4 çekirdek.

Mimari:

```
Tarayıcı → Nginx (aaPanel, 443) → /envanter → 127.0.0.1:8901 (uvicorn, 4 worker)
                                                     ↓
                                              PostgreSQL
```

Uygulama **doğrudan internete açılmaz**; yalnızca localhost'ta dinler, Nginx
önünde durur. SSL'i aaPanel'in Let's Encrypt'i sağlar.

---

## 1. Dosyaları sunucuya al

SSH ile bağlan:

```bash
ssh root@ernsaha.com.tr
mkdir -p /www/wwwroot/ernsaha.com.tr
cd /www/wwwroot/ernsaha.com.tr
git clone <REPO_ADRESI> envanter
cd envanter
```

> Git yoksa: `apt install -y git`

---

## 2. PostgreSQL veritabanı oluştur

**aaPanel arayüzünden:** App Store → PostgreSQL Manager (kurulu değilse kur) →
Databases → Add. Veritabanı adı `envanter`, kullanıcı `envanter`.

**Veya komut satırından:**

```bash
sudo -u postgres psql <<'SQL'
CREATE USER envanter WITH PASSWORD 'BURAYA_GUCLU_PAROLA';
CREATE DATABASE envanter OWNER envanter;
SQL
```

---

## 3. Otomatik kurulumu çalıştır

```bash
cd /www/wwwroot/ernsaha.com.tr/envanter
sudo bash deploy/kurulum.sh
```

Script şunları yapar: sistem paketleri (Türkçe PDF için DejaVu fontu dahil),
sanal ortam, bağımlılıklar, `.env` üretimi (rastgele `SECRET_KEY`), veritabanı
göçleri, systemd servisi.

**Sonra `.env` dosyasını düzenle:**

```bash
nano /www/wwwroot/ernsaha.com.tr/envanter/.env
```

```ini
DATABASE_URL=postgresql+psycopg2://envanter:PAROLA@localhost:5432/envanter
ORG_NAME=Ernsaha A.Ş.
ROOT_PATH=/envanter
SECRET_KEY=<script otomatik doldurdu, değiştirme>
ANTHROPIC_API_KEY=      # fatura okuma + doğal dil arama için (isteğe bağlı)
```

Değişiklikten sonra:

```bash
sudo systemctl restart envanter
```

---

## 4. Nginx yapılandırması (aaPanel)

aaPanel → **Website** → `ernsaha.com.tr` → **Config** (Yapılandırma).

Açılan `server { ... }` bloğunun **içine**, `deploy/nginx-envanter.conf`
dosyasındaki `location` bloklarını yapıştır → **Save**.

> ⚠️ Blok içindeki `rewrite ^/envanter/?(.*)$ /$1 break;` satırı **şart**.
> Uygulama kendi içinde `/ui/`, `/assets` yollarını sunar; `/envanter` ön eki
> Nginx tarafından kırpılmazsa her istek 404 döner.

Nginx'i yenile:

```bash
nginx -t && systemctl reload nginx
```

---

## 5. Yönetici kullanıcı oluştur

```bash
cd /www/wwwroot/ernsaha.com.tr/envanter
./.venv/bin/python scripts/create_admin.py --username admin --password 'GucluParola'
```

Artık **https://ernsaha.com.tr/envanter/ui/** adresinden giriş yapabilirsin.

---

## 6. Otomatik yedekleme (önerilir)

```bash
sudo cp deploy/yedek.sh /usr/local/bin/envanter-yedek
sudo chmod +x /usr/local/bin/envanter-yedek
sudo crontab -e
```

Şu satırı ekle (her gece 03:00, 30 gün saklama):

```cron
0 3 * * * /usr/local/bin/envanter-yedek >> /var/log/envanter-yedek.log 2>&1
```

Elle yedek/geri yükleme:

```bash
/usr/local/bin/envanter-yedek                          # yedek al
gunzip -c /www/backup/envanter/envanter_2026-06-11_0300.dump.gz \
  | pg_restore -d "postgresql://envanter:PAROLA@localhost/envanter" --clean
```

---

## 7. Snipe-IT verisini taşı

```bash
cd /www/wwwroot/ernsaha.com.tr/envanter
nano .env      # SNIPEIT_URL ve SNIPEIT_TOKEN ekle

# Önce güvenli deneme (hiçbir şey yazmaz):
./.venv/bin/python scripts/import_snipeit.py --dry-run --limit 20

# Sonuç doğruysa tam aktarım:
./.venv/bin/python scripts/import_snipeit.py
```

---

## Günlük yönetim

| İşlem | Komut |
|---|---|
| Durum | `systemctl status envanter` |
| Canlı log | `journalctl -u envanter -f` |
| Yeniden başlat | `systemctl restart envanter` |
| Güncelle | `git pull && ./.venv/bin/pip install -r requirements.txt && ./.venv/bin/alembic upgrade head && systemctl restart envanter` |

---

## Sorun giderme

**502 Bad Gateway**
Uygulama çalışmıyordur: `systemctl status envanter` ve `journalctl -u envanter -n 50`.
Genelde `.env` içindeki `DATABASE_URL` hatalıdır.

**Her şey 404 veriyor**
Nginx `/envanter` ön ekini kırpmıyordur. Blokta
`rewrite ^/envanter/?(.*)$ /$1 break;` satırı bulunmalı. Ayrım için:

```bash
curl -s -o /dev/null -w "uygulama: %{http_code}\n" http://127.0.0.1:8901/ui/
```

200 dönüyorsa uygulama sağlamdır, sorun Nginx yapılandırmasındadır.

**Arayüz açılıyor ama QR kodu / PDF / CSV 404 veriyor**
aaPanel'in statik dosya regex kuralı (`location ~ .*\.(png|jpg)$`) bu
uzantıları yakalıyordur. Yapılandırmada
`location ~ ^/envanter/.*\.(pdf|png|csv|...)$` bloğunun bulunduğundan emin ol.

**PDF'lerde Türkçe karakterler bozuk (□□□)**
DejaVu fontu eksik: `apt install -y fonts-dejavu-core && systemctl restart envanter`.

**Fatura okuma "503" veriyor**
`.env` içinde `ANTHROPIC_API_KEY` yok. Ekleyip `systemctl restart envanter`.
(Bu olmadan sistemin geri kalanı normal çalışır.)

**Giriş yapılıyor ama hemen çıkıyor**
`SECRET_KEY` değişmiştir (her değişiklikte mevcut oturumlar geçersiz olur).
Yeniden giriş yapmak yeterli.

**Yükleme "413" hatası**
Nginx `client_max_body_size` küçük. Yapılandırmada `12m` olduğundan emin ol.
