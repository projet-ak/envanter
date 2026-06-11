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
python scripts/import_snipeit.py
```

Taşınan veriler: kategoriler, üreticiler, tedarikçiler, şirketler, durum
etiketleri, lokasyonlar (hiyerarşi dahil), modeller, kullanıcılar, varlıklar
(zimmet durumu ve özel alanlar dahil). Script birden çok kez çalıştırılabilir;
`external_id` eşlemesi sayesinde veriyi çoğaltmaz, günceller.

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

## API uçları (özet)

| Yöntem | Yol | Açıklama |
|---|---|---|
| `GET/POST` | `/assets` | Varlık listele / oluştur |
| `GET/PUT/DELETE` | `/assets/{id}` | Varlık görüntüle / güncelle / sil |
| `POST` | `/assets/{id}/checkout` | Zimmetle (kullanıcı/lokasyon/varlık) |
| `POST` | `/assets/{id}/checkin` | İade al |
| `GET` | `/assets/{id}/history` | Varlık geçmişi |
| `POST` | `/search` | Doğal dil araması |
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
- [ ] Aksesuar / sarf malzeme / lisans / bileşen türleri (model bunlara hazır)
- [ ] Fatura/irsaliye görselinden otomatik varlık çıkarımı (Claude vision)
- [ ] CSV içe/dışa aktarım

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
