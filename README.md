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

## Arayüz

Sol menü + üst bar düzeni. Menü iki bölümdür: günlük işler (Kontrol Paneli,
Varlıklar, **Ağ Ürünleri**, **Yangın Sistemleri**, **Alarm Sistemleri**,
**Geçiş Sistemleri**, **Kantar Sistemi**, Personel,
Aksesuar/Sarf/Bileşen/Lisans) ve
**Yönetim** (Tanımlar,
Excel Aktarım, Fatura Oku, Ayarlar). Üst barda her yerden çalışan arama
kutusu, oturum sayacı, koyu/açık tema düğmesi ve kullanıcı kartı bulunur.

Tema tercihi tarayıcıda saklanır; oturum sayacı jetonun bitişini gösterir ve
süre dolduğunda giriş sayfasına döner.

## Kimlik doğrulama ve roller

Giriş ayrı bir sayfadadır: **`/login`**. Oturumu olmayan kullanıcı arayüze
girmeye çalıştığında `?redirect=` ile buraya yönlenir ve giriş sonrası
bulunduğu sayfaya geri döner:

```
https://site.com/envanter/login?redirect=%2Fenvanter%2Fui%2F
```

> `redirect` yalnızca **bu sitedeki yollara** izin verir (`/…`). Tam URL ya da
> `//baska.site` gelirse yok sayılıp arayüzün köküne dönülür — açık
> yönlendirme (open redirect) açığı oluşmasın diye.

Giriş JWT ile yapılır. Üç rol vardır:

| Rol | Yetki |
|---|---|
| `admin` | Her şey + kullanıcı yönetimi |
| `editor` | Okuma + yazma (ekle/güncelle/sil, zimmet) |
| `viewer` | Sadece okuma |

### Kullanıcı ayarları

**Ayarlar** ekranının bölümleri:

| Bölüm | Kim görür | Ne yapar |
|---|---|---|
| Profilim | herkes | Ad, soyad, e-posta, telefon |
| Parola | herkes | Kendi parolasını değiştirir (mevcut parola sorulur) |
| Kullanıcı hesapları | yalnızca `admin` | Kullanıcı adı, yetki, parola sıfırlama, hesap açma/kapatma |
| Yedekleme | yalnızca `admin` | Yedek al, listele, indir, sil (bkz. *Yedekleme*) |

Ayrı bir kullanıcı tablosu yoktur — aynı kişi hem personel hem kullanıcıdır.
**+ Kullanıcı ekle** penceresi iki yol sunar:

| Yol | Ne zaman |
|---|---|
| Kayıtlı personele yetki ver | Kişi zaten sistemde: ara, seç, kullanıcı adı + parola + yetki gir |
| Yeni kişi oluştur | Kişi sistemde yok: kişi bilgileri ve giriş bilgileri tek formda |

Yeni kişi formunda giriş bilgilerini boş bırakırsan kişi yalnızca personel
olarak eklenir (zimmet alabilir ama sisteme giremez). Kullanıcı adı çakışırsa
oluşturulan kişi kaydı geri alınır — yarım kalmış kayıt birikmez.

```bash
curl -X PUT -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"username":"mehmet","yeni_parola":"GucluParola1","role":"editor"}' \
  "$API/users/42/hesap"
```

Bir kullanıcıyı **yönetici yapmak** için hesap listesindeki yetki kutusundan
"Yönetici"yi seçmeniz yeterli; yeni kullanıcı eklerken de yetki formda seçilir.

Sistem yöneticisiz kalamaz: kendi yetkinizi düşüremez, kendi hesabınızı
kapatamazsınız; giriş yapabilen son yöneticiyi devre dışı bırakacak her
değişiklik geri alınır.

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
git clone <repo> /www/wwwroot/ernsaha.com.tr/envanter
cd /www/wwwroot/ernsaha.com.tr/envanter
sudo bash deploy/kurulum.sh          # paketler, venv, .env, göçler, systemd
nano .env                            # DATABASE_URL, ORG_NAME, ANTHROPIC_API_KEY
sudo systemctl restart envanter
```

Sonra aaPanel → Website → Config'e `deploy/nginx-envanter.conf` içeriğini ekle.

| Dosya | İşlev |
|---|---|
| `deploy/kurulum.sh` | Tek komutla kurulum (tekrar çalıştırılabilir) |
| `deploy/envanter.service` | systemd servisi (4 worker, otomatik yeniden başlatma) |
| `deploy/nginx-envanter.conf` | Nginx alt klasör (`/envanter`) vekil ayarı |
| `deploy/yedek.sh` | Günlük otomatik veritabanı yedeği (cron ile) |

### Alt klasörde yayın

Uygulama alt klasörde çalışabilir (örn. `https://site.com/envanter/`).
**İki parça birlikte** çalışır:

1. **Nginx ön eki kırpar** — `rewrite ^/envanter/?(.*)$ /$1 break;`
   Uygulamanın kendi yolları `/ui/`, `/assets` şeklindedir; ön ek kırpılmazsa
   **tüm istekler 404 döner**. `deploy/nginx-envanter.conf` bunu içerir.
2. **`.env` → `ROOT_PATH=/envanter`** — yalnızca uygulamanın *ürettiği*
   adreslere (OpenAPI/`/docs`) ön ek ekler; yönlendirmeye karışmaz. Arayüz
   API adreslerini zaten bulunduğu yoldan türetir.

> Ön ek, FastAPI kurucusuna `root_path=` olarak **verilmez**. Verilseydi
> StaticFiles bağlaması yolu ön ekle beklerdi ve Nginx zaten kırptığı için
> `/ui/` 404 dönerdi. `tests/test_alt_klasor.py` bu tuzağı kapalı tutar.

Kurulumu doğrulamak için:

```bash
bash scripts/kurulum-kontrol.sh
# dışarıdan erişimi de sınamak için:
ADRES=https://ernsaha.com.tr/envanter bash scripts/kurulum-kontrol.sh
```

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

## Sistem ürünleri (ağ, yangın, alarm, geçiş, kantar)

Sol menüde beş bölüm vardır: **Ağ Ürünleri**, **Yangın Sistemleri**,
**Alarm Sistemleri**, **Geçiş Sistemleri** ve **Kantar Sistemi**. Hepsi aynı
makineyi kullanır — ayrı bir tablo değildir, normal varlıklardır; bu yüzden
zimmet, dosya eki, etiket basma ve arama aynen çalışır. Fark, her türün kendi
teknik alan listesi olmasıdır.

### 🌐 Ağ Ürünleri

| Alt kategori | Türe özel alanlar |
|---|---|
| 🔀 Switch | Port sayısı, port hızı, **PoE** (yok/PoE/PoE+/PoE++), PoE bütçesi, **ağdaki yeri** (erişim/dağıtım/**omurga**), yönetilebilirlik, uplink, stack, VLAN, rack U |
| 🔌 SFP / Modül | Hız, dalga boyu, mesafe, mod (single/multi), konnektör |
| 📶 Access Point | Wi-Fi standardı, bantlar, PoE, anten, montaj |
| 🛡️ Güvenlik Duvarı | Port, WAN, firewall/VPN throughput, eşzamanlı oturum, VPN tipi, lisans bitişi, HA, rack U |
| 🔭 Noktadan Noktaya Link | Frekans, hız, menzil, anten kazancı (dBi), PtP/PtMP, master/slave, **karşı uç**, PoE |
| 📡 Router / Modem | Port, WAN, throughput, bağlantı tipi (fiber/VDSL/4G…), ağdaki yeri |
| 📱 Mobil İnternet / Superbox | Cihaz tipi (Superbox / Vinn-MiFi / USB modem / SIM'li router), şebeke nesli (4G-4.5G-5G), Wi-Fi standardı, bağlanabilen cihaz, **tarife/kota**, taahhüt bitişi, batarya — ayrıca künyede **operatör, hat no, SIM no, IMEI** |
| 🎥 NVR / Kayıt Cihazı | Kanal sayısı, PoE portu, PoE bütçesi, disk yuvası, takılı disk, RAID, azami çözünürlük, kayıt süresi |
| 🗄️ Kabinet / Patch Panel | Boyut (U), port sayısı, kablo kategorisi, derinlik |

### 🔥 Yangın Sistemleri

| Alt kategori | Türe özel alanlar |
|---|---|
| 🚨 Yangın Alarm Paneli | Adresli/konvansiyonel, çevrim (loop) sayısı, çevrim başına adres, zon, siren çıkışı, batarya, yedekleme süresi, ağ bağlantısı, sertifika (EN 54…) |
| 🔎 Dedektör / Sensör | Algılama tipi (optik duman / iyonize / ısı / kombine / alev / gaz / aspirasyon), adresli mi, adres, kapsama alanı (m²), montaj, IP sınıfı |
| 🔔 Buton / Siren | Cihaz tipi (ihbar butonu / siren / flaşör), adresli mi, adres, ses seviyesi (dB), iç-dış mekan, IP sınıfı, besleme |
| 📡 Beam Dedektör / Yansıtıcı | Parça tipi (verici-alıcı / verici / alıcı / **yansıtıcı prizma**), menzil, yansıtıcı sayısı, hizalama, adres, montaj yüksekliği |
| 🧯 Diğer Yangın Ekipmanı | Giriş/çıkış modülü, izolatör, tekrarlayıcı panel, yangın dolabı/tüpü, duman damperi |

### 🔐 Alarm Sistemleri

Hırsız ihbar (intrusion) tarafı. Her türde **Bağlantı Tipi**
(kablolu / kablosuz / hibrit) ve **Frekans** (433 / 868 / 915 MHz, 2.4 GHz)
sorulur; kablosuz cihazlarda ayrıca pil tipi ve pil ömrü tutulur.

| Alt kategori | Türe özel alanlar |
|---|---|
| 🔐 Alarm Paneli | Kablolu/kablosuz zon sayısı, genişletme ile azami zon, **bölme (partition)**, kullanıcı kodu, haberleşme (PSTN / GSM / IP / Wi-Fi), mobil uygulama, PGM çıkışı, batarya ve yedekleme süresi, sertifika (EN 50131) |
| 🚶 Alarm Dedektörü | Algılama tipi (**PIR**, dual PIR+mikrodalga, manyetik kontak, cam kırılma, titreşim, perde tipi, dış mekan bariyer, su baskını), menzil, algılama açısı, **evcil hayvan bağışıklığı**, pil tipi/ömrü, zon, montaj, tamper, IP sınıfı |
| 🔢 Tuş Takımı / Kumanda | Cihaz tipi (LED/LCD/dokunmatik keypad, uzaktan kumanda, proximity okuyucu, panik butonu), buton sayısı, bölme desteği, pil, tamper |
| 📢 Alarm Sireni | İç/dış mekan siren, siren+flaşör, ses seviyesi (dB), besleme, yedek batarya, tamper, IP sınıfı |
| 🧩 Alarm Modülü | Modül tipi (zon genişletme, **kablosuz alıcı**, GSM/GPRS, IP, Wi-Fi, röle/çıkış, güç kaynağı, tekrarlayıcı), zon/kanal sayısı, menzil, besleme, uyumlu panel |

### 🚧 Geçiş Sistemleri

| Alt kategori | Türe özel alanlar |
|---|---|
| 🪪 Kart Okuyucu | Cihaz tipi (kart, kart+şifre, parmak izi, yüz tanıma, UHF uzun mesafe, turnike, plaka), **kart teknolojisi** (proximity 125 kHz, Mifare, DESFire, iCLASS, NFC, UHF, manyetik, barkod), haberleşme (Wiegand 26/34, RS485, **OSDP**, TCP/IP), kullanım (geçiş / PDKS / turnike / otopark), okuma mesafesi, kullanıcı kapasitesi, bağlı panel |
| 🖨️ Kart Yazıcı / Kodlayıcı | Tek/çift yüz, renkli-monokrom, doğrudan/retransfer, dpi, **kart kodlama** (manyetik şerit, Mifare/RFID, temaslı çip, UHF), bağlantı, hız, laminasyon, hazne, ribbon, baskı sayacı |
| 🚧 Bariyer | Kol tipi (düz / eklemli / çitli), kol uzunluğu, açılma süresi, motor tipi, besleme, **nasıl açılıyor** (kumanda / kart / plaka tanıma / kantar), güvenlik (fotosel, loop dedektör), giriş-çıkış yönü, manuel açma, LED kol |
| 🔧 Bariyer Parçası | Parça tipi (kol, motor, redüktör, denge yayı, kontrol kartı, **loop dedektör**, fotosel, kumanda, alıcı, LED, flanş), uyumlu model, ölçü, adet |
| 📷 Plaka Tanıma Kamerası | Çözünürlük, lens, okuma mesafesi, **okuyabildiği azami hız**, aydınlatma (IR / beyaz ışık), IR mesafesi, besleme (PoE), bağlı ünite, giriş-çıkış yönü, montaj, IP sınıfı |
| 🚗 Plaka Tanıma Ünitesi | Bileşen tipi (gömülü ünite / sunucu-yazılım / kontrol ünitesi), kanal sayısı, plaka formatı, **beyaz liste kapasitesi**, entegre olduğu sistem (bariyer / kantar / kartlı geçiş), bağlantı, lisans bitişi |

### ⚖️ Kantar Sistemi

| Alt kategori | Türe özel alanlar |
|---|---|
| ⚖️ Kantar / Tartım Platformu | Kantar tipi (araç-köprü, platform, bant, vinç, mobil), **kapasite (ton)**, platform ölçüsü, yük hücresi sayısı, bölüntü (d), yapı, kurulum şekli, son kalibrasyon, **damga/muayene bitişi** |
| 🏋️ Yük Hücresi (Loadcell) | Kapasite, hücre tipi (kolon / kesme kirişi / tek nokta / S / halka), malzeme, çıkış (mV/V), doğruluk sınıfı (C3…), kablo uzunluğu, bağlı kantar, **platformdaki konumu**, IP sınıfı |
| 🖥️ Kantar Terminali / İndikatör | Cihaz tipi (indikatör / terminal / tartım bilgisayarı / uzak gösterge), ekran, bağlanabilen yük hücresi, haberleşme (RS232/RS485/TCP-IP), fiş yazıcısı, tartım yazılımı, onay (OIML R76) |
| 🧰 Diğer Kantar Ekipmanı | Bağlantı kutusu (junction box), trafik lambası, uzak gösterge, yük hücresi kablosu, parafudr, kalibrasyon ağırlığı, yazılım |

Ekranın üstünde toplam ürün, ağ tarafında **toplam port** ve PoE besleyen
cihaz sayısı, yangın ve alarm tarafında ürün çeşidi ve lokasyon dağılımı;
listede her ürünün **görseli**, lokasyonu, proje kodu ve kullanım durumu
(boşta / kimde) görünür.

```bash
curl -H "Authorization: Bearer $T" "$API/ag/urunler?tur=switch&proje_kodu=U030"
curl -H "Authorization: Bearer $T" "$API/ag/urunler?aile=yangin"
curl -H "Authorization: Bearer $T" "$API/ag/ozet?aile=alarm"
curl -H "Authorization: Bearer $T" "$API/ag/urunler?tur=alarm_dedektor"
curl -H "Authorization: Bearer $T" "$API/ag/urunler?aile=gecis"
curl -H "Authorization: Bearer $T" "$API/ag/ozet?aile=kantar"
```

> Uç adresleri tarihsel olarak `/ag` ile başlar (bölüm önce yalnızca ağ
> ürünleri içindi); `aile` parametresi hangi ailenin sorgulandığını belirler.

Kategori adından tür otomatik çıkarılır; Excel'den gelmiş
"POE Switch 8 Port" gibi kayıtlar da bu ekranda listelenir. Yedek parçalar
ayıklanır: **"NVR Diski"** bir disktir, NVR değil — Türkçede tamlamanın başı
sonda olduğu için son kelimeye bakılır ("Switch Kablosu" parça, "Kablosuz
Erişim Noktası" cihaz).

Aileler aynı kelimeleri paylaştığı için eşleştirme sırası önemlidir:
**"Yangın Alarm Paneli"** yangın, **"Kablosuz Alarm Paneli"** alarm,
**"Kablosuz Erişim Noktası"** ağ ürünüdür. Adında "yangın" geçen hiçbir kayıt
alarm ailesine düşmez. Aynı şekilde **"Bariyer Kolu"** bariyerin kendisi değil
parçası, **"4G Modem"** router değil mobil internet cihazı, düz **"Yazıcı"**
ise geçiş sistemi değildir (kart yazıcı anahtarlarının hepsi "kart" içerir).
"Vinç Kantarı" da Vinn sanılmaz — kısa anahtarlar tam kelime aranır.

Hangi kategorilerin hangi aileye/türe düştüğünü görmek için:

```bash
./.venv/bin/python scripts/ag-kategori-kontrol.py
```

Eşleşmeyen bir kategoriyi dahil etmek için ya Tanımlar'dan yeniden
adlandırın ya da `app/ag.py` içindeki `_KATEGORI_IPUCU`'na anahtar kelime
ekleyin.

### Marka nerede tutulur?

Marka cihaz kaydında değil **modelde** durur:
`Cihaz → Model → Üretici`. Aynı model iki kez farklı markayla açılmasın diye
böyle; ama modelin markası boşsa cihaz detayında **Marka satırı hiç
görünmez**. Snipe-IT'ten üreticisiz gelen modellerde tipik durumdur.

```bash
./.venv/bin/python scripts/marka-kontrol.py            # rapor
./.venv/bin/python scripts/marka-kontrol.py --uygula   # addan çıkarıp doldur
```

Betik yalnızca adın **başında** marka geçiyorsa doldurur ("HP ProBook 450" →
HP); "N439" gibi ipucu vermeyen adlar elle düzeltilmek üzere listelenir.
Elle düzeltme yeri: **Tanımlar → Modeller** — listede Marka ve Cihaz Tipi
sütunları vardır, markasız kayıtlar "— eksik —" görünür ve satıra tıklayıp
seçebilirsiniz.

Excel'i yeniden içe aktarmak da düzeltir: içe aktarım mevcut modeldeki **boş**
marka/kategoriyi doldurur (dolu değeri ezmez — aynı model adı başka markada da
kullanılabilir).

### Snipe-IT görsellerini ve belgelerini aktarma

Snipe-IT dosyaları veritabanında tutmaz: adları kayıtlarda, içerikleri diskte
durur. Bu yüzden iki şey gerekir — **döküm** (hangi dosya kime ait) ve
**Snipe-IT klasörü** (dosyaların kendisi):

```bash
./.venv/bin/python scripts/snipeit-dosya-aktar.py dokum.sql /path/snipe-it
./.venv/bin/python scripts/snipeit-dosya-aktar.py dokum.sql /path/snipe-it --uygula
```

| Snipe-IT'te | Nereye gider |
|---|---|
| `assets.image` | cihaz eki (görsel) |
| `action_logs` → Asset | cihaz eki (belge) |
| `action_logs` → User | **kişi eki** (imzalı zimmet formu) |
| `models.image` | `--model-gorselleri` ile o modelin cihazlarına |
| aksesuar/bileşen ekleri | aktarılmaz, raporlanır |

| aksesuar/sarf/bileşen/lisans görsel ve ekleri | stok kaydı eki |

Dosya adları klasörün altında **ada göre** aranır, bu yüzden Snipe-IT sürümü
klasörleri nereye koymuş olursa olsun bulunur (`public/uploads/...` ya da
`storage/private_uploads/...`). Tekrar çalıştırılabilir: aynı dosya ikinci kez
eklenmez. Ad önekindeki `user-3-0mQ0RyRs-` gibi gürültü temizlenir, asıl ad
korunur.

Snipe-IT'te dosya adları çoğu zaman `tmp20241020161408.pdf` gibidir; addan tür
anlaşılmaz ve belgeler "Diğer" olarak gelir. Kişiye bağlı PDF'ler pratikte
imzalı zimmet formudur:

```bash
# aktarım sırasında
./.venv/bin/python scripts/snipeit-dosya-aktar.py dokum.sql /path --kisi-pdf-zimmet
# aktarılmış belgeleri sonradan düzeltmek için
./.venv/bin/python scripts/kisi-belge-turu.py            # rapor
./.venv/bin/python scripts/kisi-belge-turu.py --uygula   # yaz
```

`kisi-belge-turu.py` yalnızca **PDF** ve türü **Diğer** olanlara dokunur;
Excel/görsellere ve elle seçilmiş türlere karışmaz. Varsayılan olarak yalnızca
aktarımdan gelenleri işler, `--tumu` bu sınırı kaldırır.

### Snipe-IT dışa aktarımıyla karşılaştırma

Snipe-IT'in Export düğmesiyle aldığınız dosyayı mevcut veriyle karşılaştırıp
**yalnızca boş alanları** doldurur; dolu bir değeri asla ezmez, çakışanları
listeler. Lokasyon/durum/zimmet hiç yazılmaz (bunlar sistemde günlük değişir,
eski dosyadan yazmak yeni değişiklikleri geri alır) — yalnızca farklıysa
rapora düşer.

```bash
./.venv/bin/python scripts/snipeit-karsilastir.py disaaktarim.xls
./.venv/bin/python scripts/snipeit-karsilastir.py disaaktarim.xls --uygula
```

Snipe-IT'te de boş olan markalar için `--marka-tahmini`: aynı alım
partisindeki (etiket önekindeki, örn. `FRM-0002-34543-…`) kardeş cihazların
markasını kullanır. Varsayılan olarak en az **2 hemfikir kardeş** aranır —
gerçek veri üzerinde çapraz doğrulamada 34 denemede %100 isabet; `--en-az 1`
kapsamı büyütür ama isabet %96.6'ya iner.

Dosya üç biçimde olabilir: Snipe-IT'in ürettiği HTML görünümlü `.xls`, gerçek
`.xlsx` ya da tam veritabanı dökümü `.sql` (mysqldump). Döküm en zengini —
cihazların yanı sıra aksesuar/sarf/bileşen/lisans/personel sayılarını da
karşılaştırır ve kurulum bir tablo öneki (`stop_` gibi) kullanıyorsa onu
kendiliğinden bulur.

> Döküm dosyası **parola özetleri ve oturum anahtarları** içerir; işi bitince
> sunucudan silin, git deposuna koymayın.

### Transferler

**🔄 Transferler** düğmesi lokasyonu değişen cihazları gösterir — hangi
şantiyeden hangisine, ne zaman. Bilgi cihaz geçmişindeki lokasyon
değişikliğinden okunur; ayrıca bir kayıt tutulmaz.

### Listeden toplu ekleme

Elinizdeki tabloyu doğrudan içe aktarabilirsiniz (sekme ya da 2+ boşlukla
ayrılmış sütunlar):

```
Marka       Model / Parça No           Seri Numarası     Hız / Mesafe / Mod
HIKVISION   HK-SFP-1.25G-1310-DF-MM    30004735548       1.25G / 1310nm / Multi-Mode
HUAWEI      SFP-GE-LX-SM1310           HB19481072030     1.25G / 10km / Single-Mode
```

```bash
# Önce ne olacağını gör (hiçbir şey yazılmaz):
./.venv/bin/python scripts/ag-urun-aktar.py liste.txt --tur sfp --dry-run

# Uygula: ürünleri hedef şantiyeye koy, transferi geçmişe yaz
./.venv/bin/python scripts/ag-urun-aktar.py liste.txt --tur sfp \
    --lokasyon "ŞANTİYE U030-U031" --nereden "ŞANTİYE U025"
```

"Hız / Mesafe / Mod" sütunu ayrıştırılır: `1.25G / 1310nm / Multi-Mode` →
Hız `1.25G`, Dalga Boyu `1310nm`, Mod `Multi-Mode`. Seri no zaten kayıtlıysa
satır atlanır — script tekrar çalıştırılabilir.
Örnek dosya: `ornek-veri/ag-sfp-u025-u030.txt`

## Şantiyeler ve proje kodları

Her lokasyonun bir **proje kodu** (`proje_kodu`, örn. `U023`) olabilir.
Varlıklar bu koda göre filtrelenir:

```bash
curl -H "Authorization: Bearer $T" "$API/assets?proje_kodu=U023"
curl -H "Authorization: Bearer $T" "$API/assets/proje-kodlari"   # kod + cihaz sayısı
```

Excel'de "Bulunduğu Yer" genellikle tek bir genel değerdir ("ŞANTİYE");
şantiye ayrımı **"Kullanılan Birim"** sütununda durur. İçe aktarım bu ikisini
birleştirip her proje için ayrı lokasyon açar ve kodu ona yazar:

| Bulunduğu Yer | Kullanılan Birim | Oluşan lokasyon | Proje kodu |
|---|---|---|---|
| ŞANTİYE | U023 | `ŞANTİYE U023` | `U023` |
| ŞANTİYE | u026 | `ŞANTİYE U026` | `U026` |
| *(boş)* | U023 | `ŞANTİYE U023` *(mevcut şantiyeye katılır)* | `U023` |

Elle girilmiş bir proje kodu içe aktarımda **ezilmez**.

### Eski veriyi şantiyelere ayırma

Bu ayrım eklenmeden önce aktarılmış kayıtlar tek bir lokasyonda toplanmıştı.
Onları dağıtmak için (tekrar çalıştırılabilir, taşınacak cihaz kalmadığında
hiçbir şeyi değiştirmez):

```bash
./.venv/bin/python scripts/santiye-ayir.py --dry-run   # önce ne olacağını gör
./.venv/bin/python scripts/santiye-ayir.py             # uygula
```

Proje kodu olmayan cihazlara dokunulmaz. Yalnızca belirli bir lokasyonu
ayırmak için `--kaynak "ŞANTİYE"` kullan.

## Arama (yazdıkça listeleme)

Üst çubuktaki arama kutusu, yazmaya başlar başlamaz cihazları, personeli ve
şantiyeleri birlikte listeler.

| Arananlar | Alanlar |
|---|---|
| Cihaz | etiket (cihaz no), seri no, demirbaş no, ad, IP, barkod, IMEI, hostname |
| Personel | ad soyad, sicil no, departman, e-posta |
| Lokasyon / proje | lokasyon adı, **proje kodu** (örn. `U023`) |

Bir cihaz; kendi alanları, **zimmetli olduğu kişinin adı** ya da **bulunduğu
lokasyonun adı/proje kodu** eşleştiğinde bulunur. Yani `ertekin` yazınca o
kişideki cihazlar, `U026` yazınca o şantiyedeki cihazlar gelir.

```bash
curl -H "Authorization: Bearer $T" "$API/assets/ara?q=ertekin"
curl -H "Authorization: Bearer $T" "$API/assets?q=U026"   # şantiyedeki cihazlar
```

Sonuç listesinde bir şantiyeye tıklamak varlık listesini o projeye filtreler
(proje kodu yoksa o lokasyona).

Eşleştirme Türkçe duyarlıdır: `ertekin` → **ERTEKİN**, `atesoglu` → **Ateşoğlu**,
`monitor` → **Monitör**, `santiye` → **ŞANTİYE** bulur.

> Bu karşılaştırma bilerek veritabanında değil Python'da yapılır. SQL'in
> `LOWER()`/`ILIKE`'ı Türkçe'de yanılır: PostgreSQL `lower('ERTEKİN')` sonucu
> `erteki̇n` (i + birleşen nokta) verir, SQLite ise yalnızca ASCII harfleri
> çevirir. İkisinde de `ertekin` araması boş dönerdi. Ayrıntı: `app/arama.py`.

## Teknik özellikler

Cihaz detayında **+ Özellik ekle** ile istediğin grubu ve alanı açabilirsin;
şemayı değiştirmen gerekmez (`Asset.custom`, JSON). Bilinen grup/alan adları
öneri olarak sunulur.

```bash
curl -X PUT -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"grup":"Bellek","ad":"Ram Kapasitesi (mB)","deger":"32 GB"}' \
  "$API/assets/12/ozellik"

curl -X DELETE -H "Authorization: Bearer $T" \
  "$API/assets/12/ozellik?grup=Bellek&ad=Ram%20Kapasitesi%20(mB)"
```

## Görsel ve belge yükleme (cihaz ve kişi)

Her **cihaza** fotoğraf, imzalı zimmet formu, fatura ve diğer belgeler
eklenebilir. Ayrıca her **kişiye** de belge eklenebilir: imzalı zimmet formu
tek bir cihaza değil kişiye aittir — bir form o kişinin birden çok cihazını
listeler. Personel kartındaki **Belgeler** bölümü bunun içindir. Dosyalar veritabanında değil diskte (`UPLOAD_DIR`, varsayılan
`yuklemeler/`) tutulur; veritabanında **yalnızca göreli yol** saklanır.

Klasörler türe ve aya göre ayrılır:

```
yuklemeler/
  gorseller/2026/08/12-a1b2c3d4e5f6a7b8.png
  belgeler/2026/08/12-9f8e7d6c5b4a3210.pdf      ← imzalı zimmet formu, diğer belgeler
  faturalar/2026/08/...
```

> Tek klasörde on binlerce dosya biriktiğinde listeleme ve yedekleme yavaşlar;
> ay bazlı bölme bunu önler. Yol **göreli** tutulur — sunucu ya da klasör
> değişince kayıtlar geçersiz olmasın diye.

```bash
# cihaza
curl -H "Authorization: Bearer $T" -F "file=@imzali.pdf" -F "tur=zimmet_formu" \
  "$API/assets/12/dosyalar"
# kişiye
curl -H "Authorization: Bearer $T" -F "file=@imzali.pdf" -F "tur=zimmet_formu" \
  "$API/users/42/dosyalar"
```

Kişi ekleri ayrı tabloda (`user_files`) ama aynı klasörlerde durur; dosya adı
`k` ile başlar (`belgeler/2026/08/k42-…pdf`) — böylece diskte hangisinin kime
ait olduğu bellidir. İndirme/silme uçları `\/kisi-dosyalari\/{id}`.

| Tür | Anlamı |
|---|---|
| `gorsel` | Cihaz fotoğrafı (yalnızca resim dosyaları) |
| `zimmet_formu` | İmzalı / taranmış zimmet formu |
| `fatura` | Fatura veya irsaliye |
| `diger` | Diğer belgeler |

Yürütülebilir dosyalar (`.exe`, `.sh`, `.php`…) reddedilir; boyut sınırı
`MAX_UPLOAD_MB` (varsayılan 20 MB). Diskteki adı sunucu üretir, bu yüzden
dosya adındaki `../` gibi ifadeler zarar veremez.

> **Yedeklemede `yuklemeler/` klasörünü de al** — veritabanı yedeği bu
> dosyaları içermez. Arayüzdeki yedekleme bunu kendiliğinden yapar
> (bkz. *Yedekleme*).

## Yedekleme

**Ayarlar → Yedekleme** (yalnızca yönetici):

- **Şimdi yedek al** — veritabanının tam dökümü + yüklenen dosyaların arşivi,
  iki ayrı dosya olarak
- Mevcut yedekleri listeleme, **indirme** ve silme
- `BACKUP_KEEP_DAYS` (varsayılan 30) günden eski yedekler otomatik silinir

```bash
curl -H "Authorization: Bearer $T" "$API/yedek"          # liste
curl -X POST -H "Authorization: Bearer $T" "$API/yedek"  # şimdi al
```

| Veritabanı | Üretilen dosya | Kullanılan araç |
|---|---|---|
| PostgreSQL | `envanter_<tarih>.dump` | `pg_dump -Fc` |
| MySQL / MariaDB | `envanter_<tarih>.sql` | `mysqldump --single-transaction` |
| SQLite | `envanter_<tarih>.sqlite` | `sqlite3 .backup` (tutarlı kopya) |

Yüklenen dosyalar ayrıca `dosyalar_<tarih>.tar.gz` olarak arşivlenir.

> Parola hiçbir zaman komut satırına yazılmaz (`ps` çıktısı tüm kullanıcılara
> açıktır): PostgreSQL için `PGPASSWORD`, MySQL için geçici `--defaults-extra-file`
> kullanılır. Dış araçların hata çıktısı da maskelenir — bağlantı dizesi
> içerebilir.

**Her gece otomatik yedek** için sunucuda bir kez:

```bash
sudo cp deploy/yedek.sh /usr/local/bin/envanter-yedek
sudo chmod +x /usr/local/bin/envanter-yedek
echo "0 3 * * * /usr/local/bin/envanter-yedek" | sudo crontab -
```

> ⚠️ Yedekler sunucunun kendi diskinde durur. Disk arızasına karşı düzenli
> olarak başka bir yere (harici disk, bulut) kopyalayın.

## Zimmet verme

Kimlik numarası hiçbir yerde sorulmaz. İki yönde de aynı pencere açılır:

| Nereden | Ne seçilir |
|---|---|
| **Varlıklar** → cihazın *Zimmetle* düğmesi, cihaz detayı | **kişi** aranır |
| **Personel** → satırın *+ Zimmetle* düğmesi, kişi detayı → *+ Zimmet ekle* | **cihaz** aranır |

Pencere açılır açılmaz seçilebilecek kayıtlar listelenir (kişi tarafında en çok
cihaz taşıyanlar, cihaz tarafında boştaki cihazlar) ve yazdıkça süzülür.
Arama Türkçe duyarlıdır (`atesoglu` → **Ateşoğlu**, `santiye` → **ŞANTİYE**).

- Kişi listesinde her satırda **kaç cihaz taşıdığı**,
- Cihaz listesinde **tür, bulunduğu şantiye ve seri no** görünür.

```bash
curl -H "Authorization: Bearer $T" "$API/users/ara?q=ertekin"       # kişi ara
curl -H "Authorization: Bearer $T" "$API/assets?assigned=false&q=hilook"  # boştaki cihaz
```

Kişi seçme penceresinde ayrıca:

- **+ Yeni personel** — kayıtlı olmayan kişiyi oradan ekleyip aynı anda
  zimmetleyebilirsin (arama kutusuna yazdığın ad forma hazır gelir).
- **Lokasyona zimmetle** — cihaz kişiye değil bir yere (depo, şantiye)
  verilecekse.

## Demirbaş zimmet formu (PDF)

Personele cihaz teslim ederken imzalatılacak form, kurumun kullandığı
**DEMİRBAŞ ZİMMET FORMU** düzeninde üretilir — Türkçe karakterler gömülü fontla
doğru basılır.

```bash
# Tek cihaz için zimmet formu
GET /documents/zimmet/asset/{asset_id}.pdf
# Personele zimmetli tüm cihazlar (her cihaz ayrı sayfa, ayrı imza)
GET /documents/zimmet/user/{user_id}.pdf
# İade formu + not
GET /documents/zimmet/user/{user_id}.pdf?doc_type=iade&note=Ekran%20çizik
```

Formun bölümleri:

| Bölüm | İçerik |
|---|---|
| Künye | Nesne No, Nesne Açıklama, Nesne Türü / Kategori |
| Özellikler | MARKA, MODEL, ŞASİ NO / SERİ NO, KULLANIM DURUMU, ZİMMETLENEN PERSONEL, LOKASYON, KİRALANAN FİRMA, KAPASİTE, İŞLEMCİ, RAM, EKRAN KARTI, HDD, ANAKART, EKRAN BOYUTU, İŞLETİM SİSTEMİ, CİHAZ KODU |
| Notlar | Elle doldurulabilir boş alan (ya da `note` parametresi) |
| Kullanıcı Bilgileri | Ad Soyad, Sicil No, Departman, Mail Adresi |
| Taahhüt | `ORG_NAME` ile başlayan teslim alma metni |
| İmza | TESLİM EDEN / TESLİM ALAN — Ad Soyad, İmza, Tarih |

Teknik özellikler cihazın `custom` alanından okunur. Çok uzun değerleri
(ekran kartı, anakart) olan cihazlarda form otomatik küçültülerek **tek
sayfada** tutulur; veri kırpılmaz.

Kurum adını `.env` içinde ayarla:

```ini
ORG_NAME=YILDIZLAR GRUP
```

Arayüzde cihazın 📄 butonundan açılır. İmzalandıktan sonra taranan formu
cihaza geri yükleyebilirsin (bkz. *Cihaz görseli ve imzalı form yükleme*).

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
| `GET` | `/assets/sayi` | Filtrelere uyan toplam sayı (sayfalamadan bağımsız) |
| `GET` | `/assets/proje-kodlari` | Proje kodları + cihaz sayıları |
| `GET/POST` | `/ag/urunler` | Ağ ürünlerini listele / ekle |
| `GET` | `/ag/aileler` | Ürün aileleri (ağ / yangın) |
| `GET` | `/ag/sablon` | Türler ve teknik alanları (`?aile=`) |
| `GET` | `/ag/ozet` | Tür/lokasyon dağılımı, toplam port, PoE |
| `GET` | `/ag/transferler` | Lokasyonu değişen cihazlar |
| `PUT` | `/ag/urunler/{id}/ozellikler` | Ağ özelliklerini topluca yaz |
| `GET` | `/assets/ara` | Yazdıkça arama (cihaz + personel + lokasyon, Türkçe duyarlı) |
| `GET` | `/users/ara` | Zimmet için personel arama (cihaz sayılarıyla) |
| `GET/PUT` | `/auth/me` | Kendi bilgilerini gör / güncelle |
| `POST` | `/auth/parola` | Kendi parolasını değiştir |
| `GET` | `/users/hesaplar` | Giriş yetkisi olan kullanıcılar (admin) |
| `PUT` | `/users/{id}/hesap` | Kullanıcı adı / yetki / parola / durum (admin) |
| `PUT/DELETE` | `/assets/{id}/ozellik` | Teknik özellik ekle-güncelle / sil |
| `GET` | `/assets/ozellik-sablonu` | Bilinen özellik grupları ve alan adları |
| `GET/POST` | `/assets/{id}/dosyalar` | Cihaz dosyalarını listele / yükle |
| `GET/DELETE` | `/dosyalar/{id}` | Dosyayı indir/göster / sil |
| `GET/POST` | `/yedek` | Yedekleri listele / şimdi yedek al (admin) |
| `GET/DELETE` | `/yedek/{ad}` | Yedeği indir / sil (admin) |
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
  santiye.py         # Cihazları proje koduna göre şantiyelere dağıtma
  yedek.py           # Veritabanı dökümü + dosya arşivi
  arama.py           # Türkçe duyarlı yazdıkça arama (cihaz/personel/lokasyon)
  ag.py              # Ağ ürünleri: tür şablonları, özet, transferler
  pdf/               # Zimmet formu ve barkod/QR etiket üretimi
  ai/search.py       # Doğal dil → yapısal filtre (Claude)
  excel/             # Excel içe/dışa aktarım (sütun şeması + aktarım)
  routers/           # API uçları
  static/index.html  # Web arayüzü (sol menü + üst bar)
  static/login.html  # Giriş sayfası (/login)
alembic/             # Veritabanı göçleri
scripts/
  import_snipeit.py  # Snipe-IT'ten veri taşıma
  create_admin.py    # Admin kullanıcı oluştur/yükselt
  santiye-ayir.py    # Eski veriyi şantiyelere ayır (tekrar çalıştırılabilir)
  kurulum-kontrol.sh # Güncelleme sonrası sağlık kontrolü (hiçbir şey değiştirmez)
  ag-urun-aktar.py   # Ağ ürünlerini metin tablosundan içe aktar
  ag-kategori-kontrol.py # Hangi kategoriler sistem ürünü sayılıyor
  marka-kontrol.py   # Markası boş modelleri bul/doldur
  snipeit-karsilastir.py # Snipe-IT dışa aktarımı/dökümüyle karşılaştır, boşları doldur
  snipeit-dosya-aktar.py # Snipe-IT görsel ve belgelerini aktar
  kisi-belge-turu.py # Kişi belgelerini imzalı zimmet formu olarak işaretle
tests/               # pytest (API + içe aktarım + kimlik doğrulama)
```
