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

- API dokümanı: <http://localhost:8000/docs>
- Sağlık kontrolü: <http://localhost:8000/health>

## PostgreSQL (önerilen, üretim)

```bash
# Örnek kurulum
sudo -u postgres createuser envanter --pwprompt
sudo -u postgres createdb envanter -O envanter
# .env içinde:
# DATABASE_URL=postgresql+psycopg2://envanter:PAROLA@localhost:5432/envanter
```

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

## Yol haritası (sonraki adımlar)

- [ ] Alembic göçleri (üretimde `create_all` yerine)
- [ ] Kimlik doğrulama + rol/izin (JWT)
- [ ] Web arayüzü
- [ ] Aksesuar / sarf malzeme / lisans / bileşen türleri (model bunlara hazır)
- [ ] Fatura/irsaliye görselinden otomatik varlık çıkarımı (Claude vision)
- [ ] CSV içe/dışa aktarım
- [ ] Otomatik testler (pytest)

## Proje yapısı

```
app/
  main.py            # FastAPI uygulaması
  config.py          # Ayarlar (.env)
  database.py        # DB bağlantısı/oturum
  models.py          # ORM modelleri (tüm varlıklar)
  schemas.py         # Pydantic şemaları
  crud_factory.py    # Referans tabloları için jenerik CRUD
  seed.py            # Varsayılan durum etiketleri
  ai/search.py       # Doğal dil → yapısal filtre (Claude)
  routers/           # API uçları
scripts/
  import_snipeit.py  # Snipe-IT'ten veri taşıma
```
