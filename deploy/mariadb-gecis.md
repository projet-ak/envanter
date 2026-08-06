# MariaDB / MySQL'e geçiş

aaPanel'in yönettiği MariaDB'yi kullanmak istersen (panelden yedek, phpMyAdmin
vb. avantajları için) bu adımları izle.

> **Önce oku:** PostgreSQL kurulumun çalışıyorsa geçiş **zorunlu değil**.
> Geçiş, çalışan bir sistemi değiştirmek demektir. aaPanel'den yönetme
> kolaylığı istiyorsan mantıklı; sadece "bir sorunu çözmek" için yapma.

---

## 1. Veritabanını oluştur

**aaPanel'den:** Databases → Add database
- Veritabanı adı: `envanter`
- Kullanıcı: `envanter`
- **Charset/Collation: `utf8mb4`** ← Türkçe karakterler için şart

**Veya komut satırından:**

```bash
mysql -u root -p <<'SQL'
CREATE DATABASE envanter CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'envanter'@'localhost' IDENTIFIED BY 'GUCLU_PAROLA';
GRANT ALL PRIVILEGES ON envanter.* TO 'envanter'@'localhost';
-- Uyumluluk testinin geçici veritabanı açabilmesi için (test sonrası kaldırabilirsin):
GRANT CREATE ON *.* TO 'envanter'@'localhost';
FLUSH PRIVILEGES;
SQL
```

---

## 2. Uyumluluğu DOĞRULA (geçmeden önce)

Bu script geçici bir test veritabanı oluşturur, tüm göçleri uygular, Türkçe
karakterleri / JSON alanları / enum'ları / zimmet akışını / PDF üretimini
dener, sonra temizler. **Mevcut verine dokunmaz.**

```bash
cd /www/wwwroot/ernsaha.com.tr/envanter
./.venv/bin/pip install -r requirements.txt      # PyMySQL sürücüsü
./.venv/bin/python scripts/veritabani_testi.py \
  "mysql+pymysql://envanter:GUCLU_PAROLA@localhost:3306/envanter?charset=utf8mb4"
```

**"✓ 9 testin tamamı geçti"** görmeden geçiş yapma. Hata çıkarsa çıktıyı
paylaş — düzeltilir.

---

## 3. Geçiş

```bash
cd /www/wwwroot/ernsaha.com.tr/envanter

# Mevcut PostgreSQL verini yedekle (geri dönmek istersen)
sudo -u postgres pg_dump -Fc envanter > /root/envanter-postgres-yedek.dump

# .env içindeki DATABASE_URL'i değiştir
nano .env
#   DATABASE_URL=mysql+pymysql://envanter:GUCLU_PAROLA@localhost:3306/envanter?charset=utf8mb4

# Şemayı yeni veritabanında oluştur
./.venv/bin/alembic upgrade head

# Yönetici kullanıcıyı yeniden oluştur (yeni veritabanı boş)
./.venv/bin/python scripts/create_admin.py --username admin --password 'GucluParola'

sudo systemctl restart envanter
```

---

## 4. Veriyi taşımak (PostgreSQL'de veri varsa)

Yeni kurulumda veri yoksa bu adımı atla. Varsa en temiz yol Snipe-IT'ten
yeniden içe aktarmak:

```bash
./.venv/bin/python scripts/import_snipeit.py --dry-run --limit 20
./.venv/bin/python scripts/import_snipeit.py
```

Ya da PostgreSQL'deki veriyi CSV üzerinden taşı:
`GET /io/assets.csv` ile indir → yeni sistemde `POST /io/assets/import`.

---

## Geri dönüş

`.env` içindeki `DATABASE_URL`'i eski PostgreSQL satırına çevirip
`systemctl restart envanter` demen yeterli — PostgreSQL verisi olduğu gibi durur.

---

## MySQL/MariaDB'ye özgü notlar

| Konu | Durum |
|---|---|
| Sürücü | `PyMySQL` (requirements.txt'te) |
| Karakter seti | `utf8mb4` zorunlu — bağlantı dizesinde `?charset=utf8mb4` |
| JSON özel alanlar | MariaDB 10.2+ / MySQL 5.7+ destekler |
| ENUM sütunları | Satır içi ENUM olarak oluşur (PostgreSQL'deki ayrı tip sorunu yok) |
| Bağlantı kopması | `pool_recycle=3600` ayarlı (MySQL `wait_timeout` için) |
| İndeksler | VARCHAR(255) = 1020 bayt, InnoDB DYNAMIC sınırı 3072 — sorun yok |

### Yedekleme

`deploy/yedek.sh` şu an PostgreSQL ve SQLite destekliyor. MySQL için:

```bash
mysqldump --single-transaction --default-character-set=utf8mb4 \
  -u envanter -p envanter | gzip > /www/backup/envanter/envanter_$(date +%F).sql.gz
```

aaPanel'in kendi otomatik yedekleme özelliğini de kullanabilirsin
(Databases → Backup).
