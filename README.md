# Envanter

Esnek ve stabil BT envanter yönetim sistemi — **Snipe-IT alternatifi**.
Verilerin senin elinde (PostgreSQL), şema değişiklikleri kontrollü, doğal dil
ile arama Claude ile yapılır.

> Amaç: Snipe-IT'in güncelleme/bakım yükünden ve kırılganlığından kurtulmak,
> veriyi kaybetmeden daha sade ve esnek bir sisteme geçmek.

## Neden bu yığın?

| Bileşen | Sebep |
|---|---|
| **PostgreSQL** | Çok stabil; `pg_dump` ile saniyeler içinde yedek → veri güvenliği |
| **FastAPI** | Sade, hızlı, otomatik API dokümanı (`/docs`); bakımı hafif |
| **SQLAlchemy + Alembic** | Şema değişiklikleri kontrollü göçlerle (sonraki adım) |
| **Claude (Opus 4.8)** | Doğal dil sorgusunu güvenli, parametreli filtreye çevirir |
| **JSON özel alanlar** | Şema değiştirmeden alan ekle → Snipe-IT custom fields'in esnek hali |

## Hızlı başlangıç

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # ayarları düzenle

# Geliştirme için DATABASE_URL'i sqlite yapabilirsin (kurulum gerektirmez):
#   DATABASE_URL=sqlite:///./envanter.db

uvicorn app.main:app --reload
```

İlk yönetici kullanıcıyı oluştur (giriş için gerekir):

```bash
python scripts/create_admin.py --username admin --password "GucluParola"
```

- Web arayüzü: <http://localhost:8000/ui/>
- API dokümanı: <http://localhost:8000/docs>
- Sağlık kontrolü: <http://localhost:8000/health>

## Kimlik doğrulama ve roller

Giriş JWT ile yapılır. Üç rol vardır:

| Rol | Yetki |
|---|---|
| `admin` | Her şey + kullanıcı yönetimi |
| `editor` | Okuma + yazma (ekle/güncelle/sil, zimmet) |
| `viewer` | Sadece okuma |

```bash
# Giriş → token al
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"GucluParola"}'
# Korumalı uca istek
curl http://localhost:8000/assets -H "Authorization: Bearer <TOKEN>"
```

> ⚠️ Üretimde `SECRET_KEY`'i mutlaka ayarla (`openssl rand -hex 32`). Snipe-IT'ten
> içe aktarılan kullanıcılar parolasız gelir (giriş yapamaz); birini yönetici
> yapmak için `create_admin.py`'yi o kullanıcı adıyla çalıştır.

## Sunucuya kurulum (VPS / aaPanel)

Uygulamayı kendi sunucunda yayınlamak için: **[deploy/KURULUM.md](deploy/KURULUM.md)**

Kısaca:

```bash
git clone <repo> /www/wwwroot/ernsaha.com.tr/envanet
cd /www/wwwroot/ernsaha.com.tr/envanet
sudo bash deploy/kurulum.sh          # paketler, venv, .env, göçler, systemd
nano .env                            # DATABASE_URL, ORG_NAME, ANTHROPIC_API_KEY
sudo systemctl restart envanter
```

Sonra aaPanel → Website → Config'e `deploy/nginx-envanet.conf` içeriğini ekle.

| Dosya | İşlev |
|---|---|
| `deploy/kurulum.sh` | Tek komutla kurulum (tekrar çalıştırılabilir) |
| `deploy/envanter.service` | systemd servisi (4 worker, otomatik yeniden başlatma) |
| `deploy/nginx-envanet.conf` | Nginx alt klasör (`/envanet`) vekil ayarı |
| `deploy/yedek.sh` | Günlük otomatik veritabanı yedeği (cron ile) |

### Alt klasörde yayın

Uygulama alt klasörde çalışabilir (örn. `https://site.com/envanet/`):
`.env` içinde `ROOT_PATH=/envanet` yeter — arayüz API adreslerini kendi
bulunduğu yoldan türetir, ek ayar gerekmez.

## PostgreSQL (önerilen, üretim)

```bash
# Örnek kurulum
sudo -u postgres createuser envanter --pwprompt
sudo -u postgres createdb envanter -O envanter
# .env içinde:
# DATABASE_URL=postgresql+psycopg2://envanter:PAROLA@localhost:5432/envanter
```

Üretimde şemayı Alembic göçleriyle oluştur (sqlite'ta tablolar otomatik
oluşur; PostgreSQL'de göç çalıştırmalısın):

```bash
alembic upgrade head
```

### Şema değişiklikleri (göçler)

Modeli değiştirdiğinde yeni bir göç üret, sonra uygula:

```bash
alembic revision --autogenerate -m "açıklama"
alembic upgrade head
```

Böylece "güncelleme her şeyi bozdu" durumu olmaz — her değişiklik sürümlenir
ve geri alınabilir (`alembic downgrade -1`).

### Yedekleme (veri kaybolmasın)

```bash
# Tam yedek
pg_dump -Fc envanter > yedek_$(date +%F).dump
# Geri yükleme
pg_restore -d envanter --clean yedek_2026-06-11.dump
```

Otomatik günlük yedek için bu komutu bir cron işine koyman yeterli.

## Snipe-IT'ten veri taşıma

Salt-okunur, **tekrar çalıştırılabilir** (idempotent) içe aktarım. Snipe-IT'ten
hiçbir şey silinmez; veriler REST API üzerinden okunur.

1. Snipe-IT'te bir API token oluştur (Profil → Manage API Keys).
2. `.env` içine `SNIPEIT_URL` ve `SNIPEIT_TOKEN` gir.
3. Çalıştır:

```bash
# Önce güvenli deneme (hiçbir şey yazmaz, ne aktarılacağını gösterir):
python scripts/import_snipeit.py --dry-run --limit 20

# Gerçek aktarım:
python scripts/import_snipeit.py
```

Taşınan veriler: kategoriler, üreticiler, tedarikçiler, şirketler, durum
etiketleri, lokasyonlar (hiyerarşi dahil), modeller, kullanıcılar, varlıklar
(zimmet durumu ve özel alanlar dahil), **aksesuarlar, sarf malzemeleri,
bileşenler ve lisanslar**. Script birden çok kez çalıştırılabilir;
`external_id` eşlemesi sayesinde veriyi çoğaltmaz, günceller.

| Seçenek | Açıklama |
|---|---|
| `--dry-run` | Yazmadan dener; her türden kaç kayıt aktarılacağını gösterir |
| `--limit N` | Her türden en fazla N kayıt (hızlı deneme için) |

## Kuruma özel alanlar

Snipe-IT'in standart alanlarına ek olarak, kendi kullanımımıza göre eklenen
alanlar (hepsi CSV içe/dışa aktarımda ve aramada desteklenir):

| Grup | Alanlar |
|---|---|
| Demirbaş / muhasebe | `demirbas_no`, `muhasebe_kodu`, `fatura_no`, `warranty_end` |
| Etiket / teknik | `barkod`, `imei`, `mac_address`, `ip_address`, `hostname` |
| Telefon / hat | `telefon_no`, `sim_no`, `operator` |
| Personel (kullanıcı) | `tckn`, `sube`, `telefon`, `ise_giris`, `employee_num`, `department` |

Bunların dışında kalan her şey için `custom` (JSON) alanı var — şema
değiştirmeden istediğin alanı ekleyebilirsin.

## Zimmet / iade tutanağı (PDF)

Personele cihaz teslim ederken imzalatılacak tutanağı sistem üretir — Türkçe
karakterler gömülü fontla doğru basılır.

```bash
# Tek cihaz için zimmet fişi
GET /documents/zimmet/asset/{asset_id}.pdf
# Personele zimmetli tüm cihazlar tek tutanakta
GET /documents/zimmet/user/{user_id}.pdf
# İade tutanağı + not
GET /documents/zimmet/user/{user_id}.pdf?doc_type=iade&note=Ekran%20çizik
```

Tutanakta: kurum başlığı (`ORG_NAME`), personel bilgileri (ad, sicil,
departman, şube), cihaz tablosu (etiket, demirbaş no, seri, barkod), taahhüt
metni, tarih ve **imza alanları** bulunur. Arayüzde zimmetli cihazın satırındaki
📄 butonundan açılır.

## Barkod / QR etiket

Cihazlara yapıştırılacak etiketleri sistem üretir; okutunca cihaz anında bulunur.

```bash
GET  /documents/etiket/asset/{id}.png   # tek QR kod görseli
GET  /documents/etiket/asset/{id}.pdf   # tek yazdırılabilir etiket
POST /documents/etiketler.pdf           # toplu etiket sayfası (A4'te 24 etiket)
GET  /documents/tara?kod=BT-0001        # okutulan kodu varlıkla eşleştir
```

Etikette: kurum adı, varlık etiketi, cihaz adı, demirbaş no, **QR kod** ve
**Code128 barkod**. Toplu üretimde `asset_ids` veya `location_id` ile seçim,
`start_offset` ile yarım kalmış etiket kağıdını kullanma desteği var.

Okutma (`/documents/tara`) şu alanlarla eşleşir: varlık etiketi, demirbaş no,
barkod, seri no, IMEI. Arayüzdeki "Barkod / QR okut" kutusuna el tipi okuyucuyla
okutmak yeterli (okuyucu Enter gönderir, cihaz anında listelenir).

## Raporlar ve dashboard

Arayüzdeki **Özet** sekmesi ve `/reports/*` uçları:

| Uç | İçerik |
|---|---|
| `GET /reports/ozet` | Toplam varlık, zimmetli/boşta, toplam değer, personel/lisans sayıları |
| `GET /reports/dagilim` | Kategori, lokasyon, üretici ve duruma göre dağılım |
| `GET /reports/dusuk-stok` | Adedi minimumun altına düşen aksesuar/sarf/bileşenler |
| `GET /reports/garanti?gun=90` | Garantisi biten/bitecek cihazlar (kalan gün ile) |
| `GET /reports/personel-zimmet` | Personel başına zimmetli cihaz sayısı |
| `GET /reports/lisans-kullanim` | Lisans koltukları ve süresi dolanlar |

## Doğal dil arama

`ANTHROPIC_API_KEY` ayarlıysa, sorgular Claude ile yapısal filtreye çevrilir.
Anahtar yoksa sistem serbest-metin aramasıyla çalışmaya devam eder.

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"q": "depodaki boştaki Dell laptoplar"}'
```

Yanıt, Claude'un sorguyu nasıl yorumladığını (`interpreted_filter`) ve eşleşen
varlıkları döner. **Güvenlik:** Modele asla ham SQL yazdırılmaz; yalnızca
yapısal bir filtre üretir, o da parametreli sorguya çevrilir.

## Fatura / irsaliye okuma (Claude vision)

Fatura fotoğrafını veya PDF'ini yükle; Claude ürün kalemlerini çıkarsın.
**Onaylamadan hiçbir şey kaydedilmez** — kalemleri düzenleyip seçebilirsin.

```bash
POST /invoices/oku     # dosya yükle → kalemleri çıkar (önizleme, kaydetmez)
POST /invoices/aktar   # onaylanan kalemleri envantere ekle
```

- Desteklenen biçimler: JPEG, PNG, GIF, WebP, PDF (en fazla 10 MB).
- Hizmet/kargo/KDV satırları kalem olarak alınmaz; Türkçe sayı biçimi
  (1.250,50) doğru ayrıştırılır.
- Aktarımda her kalem **adet kadar ayrı varlık** oluşturur; etiketler
  ön eke göre otomatik üretilir (NB-0001, NB-0002…) ve çakışma olmaz.
- `ANTHROPIC_API_KEY` gerektirir; yoksa uç 503 döner (sistemin geri kalanı
  etkilenmez).

## API uçları (özet)

| Yöntem | Yol | Açıklama |
|---|---|---|
| `GET/POST` | `/assets` | Varlık listele / oluştur |
| `GET/PUT/DELETE` | `/assets/{id}` | Varlık görüntüle / güncelle / sil |
| `POST` | `/assets/{id}/checkout` | Zimmetle (kullanıcı/lokasyon/varlık) |
| `POST` | `/assets/{id}/checkin` | İade al |
| `GET` | `/assets/{id}/history` | Varlık geçmişi |
| `POST` | `/search` | Doğal dil araması |
| `GET` | `/io/assets.csv` | Varlıkları CSV olarak indir |
| `POST` | `/io/assets/import` | CSV'den varlık içe aktar (etikete göre ekle/güncelle) |
| `*` | `/accessories`, `/consumables`, `/components`, `/licenses` | Aksesuar / sarf / bileşen / lisans CRUD |
| `*` | `/categories`, `/manufacturers`, `/suppliers`, `/companies`, `/locations`, `/status-labels`, `/models`, `/users`, `/custom-fields` | Referans tabloları CRUD |

Tam liste ve deneme için `/docs`.

## Testler

```bash
pip install -r requirements-dev.txt
pytest
```

Testler API uçlarını ve **Snipe-IT veri taşımayı** (sahte API yanıtlarıyla,
gerçek Snipe-IT gerektirmeden) kapsar.

## Yol haritası

- [x] Alembic göçleri (üretimde `create_all` yerine)
- [x] Basit web arayüzü (`/ui/`) — giriş ekranı dahil
- [x] Otomatik testler (pytest)
- [x] Kimlik doğrulama + rol/izin (JWT: admin/editor/viewer)
- [x] Aksesuar / sarf malzeme / lisans / bileşen türleri
- [x] CSV içe/dışa aktarım (varlıklar)
- [x] Web arayüzünde diğer varlık türleri için ekranlar (sekmeli + düşük stok uyarısı)
- [x] Fatura/irsaliye görselinden otomatik varlık çıkarımı (Claude vision)
- [x] Raporlar / dashboard, barkod-QR etiket, zimmet tutanağı

## Proje yapısı

```
app/
  main.py            # FastAPI uygulaması
  config.py          # Ayarlar (.env)
  database.py        # DB bağlantısı/oturum
  auth.py            # JWT + parola hash + rol bağımlılıkları
  models.py          # ORM modelleri (tüm varlıklar)
  schemas.py         # Pydantic şemaları
  crud_factory.py    # Referans tabloları için jenerik CRUD
  seed.py            # Varsayılan durum etiketleri
  ai/search.py       # Doğal dil → yapısal filtre (Claude)
  routers/           # API uçları
  static/index.html  # Basit web arayüzü
alembic/             # Veritabanı göçleri
scripts/
  import_snipeit.py  # Snipe-IT'ten veri taşıma
  create_admin.py    # Admin kullanıcı oluştur/yükselt
tests/               # pytest (API + içe aktarım + kimlik doğrulama)
```
