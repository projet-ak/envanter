/* Envanter arayüz mantığı — index.html'den ayrıldı.
   KLASİK betik olarak yüklenir (module DEĞİL): onclick öznitelikleri
   global işlevlere bağlı, module kapsamı onları gizlerdi. */
let token = localStorage.getItem('token') || '';
let me = JSON.parse(localStorage.getItem('me') || 'null');
let statusMap = {};
let activeTab = 'assets';
const canWrite = () => me && (me.role === 'admin' || me.role === 'editor');

// Adet bazlı türlerin yapılandırması (veri-odaklı arayüz)
const STOCK = {
  accessories: { label: 'Aksesuarlar', endpoint: '/accessories',
    kayitTuru: 'accessory',
    ikon: '🎧', alt: 'Klavye, mouse, kulaklık gibi adet bazlı malzemeler',
    cols: [['name','Ad'],['model_number','Model No'],['qty','Adet'],['min_qty','Min']],
    add: [['name','Ad','text'],['qty','Adet','number'],['min_qty','Min','number']],
    lowStock: true },
  consumables: { label: 'Sarf Malzeme', endpoint: '/consumables',
    kayitTuru: 'consumable',
    ikon: '📦', alt: 'Toner, kablo, pil gibi tüketilen malzemeler',
    cols: [['name','Ad'],['qty','Adet'],['min_qty','Min']],
    add: [['name','Ad','text'],['qty','Adet','number'],['min_qty','Min','number']],
    lowStock: true },
  components: { label: 'Bileşenler', endpoint: '/components',
    kayitTuru: 'component',
    ikon: '🔩', alt: 'RAM, disk, ekran kartı gibi cihaz parçaları',
    cols: [['name','Ad'],['serial','Seri'],['qty','Adet'],['min_qty','Min']],
    add: [['name','Ad','text'],['serial','Seri','text'],['qty','Adet','number'],['min_qty','Min','number']],
    lowStock: true },
  licenses: { label: 'Lisanslar', endpoint: '/licenses',
    kayitTuru: 'license',
    ikon: '🔑', alt: 'Yazılım lisansları ve koltuk sayıları',
    cols: [['name','Ad'],['seats','Koltuk'],['license_key','Anahtar'],['expiration_date','Bitiş']],
    add: [['name','Ad','text'],['seats','Koltuk','number'],['license_key','Anahtar','text']],
    lowStock: false },
};

// Referans (tanım) tabloları — Lokasyon, Kategori, Üretici vb.
const TANIMLAR = {
  locations:     { label: 'Lokasyonlar',  endpoint: '/locations',
    cols: [['name','Ad'],['proje_kodu','Proje Kodu'],['city','Şehir'],['address','Adres']],
    add: [['name','Ad','text'],['proje_kodu','Proje Kodu','text'],
          ['city','Şehir','text'],['address','Adres','text']] },
  categories:    { label: 'Kategoriler',  endpoint: '/categories',
    cols: [['name','Ad'],['type','Tür']],
    add: [['name','Ad','text']] },
  manufacturers: { label: 'Üreticiler',   endpoint: '/manufacturers',
    cols: [['name','Ad'],['support_phone','Destek Tel'],['support_email','Destek E-posta']],
    add: [['name','Ad','text'],['support_phone','Destek Tel','text']] },
  // Marka cihaz kaydında değil MODELDE durur: burada boş kalırsa cihaz
  // detayında da boş görünür, bu yüzden listede ve formda yer alır.
  models:        { label: 'Modeller',     endpoint: '/models',
    cols: [['name','Ad'],['model_number','Model No'],
           ['manufacturer_id','Marka'],['category_id','Cihaz Tipi']],
    add: [['name','Ad','text'],['model_number','Model No','text']],
    sec: [['manufacturer_id','Marka','/manufacturers'],
          ['category_id','Cihaz Tipi','/categories']] },
  suppliers:     { label: 'Tedarikçiler', endpoint: '/suppliers',
    cols: [['name','Ad'],['phone','Telefon'],['email','E-posta']],
    add: [['name','Ad','text'],['phone','Telefon','text'],['email','E-posta','text']] },
  companies:     { label: 'Şirketler',    endpoint: '/companies',
    cols: [['name','Ad']], add: [['name','Ad','text']] },
  'status-labels': { label: 'Durumlar',   endpoint: '/status-labels',
    cols: [['name','Ad'],['type','Tür']], add: [['name','Ad','text']] },
};
let aktifTanim = 'locations';

// Uygulama alt klasörde de yayınlanabilir (örn. https://site.com/envanter/).
// Arayüz /ui/ altında sunulduğu için, taban yolu adresten türetiyoruz:
//   /ui/           -> ''           (kök dizin)
//   /envanter/ui/  -> '/envanter'  (alt klasör)
const BASE = window.location.pathname.replace(/\/ui\/?$/, '');
const url = (path) => BASE + path;

// ---------- Giriş / oturum ----------
// Giriş ayrı bir sayfada (/login). Oturum yoksa oraya gidilir; kullanıcı
// giriş yapınca ?redirect ile bulunduğu sayfaya geri döner.
function girisSayfasi() {
  const nereye = location.pathname + location.search;
  location.replace(`${BASE || ''}/login?redirect=${encodeURIComponent(nereye)}`);
}

async function api(path, opt = {}) {
  opt.headers = Object.assign({ 'Authorization': `Bearer ${token}` }, opt.headers || {});
  const r = await fetch(url(path), opt);
  if (r.status === 401) { logout(); throw { detail: 'Oturum süresi doldu' }; }
  if (!r.ok) throw await r.json().catch(() => ({ detail: 'Hata' }));
  // Başarılı her YAZMA isteği bayrağı kaldırır; pencere kapanınca arkadaki
  // ekran kendiliğinden tazelenir (bkz. modalKapat) — kullanıcı sekme
  // değiştirmeden güncel veriyi görür.
  if ((opt.method || 'GET').toUpperCase() !== 'GET') verilerDegisti = true;
  return r.status === 204 ? null : r.json();
}

// Pencere içindeki kayıtlardan sonra arkadaki liste bayat kalmasın
let verilerDegisti = false;

function aktifVeriyiYenile() {
  try {
    if (activeTab === 'assets') loadAssets();
    else if (activeTab === 'personel') loadPersonel();
    else if (activeTab === 'tanimlar') loadTanim();
    else if (STOCK[activeTab]) loadStock(activeTab);
    else if (AILE_BILGI[activeTab]) renderAgView(activeTab);
    else if (activeTab === 'dashboard') renderDashboard();
  } catch { /* ekran henüz kurulmadıysa sessiz geç */ }
}

function logout() {
  canliDurdur();
  token = ''; me = null;
  localStorage.removeItem('token'); localStorage.removeItem('me');
  girisSayfasi();
}

// ---------- Tema ----------
function temaUygula(tema) {
  document.documentElement.dataset.tema = tema;
  const d = document.getElementById('temaDug');
  if (d) d.textContent = tema === 'koyu' ? '☀️' : '🌙';
}
function temaDegistir() {
  const yeni = document.documentElement.dataset.tema === 'koyu' ? 'acik' : 'koyu';
  localStorage.setItem('tema', yeni);
  temaUygula(yeni);
}

// ---------- Oturum sayacı ----------
// Jetonun bitiş anı (exp) içinde yazılıdır; kalan süreyi oradan gösteriyoruz.
let sayacZaman = null;
function jetonBitisi() {
  try {
    const govde = JSON.parse(atob(token.split('.')[1]));
    return govde.exp ? govde.exp * 1000 : null;
  } catch { return null; }
}
function sayacBaslat() {
  clearInterval(sayacZaman);
  const bitis = jetonBitisi();
  const el = document.getElementById('oturumSayac');
  if (!bitis || !el) { el?.classList.add('hidden'); return; }
  const iki = (n) => String(n).padStart(2, '0');
  const tik = () => {
    const kalan = Math.max(0, Math.floor((bitis - Date.now()) / 1000));
    const sa = Math.floor(kalan / 3600);
    const dk = Math.floor((kalan % 3600) / 60);
    // Oturum 8 saat olabiliyor; saat varken sa:dd:ss, yokken dd:ss göster
    el.textContent = sa ? `🕐 ${sa}:${iki(dk)}:${iki(kalan % 60)}`
                        : `🕐 ${iki(dk)}:${iki(kalan % 60)}`;
    el.classList.toggle('azaliyor', kalan < 300);
    if (kalan === 0) { clearInterval(sayacZaman); logout(); }
  };
  tik();
  sayacZaman = setInterval(tik, 1000);
}

// Kurum logosu: app/static/logo.png varsa emoji yerine o gösterilir.
// /logo ucu dosya yokken 204 döner; 404 yoklaması gibi konsolu kirletmez.
(function logoDene() {
  const kutu = document.getElementById('markaLogo');
  if (!kutu) return;
  fetch(url('/logo')).then(r => r.status === 200 ? r.blob() : null).then(b => {
    if (!b) return;
    const img = new Image();
    img.alt = 'Logo';
    img.src = URL.createObjectURL(b);
    kutu.textContent = '';
    kutu.classList.add('genis');       // yatay logo dar karede ezilmesin
    kutu.closest('.yan-bas')?.classList.add('logolu');
    kutu.appendChild(img);
  }).catch(() => {});
})();

// ---------- Menü ----------
// [anahtar, etiket, ikon, yalnızca-yazma-yetkisi?]
const MENU_ANA = [
  ['dashboard', 'Kontrol Paneli', '📊'],
  ['assets', 'Varlıklar', '💻'],
  ['ag', 'Ağ Ürünleri', '🌐'],
  ['yangin', 'Yangın Sistemleri', '🔥'],
  ['alarm', 'Alarm Sistemleri', '🔐'],
  ['gecis', 'Geçiş Sistemleri', '🚧'],
  ['kantar', 'Kantar Sistemi', '⚖️'],
  ['personel', 'Personel', '👥'],
  ['accessories', 'Aksesuarlar', '🎧'],
  ['consumables', 'Sarf Malzeme', '📦'],
  ['components', 'Bileşenler', '🔩'],
  ['licenses', 'Lisanslar', '🔑'],
];
const MENU_YONETIM = [
  ['raporlar', 'Raporlar', '📈'],
  ['tanimlar', 'Tanımlar', '🗂️'],
  ['excel', 'Excel Aktarım', '📄'],
  ['invoice', 'Fatura Oku', '🧾', true],
  ['ayarlar', 'Ayarlar', '⚙️'],
];

function menuKur() {
  const dugme = ([k, label, ikon]) =>
    `<button data-tab="${k}" onclick="selectTab('${k}')">
       <span class="ikon">${ikon}</span>${label}</button>`;
  const yonetim = MENU_YONETIM.filter(([, , , yazar]) => !yazar || canWrite());
  document.getElementById('gez').innerHTML =
    MENU_ANA.map(dugme).join('') +
    '<div class="yan-baslik">Yönetim</div>' +
    yonetim.map(dugme).join('');
}

function menuAcKapa() {
  document.getElementById('yanmenu').classList.toggle('acik');
}

function selectTab(tab) {
  activeTab = tab;
  document.querySelectorAll('#gez button').forEach(b =>
    b.classList.toggle('aktif', b.dataset.tab === tab));
  document.getElementById('yanmenu').classList.remove('acik');
  if (tab !== 'dashboard') canliDurdur();
  if (tab === 'dashboard') { renderDashboard(); canliBaslat(); }
  else if (tab === 'assets') renderAssetsView();
  else if (tab === 'invoice') renderInvoiceView();
  else if (tab === 'personel') renderPersonelView();
  else if (tab === 'tanimlar') renderTanimlarView();
  else if (tab === 'excel') renderExcelView();
  else if (tab === 'raporlar') renderRaporlarView();
  else if (AILE_BILGI[tab]) renderAgView(tab);
  else if (tab === 'ayarlar') renderAyarlarView();
  else renderStockView(tab);
}

// Sayfa başlığı — her ekranın üstünde aynı düzende
function sayfaBasligi(ikon, baslik, altMetin = '') {
  return `<div class="sayfa-bas">
    <h1>${ikon} ${kacir(baslik)}</h1>
    ${altMetin ? `<div class="alt">${altMetin}</div>` : ''}
  </div>`;
}

function bashharfler(ad) {
  return (ad || '?').trim().split(/\s+/).slice(0, 2)
    .map(p => p[0] || '').join('').toLocaleUpperCase('tr');
}

const ROL_ADI = { admin: 'Yönetici', editor: 'Düzenleyici', viewer: 'Görüntüleyici' };

async function showApp() {
  const ad = [me.first_name, me.last_name].filter(Boolean).join(' ') || me.username;
  for (const [id, deger] of [['yanAd', ad], ['ustAd', ad],
                             ['yanRol', ROL_ADI[me.role] || me.role],
                             ['ustRol', ROL_ADI[me.role] || me.role],
                             ['yanAvatar', bashharfler(ad)],
                             ['ustAvatar', bashharfler(ad)]]) {
    document.getElementById(id).textContent = deger;
  }
  menuKur();
  sayacBaslat();
  const s = await api('/status-labels');
  statusMap = Object.fromEntries(s.map(x => [x.id, x.name]));
  selectTab('dashboard');
}

// ---------- Personel ----------
async function renderPersonelView() {
  document.getElementById('view').innerHTML =
    sayfaBasligi('👥', 'Personel', 'Çalışanlar ve zimmetindeki cihazlar') + `
    <div class="panel">
      <div class="row" style="align-items:center">
        <h2 style="margin:0; flex:1">Personel (<span id="pCount">0</span>)</h2>
        ${canWrite() ? `<button class="primary" onclick="personelEkleAc()">
          + Personel ekle</button>` : ''}
      </div>
      <div class="row" style="margin-top:12px">
        <input id="pAra" class="grow" placeholder="Ada, sicile veya departmana göre ara…"
               oninput="loadPersonel()" />
      </div>
      <table style="margin-top:8px"><thead><tr><th>Ad Soyad</th>
        <th class="gizle-mobil">Sicil</th><th>Departman</th>
        <th class="gizle-mobil">Şube</th><th class="gizle-mobil">E-posta</th>
        <th>Zimmet</th><th></th></tr></thead>
        <tbody id="pRows"></tbody></table>
    </div>`;
  loadPersonel();
}

// Yeni personel: popup pencerede aç
async function personelEkleAc() {
  const lokasyonlar = await api('/locations?limit=500');
  const alanlarListe = [
    ['first_name','Ad *','text'],['last_name','Soyad','text'],
    ['employee_num','Sicil No','text'],['department','Departman','text'],
    ['job_title','Unvan','text'],['sube','Şube','text'],
    ['email','E-posta','text'],['telefon','Telefon','text'],
    ['tckn','TCKN','text'],['ise_giris','İşe Giriş','date'],
  ];
  modalAc('👤 Yeni personel', `
    <div class="alan-grid">
      ${alanlarListe.map(([k, l, t]) => `<div>
        <div class="stat-l" style="margin-bottom:3px">${l}</div>
        <input id="np_${k}" type="${t}" style="width:100%"
          ${k === 'first_name' ? 'autofocus' : ''}
          onkeydown="if(event.key==='Enter')personelKaydet()" /></div>`).join('')}
      <div><div class="stat-l" style="margin-bottom:3px">Lokasyon</div>
        <select id="npl_location_id" style="width:100%">
          ${secenekler(lokasyonlar, null)}</select></div>
    </div>
    <div class="row" style="margin-top:16px">
      <button class="primary" onclick="personelKaydet()">Kaydet ve zimmet ver</button>
      <button class="ghost" onclick="modalKapat()">Vazgeç</button>
    </div>
    <div class="note">Kaydettikten sonra doğrudan bu kişinin sayfası açılır;
      cihaz zimmetlemeyi oradan yapabilirsin.</div>
    <div id="npInfo" class="note"></div>`);
  setTimeout(() => document.getElementById('np_first_name')?.focus(), 100);
}

async function personelKaydet() {
  const govde = {};
  for (const el of document.querySelectorAll('[id^="np_"]')) {
    const v = el.value.trim();
    if (v) govde[el.id.slice(3)] = v;
  }
  const lok = document.getElementById('npl_location_id');
  if (lok?.value) govde.location_id = Number(lok.value);
  const bilgi = document.getElementById('npInfo');
  if (!govde.first_name) {
    bilgi.innerHTML = '<span style="color:var(--err)">Ad zorunlu.</span>'; return;
  }
  try {
    const kisi = await api('/users', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(govde) });
    if (activeTab === 'personel') loadPersonel();
    // Listede aramaya gerek kalmasın: doğrudan yeni kişinin sayfasını aç
    kisiDetay(kisi.id);
  } catch (e) {
    bilgi.innerHTML = `<span style="color:var(--err)">⚠ ${e.detail || 'Eklenemedi'}</span>`;
  }
}

// ---------- Zimmet atama (kişi tarafı: kişi belli, cihaz seçilir) ----------
// Cihaz tarafındaki pencerenin ikizi; orada kişi aranır, burada cihaz.
let zimmetHedefKisi = null;
let zimmetHedefAd = '';
let zimmetSonrasi = null;

function zimmetPaneliAc(kisiId, adKodlu = '', sonra = null) {
  zimmetHedefKisi = kisiId;
  zimmetHedefAd = decodeURIComponent(adKodlu);
  zimmetSonrasi = sonra || (() => kisiDetay(kisiId));
  modalAc(`Zimmetle${zimmetHedefAd ? ' — ' + kacir(zimmetHedefAd) : ''}`, `
    <div class="row">
      <input id="zAra" class="grow" autocomplete="off"
             placeholder="Cihaz ara: etiket, seri no, demirbaş, tür, şantiye…"
             oninput="zimmetAra()" />
    </div>
    <div id="zSonuc" class="note">Yükleniyor…</div>`);
  setTimeout(() => document.getElementById('zAra')?.focus(), 60);
  zimmetAraCalistir();
  // Tür/lokasyon adları yalnızca Varlıklar sekmesi açıldığında yükleniyor;
  // Personel sekmesinden gelindiyse önce onları getir, sonra listeyi tazele.
  if (!Object.keys(refLokasyon).length) {
    filtreSecenekleriDoldur().then(zimmetAraCalistir).catch(() => {});
  }
}

let zAraZaman = null;
function zimmetAra() {
  clearTimeout(zAraZaman);
  zAraZaman = setTimeout(zimmetAraCalistir, 180);
}

async function zimmetAraCalistir() {
  const kutu = document.getElementById('zSonuc');
  if (!kutu) return;
  const q = document.getElementById('zAra')?.value.trim() || '';
  const p = new URLSearchParams({ assigned: 'false', limit: '25' });
  if (q) p.set('q', q);
  let liste;
  try { liste = await api('/assets?' + p.toString()); }
  catch { kutu.textContent = 'Cihaz listesi alınamadı.'; return; }

  if (!liste.length) {
    kutu.innerHTML = `<div class="muted">${q
      ? 'Eşleşen boştaki cihaz yok.' : 'Boştaki cihaz yok.'}</div>`;
    return;
  }
  kutu.innerHTML = `<div class="muted" style="margin-bottom:6px">
      ${q ? 'Boştaki eşleşen cihazlar' : 'Boştaki cihazlar'} — seçmek için tıkla</div>
    <table><tbody>${liste.map(a => {
      const mdl = refModelKat[a.model_id];
      const tur = mdl ? refKategori[mdl.category_id] : null;
      return `<tr class="tikla" onclick="zimmetVer(${a.id})">
        <td><b>💻 ${kacir(a.asset_tag)}</b></td>
        <td>${esc(a.name)}</td>
        <td class="muted">${esc(tur)}</td>
        <td class="muted">${esc(refLokasyon[a.location_id])}</td>
        <td class="muted">${esc(a.serial)}</td>
        <td><button class="primary">Seç</button></td></tr>`;
    }).join('')}</tbody></table>`;
}

async function zimmetVer(assetId) {
  try {
    await api(`/assets/${assetId}/checkout`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assigned_type: 'user', assigned_id: zimmetHedefKisi }) });
    modalKapat();
    zimmetSonrasi?.();
  } catch (e) { alert('⚠ ' + (e.detail || 'Zimmetlenemedi')); }
}

async function zimmetGeriAl(assetId, kisiId) {
  if (!confirm('Bu cihaz iade alınsın mı? (zimmet kalkacak)')) return;
  try {
    await api(`/assets/${assetId}/checkin`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: '{}' });
    kisiDetay(kisiId);
  } catch (e) { alert('⚠ ' + (e.detail || 'İade alınamadı')); }
}

async function loadPersonel() {
  const q = (document.getElementById('pAra')?.value || '').trim().toLocaleLowerCase('tr');
  const [kisiler, zimmetler] = await Promise.all([
    api('/users?limit=500'), api('/reports/personel-zimmet'),
  ]);
  const sayac = Object.fromEntries(zimmetler.map(z => [z.user_id, z.cihaz_sayisi]));
  const liste = kisiler.filter(k => !q ||
    [k.first_name, k.last_name, k.employee_num, k.department, k.sube, k.email]
      .filter(Boolean).join(' ').toLocaleLowerCase('tr').includes(q));
  document.getElementById('pCount').textContent = liste.length;
  document.getElementById('pRows').innerHTML = liste.map(k => {
    const adet = sayac[k.id] || 0;
    const tamAd = [k.first_name, k.last_name].filter(Boolean).join(' ');
    const zimmetle = canWrite()
      ? `<button class="ghost" title="Bu kişiye cihaz zimmetle"
           onclick="zimmetPaneliAc(${k.id}, '${encodeURIComponent(tamAd)}',
                    () => loadPersonel())">+ Zimmetle</button>` : '';
    const fis = adet
      ? `<button class="ghost" title="Zimmet fişi (PDF)"
           onclick="openPdf('/documents/zimmet/user/${k.id}.pdf')">📄</button>` : '';
    return `<tr class="tikla" onclick="if(!event.target.closest('button'))kisiDetay(${k.id})">
      <td><b>${kacir(tamAd)}</b></td>
      <td class="muted gizle-mobil">${esc(k.employee_num)}</td>
      <td>${esc(k.department)}</td>
      <td class="muted gizle-mobil">${esc(k.sube)}</td>
      <td class="muted gizle-mobil">${esc(k.email)}</td>
      <td>${adet ? `<span class="tag used">${adet} cihaz</span>`
                 : '<span class="muted">—</span>'}</td>
      <td>${zimmetle}${fis}</td></tr>`;
  }).join('');
}

// ---------- Tanımlar (lokasyon, kategori, üretici…) ----------
function renderTanimlarView() {
  const alt = Object.entries(TANIMLAR).map(([k, v]) =>
    `<button class="ghost ${k === aktifTanim ? 'sec' : ''}"
       onclick="secTanim('${k}')">${v.label}</button>`).join(' ');
  document.getElementById('view').innerHTML =
    sayfaBasligi('🗂️', 'Tanımlar',
      'Lokasyon, kategori, marka, model ve diğer referans tabloları') + `
    <div class="panel"><h2>Tanım tablosu seç</h2>
      <div class="row">${alt}</div></div>
    <div id="tanimIcerik"></div>`;
  loadTanim();
}

function secTanim(k) { aktifTanim = k; renderTanimlarView(); }

// İlişki alanları (marka, cihaz tipi…) için kimlik -> ad haritaları
let tanimSecenek = {};

async function tanimSecenekleriYukle(cfg) {
  tanimSecenek = {};
  for (const [k, , uc] of cfg.sec || []) {
    try {
      const liste = await api(uc + '?limit=1000');
      tanimSecenek[k] = liste;
    } catch { tanimSecenek[k] = []; }
  }
}

// İlişki sütunu kimlik değil ad göstermeli ("3" değil "HP")
function tanimGoster(cfg, it, k) {
  const liste = tanimSecenek[k];
  if (!liste) return esc(it[k]);
  const bulunan = liste.find(x => x.id === it[k]);
  return bulunan ? kacir(bulunan.name)
                 : '<span class="muted">— eksik —</span>';
}

async function loadTanim() {
  const cfg = TANIMLAR[aktifTanim];
  const items = await api(cfg.endpoint + '?limit=500');
  await tanimSecenekleriYukle(cfg);
  const head = cfg.cols.map(([, l]) => `<th>${l}</th>`).join('') +
    (canWrite() ? '<th></th>' : '');
  const rows = items.map(it => `<tr${canWrite() ? ' class="tikla" onclick="tanimDuzenle(' + it.id + ')"' : ''}>` +
    cfg.cols.map(([k]) => `<td>${tanimGoster(cfg, it, k)}</td>`).join('') +
    (canWrite() ? '<td class="muted">✏️</td>' : '') + '</tr>').join('');
  document.getElementById('tanimIcerik').innerHTML = `
    ${canWrite() ? `<div class="panel">
      <h2>${cfg.label} — ekle</h2>
      <div class="row">
        ${cfg.add.map(([k, l, t]) =>
          `<input id="t_${k}" type="${t}" placeholder="${l}"
             class="${k === 'name' ? 'grow' : ''}" />`).join('')}
        ${(cfg.sec || []).map(([k, l]) => `<select id="t_${k}">
          <option value="">${l} seçilmedi</option>
          ${(tanimSecenek[k] || []).map(o =>
            `<option value="${o.id}">${kacir(o.name)}</option>`).join('')}
        </select>`).join('')}
        <button class="primary" onclick="addTanim()">Ekle</button>
      </div>
      <div id="tanimInfo" class="note"></div>
    </div>` : ''}
    <div class="panel">
      <h2>${cfg.label} (${items.length})</h2>
      <table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>
    </div>`;
}

// Tanım kaydını düzenle (lokasyon, kategori, üretici…)
async function tanimDuzenle(id) {
  const cfg = TANIMLAR[aktifTanim];
  const kayit = await api(`${cfg.endpoint}/${id}`);
  // Düzenlemede tüm görünür sütunlar + ekleme alanları birleşir
  const secKeys = new Set((cfg.sec || []).map(([k]) => k));
  const anahtarlar = [...new Set([
    ...cfg.add.map(([k, l, t]) => [k, l, t]).map(x => JSON.stringify(x)),
    ...cfg.cols.filter(([k]) => k !== 'type' && !secKeys.has(k))
               .map(([k, l]) => JSON.stringify([k, l, 'text'])),
  ])].map(x => JSON.parse(x));

  modalAc(`✏️ ${cfg.label} — ${kayit.name} düzenle`, `
    <div class="alan-grid">
      ${anahtarlar.map(([k, l, t]) => `<div>
        <div class="stat-l" style="margin-bottom:3px">${l}</div>
        <input id="td_${k}" type="${t || 'text'}" style="width:100%"
          value="${kayit[k] ?? ''}" /></div>`).join('')}
      ${(cfg.sec || []).map(([k, l]) => `<div>
        <div class="stat-l" style="margin-bottom:3px">${l}</div>
        <select id="td_${k}" style="width:100%">
          <option value="">— seçilmedi —</option>
          ${(tanimSecenek[k] || []).map(o =>
            `<option value="${o.id}" ${o.id === kayit[k] ? 'selected' : ''}
             >${kacir(o.name)}</option>`).join('')}
        </select></div>`).join('')}
    </div>
    <div class="row" style="margin-top:16px">
      <button class="primary" onclick="tanimKaydet(${id})">Kaydet</button>
      <button class="ghost" onclick="modalKapat()">Vazgeç</button>
      <span class="grow"></span>
      <button class="ghost" onclick="tanimSil(${id})"
        style="color:var(--err)">Sil</button>
    </div>
    <div id="tdInfo" class="note"></div>`);
}

async function tanimKaydet(id) {
  const cfg = TANIMLAR[aktifTanim];
  const govde = {};
  const secKeys = new Set((cfg.sec || []).map(([k]) => k));
  for (const el of document.querySelectorAll('[id^="td_"]')) {
    const v = el.value.trim();
    const alan = el.id.slice(3);
    govde[alan] = v === '' ? null : (secKeys.has(alan) ? Number(v) : v);
  }
  if (!govde.name) {
    document.getElementById('tdInfo').textContent = 'Ad zorunlu.'; return;
  }
  try {
    await api(`${cfg.endpoint}/${id}`, { method: 'PUT',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(govde) });
    modalKapat(); loadTanim();
    filtreSecenekleriDoldur();   // filtre listeleri güncel kalsın
  } catch (e) {
    document.getElementById('tdInfo').innerHTML =
      `<span style="color:var(--err)">⚠ ${e.detail || 'Kaydedilemedi'}</span>`;
  }
}

async function tanimSil(id) {
  const cfg = TANIMLAR[aktifTanim];
  if (!confirm(`Bu ${cfg.label.toLowerCase()} kaydı silinsin mi?\n` +
               `Bu kayda bağlı cihazlar silinmez, yalnızca bağlantı kalkar.`)) return;
  try {
    await api(`${cfg.endpoint}/${id}`, { method: 'DELETE' });
    modalKapat(); loadTanim(); filtreSecenekleriDoldur();
  } catch (e) {
    document.getElementById('tdInfo').innerHTML =
      `<span style="color:var(--err)">⚠ ${e.detail || 'Silinemedi'}</span>`;
  }
}

async function addTanim() {
  const cfg = TANIMLAR[aktifTanim];
  const body = {};
  for (const [k, , t] of cfg.add) {
    const v = document.getElementById('t_' + k).value.trim();
    if (v !== '') body[k] = t === 'number' ? Number(v) : v;
  }
  for (const [k] of cfg.sec || []) {
    const v = document.getElementById('t_' + k)?.value;
    if (v) body[k] = Number(v);
  }
  if (!body.name) { tanimInfo.textContent = 'Ad zorunlu.'; return; }
  try {
    await api(cfg.endpoint, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    tanimInfo.textContent = '✓ Eklendi.'; loadTanim();
  } catch (e) { tanimInfo.textContent = '⚠ ' + (e.detail || 'Hata'); }
}

// ---------- Excel içe/dışa aktarım ----------
let excelVeri = null;

function renderExcelView() {
  document.getElementById('view').innerHTML =
    sayfaBasligi('📄', 'Excel Aktarım',
      'Cihaz listesini Excel dosyasından içe aktarın ya da dışa alın') + `
    <div class="panel">
      <h2>Excel'den içe aktar</h2>
      <p class="note" style="margin-top:0">
        Kurum envanter dosyanı yükle. Önce önizleme gösterilir —
        <b>onaylamadan hiçbir şey kaydedilmez.</b> Seri numarası eşleşen
        cihazlar güncellenir, yeniler eklenir.</p>
      ${canWrite() ? `<div class="row">
        <input type="file" id="xlFile" accept=".xlsx,.xlsm" class="grow" />
        <button class="primary" onclick="excelOku()">Önizle</button>
      </div>
      <div id="xlInfo" class="note"></div>`
      : '<div class="muted">İçe aktarım için yazma yetkisi gerekir.</div>'}
    </div>
    <div class="panel">
      <h2>Dışa aktar</h2>
      <div class="row">
        <button class="ghost" onclick="excelIndir('/excel/disa-aktar.xlsx','envanter.xlsx')">
          📊 Tüm envanteri Excel indir</button>
        <button class="ghost" onclick="excelIndir('/excel/sablon.xlsx','envanter-sablon.xlsx')">
          📄 Boş şablon indir</button>
        <button class="ghost" onclick="downloadCsv(event)">CSV indir</button>
      </div>
      <div class="note">Dışa aktarım, içe aktarımla aynı sütun düzenini kullanır —
        indirip düzenleyip geri yükleyebilirsin.</div>
    </div>
    <div id="xlResult"></div>`;
}

async function excelIndir(yol, dosyaAdi) {
  try {
    const r = await fetch(url(yol), { headers: { 'Authorization': `Bearer ${token}` } });
    if (!r.ok) throw await r.json().catch(() => ({ detail: 'Hata' }));
    const u = URL.createObjectURL(await r.blob());
    const a = document.createElement('a'); a.href = u; a.download = dosyaAdi; a.click();
    setTimeout(() => URL.revokeObjectURL(u), 30000);
  } catch (e) { alert('⚠ ' + (e.detail || 'İndirilemedi')); }
}

async function excelOku() {
  const f = document.getElementById('xlFile').files[0];
  const bilgi = document.getElementById('xlInfo');
  if (!f) { bilgi.textContent = 'Önce bir dosya seç.'; return; }
  bilgi.textContent = '⏳ Dosya okunuyor…';
  document.getElementById('xlResult').innerHTML = '';
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch(url('/excel/oku'), {
      method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: fd });
    if (!r.ok) throw await r.json().catch(() => ({ detail: 'Hata' }));
    excelVeri = await r.json();
    bilgi.innerHTML = `✓ <b>${excelVeri.toplam}</b> satır okundu.`;
    excelOnizle();
  } catch (e) {
    bilgi.innerHTML = `<span style="color:var(--err)">⚠ ${e.detail || 'Okunamadı'}</span>`;
  }
}

function excelOnizle() {
  const d = excelVeri;
  const tipler = Object.entries(d.tipler)
    .map(([t, n]) => `<span class="pill">${t}: <b>${n}</b></span>`).join(' ');
  const uyarilar = (d.uyarilar || []).length
    ? `<div class="panel" style="border-color:var(--warn)">
         <h2>Uyarılar</h2>${d.uyarilar.map(u => `<div class="note">⚠ ${u}</div>`).join('')}
       </div>` : '';
  const ornek = d.ornekler.slice(0, 25).map(s => `<tr>
    <td>${esc(s.asset_tag)}</td><td>${esc(s.cihaz_tipi)}</td>
    <td>${esc([s.marka, s.model].filter(Boolean).join(' '))}</td>
    <td class="muted">${esc(s.serial)}</td>
    <td>${s.kullanici ? (s.kisi_mi ? s.kullanici
         : `<span class="muted">${s.kullanici} (yer)</span>`) : '—'}</td>
    <td class="muted">${Object.keys(s.ozellikler || {}).length} grup</td></tr>`).join('');

  document.getElementById('xlResult').innerHTML = `
    <div class="stats">
      <div class="stat"><div class="stat-v">${d.toplam}</div>
        <div class="stat-l">Satır</div></div>
      <div class="stat"><div class="stat-v">${Object.keys(d.tipler).length}</div>
        <div class="stat-l">Cihaz tipi</div></div>
      <div class="stat"><div class="stat-v">${d.kisi_sayisi}</div>
        <div class="stat-l">Kişi</div></div>
    </div>
    ${uyarilar}
    <div class="panel"><h2>Cihaz tipleri</h2><div class="row">${tipler}</div></div>
    <div class="panel">
      <h2>Örnek satırlar (ilk 25)</h2>
      <table><thead><tr><th>Cihaz NO</th><th>Tip</th><th>Marka/Model</th>
        <th>Seri</th><th>Kullanıcı</th><th>Özellik</th></tr></thead>
        <tbody>${ornek}</tbody></table>
      <div class="row" style="margin-top:14px">
        <button class="primary" onclick="excelAktar()">
          ✓ Onayla ve ${d.toplam} satırı aktar</button>
        <button class="ghost" onclick="renderExcelView()">Vazgeç</button>
      </div>
      <div id="xlAktarInfo" class="note"></div>
    </div>`;
}

async function excelAktar() {
  const bilgi = document.getElementById('xlAktarInfo');
  bilgi.textContent = '⏳ Aktarılıyor, bu biraz sürebilir…';
  try {
    const r = await api('/excel/aktar', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ satirlar: excelVeri.satirlar, guncelle: true }) });
    bilgi.innerHTML = `✓ <b>${r.eklenen}</b> yeni cihaz eklendi, ` +
      `<b>${r.guncellenen}</b> güncellendi` +
      (r.atlanan ? `, <span style="color:var(--err)">${r.atlanan} atlandı</span>` : '') +
      `. <a href="#" onclick="selectTab('assets');return false">Varlıklara git →</a>`;
    if (r.hatalar?.length)
      bilgi.innerHTML += '<br>' + r.hatalar.slice(0, 5)
        .map(h => `<span class="muted">${h}</span>`).join('<br>');
  } catch (e) {
    bilgi.innerHTML = `<span style="color:var(--err)">⚠ ${e.detail || 'Aktarılamadı'}</span>`;
  }
}

// ---------- Fatura okuma (Claude vision) ----------
let invoiceData = null;

function renderInvoiceView() {
  document.getElementById('view').innerHTML =
    sayfaBasligi('🧾', 'Fatura Oku',
      'Fatura veya irsaliye görselinden cihazları otomatik çıkarın') + `
    <div class="panel">
      <h2>Fatura / irsaliye oku</h2>
      <p class="note" style="margin-top:0">
        Fatura fotoğrafını veya PDF'ini yükle; Claude kalemleri çıkarsın.
        <b>Onaylamadan hiçbir şey kaydedilmez.</b></p>
      <div class="row">
        <input type="file" id="invFile" accept="image/*,application/pdf" class="grow" />
        <button class="primary" onclick="readInvoice()">Oku</button>
      </div>
      <div id="invInfo" class="note"></div>
    </div>
    <div id="invResult"></div>`;
}

async function readInvoice() {
  const f = document.getElementById('invFile').files[0];
  const info = document.getElementById('invInfo');
  if (!f) { info.textContent = 'Önce bir dosya seç.'; return; }
  info.textContent = '⏳ Fatura okunuyor, bu birkaç saniye sürebilir…';
  document.getElementById('invResult').innerHTML = '';
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch(url('/invoices/oku'), {
      method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: fd });
    if (!r.ok) throw await r.json().catch(() => ({ detail: 'Hata' }));
    invoiceData = await r.json();
    info.innerHTML = `✓ Okundu — <b>${invoiceData.kalemler.length}</b> kalem bulundu. ` +
      `Kontrol edip onayla.`;
    renderInvoiceLines();
  } catch (e) {
    info.innerHTML = `<span style="color:var(--err)">⚠ ${e.detail || 'Okunamadı'}</span>`;
  }
}

function renderInvoiceLines() {
  const d = invoiceData;
  const rows = d.kalemler.map((k, i) => `<tr>
    <td><input type="checkbox" id="k_ok_${i}" checked /></td>
    <td><input id="k_ad_${i}" value="${(k.ad || '').replace(/"/g, '&quot;')}" class="grow" /></td>
    <td><input id="k_adet_${i}" type="number" min="1" value="${k.adet || 1}" style="width:70px" /></td>
    <td><input id="k_fiyat_${i}" type="number" step="0.01" value="${k.birim_fiyat ?? ''}" style="width:110px" /></td>
    <td><input id="k_pre_${i}" value="BT" style="width:70px" title="Etiket ön eki" /></td>
    <td class="muted">${k.kategori ?? '—'}</td></tr>`).join('');

  document.getElementById('invResult').innerHTML = `
    <div class="panel">
      <h2>Fatura bilgileri</h2>
      <div class="row">
        <input id="inv_no" value="${d.fatura_no ?? ''}" placeholder="Fatura no" />
        <input id="inv_date" type="date" value="${d.fatura_tarihi ?? ''}" />
        <input id="inv_sup" value="${d.tedarikci ?? ''}" placeholder="Tedarikçi" class="grow" disabled />
      </div>
    </div>
    <div class="panel">
      <h2>Kalemler (${d.kalemler.length})</h2>
      <table><thead><tr><th></th><th>Ürün</th><th>Adet</th><th>Birim fiyat</th>
        <th>Etiket ön eki</th><th>Kategori</th></tr></thead>
        <tbody>${rows}</tbody></table>
      <div class="row" style="margin-top:12px">
        <button class="primary" onclick="importInvoice()">Onayla ve envantere ekle</button>
        <button class="ghost" onclick="renderInvoiceView()">Vazgeç</button>
      </div>
      <div id="invImportInfo" class="note"></div>
    </div>`;
}

async function importInvoice() {
  const kalemler = [];
  invoiceData.kalemler.forEach((k, i) => {
    if (!document.getElementById(`k_ok_${i}`).checked) return;
    const fiyat = document.getElementById(`k_fiyat_${i}`).value;
    kalemler.push({
      ad: document.getElementById(`k_ad_${i}`).value.trim(),
      adet: Number(document.getElementById(`k_adet_${i}`).value) || 1,
      birim_fiyat: fiyat === '' ? null : Number(fiyat),
      seri_no: k.seri_no || null,
      asset_tag_prefix: document.getElementById(`k_pre_${i}`).value.trim() || 'BT',
    });
  });
  const info = document.getElementById('invImportInfo');
  if (!kalemler.length) { info.textContent = 'Hiç kalem seçilmedi.'; return; }
  try {
    const res = await api('/invoices/aktar', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        kalemler,
        fatura_no: document.getElementById('inv_no').value.trim() || null,
        purchase_date: document.getElementById('inv_date').value || null,
      })
    });
    info.innerHTML = `✓ <b>${res.eklenen}</b> varlık eklendi: ` +
      res.varliklar.map(v => v.asset_tag).join(', ');
  } catch (e) { info.innerHTML = `<span style="color:var(--err)">⚠ ${e.detail || 'Hata'}</span>`; }
}

// ---------- Özet / dashboard ----------
// KPI kartı: ikon + büyük sayı + etiket, sol kenarı renk kodlu
function statCard(label, value, ikon = '📦', renk = '', extra = '', tikla = '') {
  return `<div class="stat ${renk}${tikla ? ' tikla-kart' : ''}"
              ${tikla ? `onclick="${tikla}" title="Aç"` : ''}>
    <div class="kutu">${ikon}</div>
    <div><div class="stat-v">${value}</div>
         <div class="stat-l">${label}</div>${extra}</div>
  </div>`;
}

// Yetkili dosya indirme: <a href> Authorization başlığı gönderemez, bu yüzden
// içerik blob olarak çekilir; ad sunucunun Content-Disposition'ından okunur.
async function indirDosya(path, varsayilanAd = 'rapor.xlsx') {
  try {
    const r = await fetch(url(path),
                          { headers: { 'Authorization': `Bearer ${token}` } });
    if (!r.ok) throw await r.json().catch(() => ({ detail: 'İndirilemedi' }));
    const cd = r.headers.get('content-disposition') || '';
    const m = cd.match(/filename\*=UTF-8''([^;]+)/);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await r.blob());
    a.download = m ? decodeURIComponent(m[1]) : varsayilanAd;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  } catch (e) { alert('⚠ ' + (e.detail || e.message || 'İndirilemedi')); }
}

// Hızlı işlem kartı
function kisayol(ikon, etiket, islev) {
  return `<button class="kisayol" onclick="${islev}">
    <span class="ikon">${ikon}</span><b>${etiket}</b></button>`;
}

function barList(items, max) {
  if (!items.length) return '<div class="muted">Kayıt yok</div>';
  return items.slice(0, 8).map(x => {
    const pct = max ? Math.round((x.adet / max) * 100) : 0;
    return `<div class="bar-row"><span class="bar-lbl">${x.ad}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${pct}%"></span></span>
      <span class="bar-num">${x.adet}</span></div>`;
  }).join('');
}

// Canlı dashboard: sekme açıkken belirli aralıkla kendini yeniler
let canliZaman = null;
let canliAralik = Number(localStorage.getItem('canliAralik') || 30);

function canliDurdur() {
  if (canliZaman) { clearInterval(canliZaman); canliZaman = null; }
}

function canliBaslat() {
  canliDurdur();
  if (!canliAralik) return;
  canliZaman = setInterval(() => {
    // Yalnızca Özet sekmesi açık ve sayfa görünürken yenile
    if (activeTab === 'dashboard' && !document.hidden && !document.getElementById('modalArka'))
      renderDashboard(true);
  }, canliAralik * 1000);
}

function canliAralikDegistir(saniye) {
  canliAralik = Number(saniye);
  localStorage.setItem('canliAralik', canliAralik);
  canliBaslat();
  const et = document.getElementById('canliDurum');
  if (et) et.textContent = canliAralik
    ? `● canlı — ${canliAralik} sn'de bir yenileniyor` : '○ otomatik yenileme kapalı';
}

document.addEventListener('visibilitychange', () => {
  // Sekmeye geri dönüldüğünde hemen tazele
  if (!document.hidden && activeTab === 'dashboard') renderDashboard(true);
});

async function renderDashboard(sessiz = false) {
  const view = document.getElementById('view');
  if (!sessiz)
    view.innerHTML = '<div class="panel"><h2>Özet</h2><div class="muted">Yükleniyor…</div></div>';
  const [ozet, dag, dusuk, garanti, personel, islemler, sistem] =
    await Promise.all([
      api('/reports/ozet'), api('/reports/dagilim'), api('/reports/dusuk-stok'),
      api('/reports/garanti?gun=90'), api('/reports/personel-zimmet'),
      api('/reports/son-islemler').catch(() => []),
      api('/ag/ozet').catch(() => null),
    ]);
  const tl = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY',
    maximumFractionDigits: 0 }).format(ozet.toplam_deger || 0);
  const maxK = Math.max(1, ...dag.kategori.map(x => x.adet));
  const maxL = Math.max(1, ...dag.lokasyon.map(x => x.adet));

  view.innerHTML =
    sayfaBasligi('📊', 'Kontrol Paneli',
      `<span id="canliDurum">${canliAralik
         ? `● canlı — ${canliAralik} sn'de bir yenileniyor`
         : '○ otomatik yenileme kapalı'}</span>
       <span>·</span>
       <span>Son güncelleme: ${new Date().toLocaleTimeString('tr-TR')}</span>`) + `
    <div class="kisayollar">
      ${kisayol('➕', 'Yeni cihaz', "selectTab('assets')")}
      ${kisayol('🔳', 'Barkod okut', "selectTab('assets')")}
      ${kisayol('👥', 'Personel', "selectTab('personel')")}
      ${kisayol('📄', 'Excel aktarım', "selectTab('excel')")}
    </div>
    <div class="row" style="justify-content:flex-end; margin-bottom:12px">
      <select onchange="canliAralikDegistir(this.value)" title="Otomatik yenileme">
        <option value="0"${!canliAralik ? ' selected' : ''}>Yenileme: kapalı</option>
        <option value="10"${canliAralik === 10 ? ' selected' : ''}>10 sn</option>
        <option value="30"${canliAralik === 30 ? ' selected' : ''}>30 sn</option>
        <option value="60"${canliAralik === 60 ? ' selected' : ''}>1 dk</option>
        <option value="300"${canliAralik === 300 ? ' selected' : ''}>5 dk</option>
      </select>
      <button class="ghost" onclick="renderDashboard(true)" title="Şimdi yenile">⟳</button>
    </div>
    <div class="stats">
      ${statCard('Toplam varlık', ozet.varlik_toplam, '📦', '', '',
                 "selectTab('assets')")}
      ${statCard('Zimmetli', ozet.zimmetli, '🤝', 'sari', '',
                 "selectTab('assets')")}
      ${statCard('Boşta', ozet.bosta, '📥', 'mavi', '', "selectTab('assets')")}
      ${ozet.toplam_deger ? statCard('Toplam değer', tl, '₺', 'mor')
        : statCard('Sistem ürünü', sistem?.toplam ?? 0, '🌐', 'mor', '',
                   "selectTab('ag')")}
      ${statCard('Personel', ozet.personel, '👥', 'mavi', '',
                 "selectTab('personel')")}
      ${statCard('Lisans', ozet.lisans, '🔑', 'kirmizi', '',
                 "selectTab('licenses')")}
    </div>
    ${ozet.markasiz_cihaz ? `<div class="panel" style="border-left:4px solid var(--warn)">
      ⚠ <b>${ozet.markasiz_cihaz} cihazın markası boş.</b>
      <a href="#" onclick="selectTab('tanimlar');return false">Tanımlar → Modeller</a>'den
      seçin ya da sunucuda <code>scripts/marka-kontrol.py</code> çalıştırın.
    </div>` : ''}
    <div class="panel">
      <div class="row" style="align-items:center; margin-bottom:10px">
        <h2 style="margin:0; flex:1">Excel Raporları</h2>
        <span class="muted" style="font-size:12.5px">başlıklı · süzgeçli · yazdırmaya hazır</span>
      </div>
      <div class="row" style="flex-wrap:wrap">
        <button class="primary" onclick="indirDosya('/reports/excel?tip=genel')">
          📗 Genel rapor</button>
        <button class="ghost" onclick="indirDosya('/reports/excel?tip=cihazlar')">
          💻 Cihaz listesi</button>
        <button class="ghost" onclick="indirDosya('/reports/excel?tip=zimmet')">
          🤝 Zimmet raporu</button>
        <button class="ghost" onclick="indirDosya('/reports/excel?tip=lokasyon')">
          🏗️ Lokasyon raporu</button>
        <button class="ghost" onclick="indirDosya('/reports/excel?tip=stok')">
          📦 Stok raporu</button>
        <button class="ghost" onclick="indirDosya('/reports/excel?tip=sistem')">
          🌐 Sistem ürünleri</button>
      </div>
    </div>
    <div class="two-col">
      <div class="panel"><h2>Kategoriye göre</h2>${barList(dag.kategori, maxK)}</div>
      <div class="panel"><h2>Lokasyona göre</h2>${barList(dag.lokasyon, maxL)}</div>
    </div>
    <div class="panel">
      <h2>Düşük stok (${dusuk.length})</h2>
      ${dusuk.length ? `<table><thead><tr><th>Tür</th><th>Ad</th><th>Adet</th><th>Min</th></tr></thead>
        <tbody>${dusuk.map(x => `<tr><td class="muted">${x.tur}</td><td>${x.ad}</td>
          <td><span class="tag low">${x.adet}</span></td><td class="muted">${x.min}</td></tr>`).join('')}
        </tbody></table>` : '<div class="muted">Kritik seviyede stok yok 👍</div>'}
    </div>
    <div class="panel">
      <h2>Garantisi biten / bitecek (90 gün) — ${garanti.length}</h2>
      ${garanti.length ? `<table><thead><tr><th>Etiket</th><th>Cihaz</th><th>Bitiş</th><th>Kalan</th></tr></thead>
        <tbody>${garanti.slice(0, 15).map(x => `<tr class="tikla" onclick="cihazDetay(${x.id})"><td><b>${x.asset_tag}</b></td>
          <td>${x.ad ?? '<span class="muted">—</span>'}</td><td>${x.garanti_bitis}</td>
          <td>${x.bitti ? '<span class="tag low">bitti</span>'
                         : `<span class="muted">${x.kalan_gun} gün</span>`}</td></tr>`).join('')}
        </tbody></table>` : '<div class="muted">Yaklaşan garanti bitişi yok</div>'}
    </div>
    <div class="panel">
      <h2>Son işlemler</h2>
      ${islemler.length ? `<table><thead><tr><th>Ne</th><th>İşlem</th>
        <th class="gizle-mobil">Not</th><th>Kim</th><th>Ne zaman</th></tr></thead>
        <tbody>${islemler.map(x => `<tr class="${x.hedef_tur === 'asset' || x.hedef_tur === 'user' ? 'tikla' : ''}"
            onclick="${x.hedef_tur === 'asset' ? `cihazDetay(${x.hedef_id})`
                     : x.hedef_tur === 'user' ? `kisiDetay(${x.hedef_id})` : ''}">
          <td><b>${kacir(x.hedef)}</b></td>
          <td>${kacir(x.eylem)}</td>
          <td class="muted gizle-mobil">${esc(x['not'])}</td>
          <td class="muted">${esc(x.yapan)}</td>
          <td class="muted">${x.tarih
            ? new Date(x.tarih).toLocaleString('tr-TR',
                {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})
            : '—'}</td></tr>`).join('')}</tbody></table>`
        : '<div class="muted">Henüz kayıtlı işlem yok</div>'}
    </div>
    <div class="panel">
      <h2>Personel başına zimmet</h2>
      ${personel.length ? `<table><thead><tr><th>Personel</th><th>Departman</th><th>Cihaz</th><th></th></tr></thead>
        <tbody>${personel.slice(0, 15).map(x => `<tr class="tikla" onclick="if(!event.target.closest('button'))kisiDetay(${x.user_id})"><td>${x.ad}</td>
          <td class="muted">${x.departman ?? '—'}</td><td>${x.cihaz_sayisi}</td>
          <td><button class="ghost" title="Zimmet fişi (PDF)"
                onclick="openPdf('/documents/zimmet/user/${x.user_id}.pdf')">📄</button></td>
          </tr>`).join('')}</tbody></table>` : '<div class="muted">Zimmetli cihaz yok</div>'}
    </div>`;
}

// HTML kaçırma. Cihaz adları/özellikler Excel'den geliyor; <, >, " ve '
// karakterleri kaçırılmazsa sayfaya HTML enjekte edilebilir.
const kacir = (v) => String(v ?? '').replace(/[&<>"']/g, c => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// Boş değerleri "—" gösterir, dolu olanları kaçırır (hücre içi gösterim).
const esc = (v) => v == null || v === ''
  ? '<span class="muted">—</span>' : kacir(v);
const tl = (v) => v == null ? '—' : new Intl.NumberFormat('tr-TR',
  { style:'currency', currency:'TRY', maximumFractionDigits:0 }).format(v);

// ---------- Detay penceresi (modal) ----------
function modalAc(baslik, govdeHtml, ekButonlar = '') {
  // Zincirleme pencerelerde (kaydet → detayı yeniden aç) erken yenileme
  // olmasın: bayrak son kapanışa kadar bekler.
  modalKapat(false);
  const d = document.createElement('div');
  d.className = 'modal-arka';
  d.id = 'modalArka';
  d.onclick = (e) => { if (e.target === d) modalKapat(); };
  d.innerHTML = `<div class="modal">
    <div class="modal-bas"><h3>${baslik}</h3>${ekButonlar}
      <button class="kapat" onclick="modalKapat()" title="Kapat">✕</button></div>
    <div class="modal-govde">${govdeHtml}</div></div>`;
  document.body.appendChild(d);
}
function modalKapat(yenile = true) {
  const acikti = document.getElementById('modalArka');
  acikti?.remove();
  if (yenile && acikti && verilerDegisti) {
    verilerDegisti = false;
    aktifVeriyiYenile();
  }
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') modalKapat(); });

function alanlar(obj, etiketler) {
  const parcalar = etiketler
    .filter(([k]) => obj[k] != null && obj[k] !== '')
    .map(([k, l]) => `<div class="alan"><span class="et">${l}</span>
                      <span class="dg">${obj[k]}</span></div>`);
  return parcalar.length ? `<div class="alan-grid">${parcalar.join('')}</div>`
                         : '<div class="muted">Bilgi yok</div>';
}

// ---------- Cihaz detayı ----------
async function cihazDetay(id) {
  let d;
  try { d = await api('/detay/asset/' + id); }
  catch (e) { return alert('⚠ ' + (e.detail || 'Detay alınamadı')); }
  const k = d.kunye, z = d.zimmet;

  const yaz = canWrite();
  const ozellikHtml = Object.entries(d.ozellikler || {}).map(([grup, degerler]) => {
    if (!degerler || typeof degerler !== 'object') return '';
    // Grup/alan adları öznitelik içine gömüldüğü için URL kodlaması
    // kullanılır: çıktısında tırnak/boşluk olmaz, işlev tarafında çözülür.
    const g = encodeURIComponent(grup);
    const satirlar = Object.entries(degerler)
      .map(([a, v]) => `<div class="alan">
          <span class="et">${esc(a)}</span>
          <span class="dg">${esc(v)}
          ${yaz ? `<button class="ghost mini" title="Düzenle"
             onclick="ozellikAc(${id}, '${g}', '${encodeURIComponent(a)}')">✏️</button>
           <button class="ghost mini" title="Sil"
             onclick="ozellikSil(${id}, '${g}', '${encodeURIComponent(a)}')">🗑</button>` : ''}
          </span></div>`).join('');
    // "Ağ" grubu tarihsel bir addır: yangın ve alarm ürünlerinin özellikleri
    // de bu grupta durur (veri taşımamak için yalnızca başlık değiştirilir).
    const baslik = grup === 'Ağ' ? 'Sistem Özellikleri' : grup;
    return satirlar ? `<div class="bolum"><h4>${esc(baslik)}</h4>
                       <div class="alan-grid">${satirlar}</div></div>` : '';
  }).join('');

  const ozellikBolumu = `
    <div class="bolum">
      <div class="row" style="align-items:center; margin-bottom:6px">
        <h4 style="margin:0; flex:1">Teknik Özellikler</h4>
        ${yaz ? `<button class="primary" onclick="ozellikAc(${id})">
                 + Özellik ekle</button>` : ''}
      </div>
      ${ozellikHtml || '<div class="muted">Kayıtlı teknik özellik yok</div>'}
    </div>`;

  // --- Dosyalar: cihaz görselleri + imzalı zimmet formları ---
  const dosyalar = d.dosyalar || [];
  const gorseller = dosyalar.filter(f => f.tur === 'gorsel');
  const belgeler = dosyalar.filter(f => f.tur !== 'gorsel');

  // Görsel ucu Authorization başlığı ister; <img src> başlık gönderemez,
  // bu yüzden içerik blob olarak çekilip src sonradan atanır.
  const gorselHtml = gorseller.length ? `<div class="gorsel-serit">
    ${gorseller.map(f => `<figure>
      <img data-dosya="${f.id}" alt="${kacir(f.dosya_adi)}"
           onclick="dosyaAc(${f.id})" title="Büyüt" />
      ${yaz ? `<button class="ghost mini" title="Sil"
         onclick="dosyaSil(${f.id}, ${id})">🗑</button>` : ''}
    </figure>`).join('')}</div>` : '';

  const belgeHtml = belgeler.length ? `<table><tbody>
    ${belgeler.map(f => `<tr>
      <td><a href="#" onclick="dosyaAc(${f.id});return false">📎 ${esc(f.dosya_adi)}</a></td>
      <td class="muted">${TUR_ADI[f.tur] || f.tur}</td>
      <td class="muted">${(f.boyut / 1024).toFixed(0)} KB</td>
      <td class="muted">${f.tarih ? new Date(f.tarih).toLocaleDateString('tr-TR') : ''}</td>
      ${yaz ? `<td><button class="ghost mini" title="Sil"
         onclick="dosyaSil(${f.id}, ${id})">🗑</button></td>` : ''}
    </tr>`).join('')}</tbody></table>` : '';

  const dosyaBolumu = `
    <div class="bolum">
      <h4>Görseller ve Belgeler</h4>
      ${gorselHtml}${belgeHtml}
      ${!dosyalar.length ? '<div class="muted">Yüklenmiş dosya yok</div>' : ''}
      ${yaz ? `<div class="row" style="margin-top:10px">
        <button class="ghost" onclick="dosyaSec(${id}, 'gorsel')">
          📷 Cihaz görseli yükle</button>
        <button class="ghost" onclick="dosyaSec(${id}, 'zimmet_formu')">
          ✍️ İmzalı zimmet formu yükle</button>
        <button class="ghost" onclick="dosyaSec(${id}, 'diger')">
          📎 Diğer belge</button>
      </div>` : ''}
    </div>`;

  const gecmisHtml = (d.gecmis || []).length
    ? `<table><thead><tr><th>İşlem</th><th>Not</th><th>Tarih</th></tr></thead><tbody>` +
      d.gecmis.slice(0, 10).map(g => `<tr><td>${g.islem}</td>
        <td class="muted">${g['not'] ?? '—'}</td>
        <td class="muted">${g.tarih ? new Date(g.tarih).toLocaleString('tr-TR') : '—'}</td>
        </tr>`).join('') + '</tbody></table>'
    : '<div class="muted">Kayıt yok</div>';

  const butonlar =
    (yaz ? (z.tur
      ? `<button class="ghost" onclick="cihazIadeAl(${id})">↩ İade al</button>`
      : `<button class="primary" onclick="checkoutPrompt(${id}, '${
          encodeURIComponent(k.asset_tag)}', () => cihazDetay(${id}))">
         Zimmetle</button>`) : '') + `
    <button class="ghost" onclick="openPdf('/documents/etiket/asset/${id}.pdf')"
      title="Etiket bas">🏷️</button>` +
    (z.kisi_id ? `<button class="ghost" title="Zimmet fişi"
      onclick="openPdf('/documents/zimmet/asset/${id}.pdf')">📄</button>` : '') +
    (yaz ? `<button class="ghost" onclick="cihazDuzenle(${id})">✏️ Düzenle</button>` : '');

  modalAc(k.name ? `${k.asset_tag} — ${k.name}` : k.asset_tag, `
    <div class="bolum"><h4>Künye</h4>${alanlar(k, [
      ['asset_tag','Cihaz NO'],['demirbas_no','Demirbaş No'],['serial','Seri No'],
      ['kategori','Cihaz Tipi'],['marka','Marka'],['model','Model'],
      ['durum','Durum'],['lokasyon','Bulunduğu Yer'],['ip_address','IP'],
      ['hostname','Hostname'],['mac_address','MAC'],['imei','IMEI'],
      ['barkod','Barkod'],['muhasebe_kodu','IFS/Muhasebe Kodu'],
      ['fatura_no','Fatura No'],['purchase_date','Alım Tarihi'],
      ['tedarikci','Tedarikçi'],['sirket','Alınan Şirket'],
      ['telefon_no','Telefon'],['sim_no','SIM'],['operator','Operatör'],
      ['warranty_end','Garanti Bitiş'],['notes','Açıklama'],
    ])}
    ${k.purchase_cost != null ? `<div class="alan" style="margin-top:6px">
      <span class="et">Alım Bedeli</span><span class="dg">${tl(k.purchase_cost)}</span></div>` : ''}
    </div>
    <div class="bolum"><h4>Zimmet</h4>${z.kisi || z.lokasyon ? alanlar(z, [
      ['kisi','Kişi'],['departman','Departman'],['unvan','Unvan'],
      ['lokasyon','Lokasyon'],['tarih','Zimmet Tarihi'],
    ]) : '<div class="muted">Cihaz boşta</div>'}
    ${z.kisi_id ? `<button class="ghost" style="margin-top:8px"
        onclick="kisiDetay(${z.kisi_id})">👤 ${z.kisi} — tüm cihazları</button>` : ''}
    </div>
    ${ozellikBolumu}
    ${dosyaBolumu}
    <div class="bolum"><h4>Geçmiş</h4>${gecmisHtml}</div>`, butonlar);

  gorselleriYukle();
}

// Korumalı görselleri token ile çekip <img>'lere yerleştirir.
async function gorselleriYukle() {
  for (const img of document.querySelectorAll('img[data-dosya]')) {
    try {
      const r = await fetch(url('/dosyalar/' + img.dataset.dosya),
                            { headers: { 'Authorization': `Bearer ${token}` } });
      if (!r.ok) throw new Error();
      img.src = URL.createObjectURL(await r.blob());
    } catch { img.replaceWith(Object.assign(document.createElement('div'),
                              { className: 'muted', textContent: 'Görsel yüklenemedi' })); }
  }
}

// ---------- Üst bar canlı arama (isim / cihaz no / seri no) ----------
let hizliZaman = null;
let hizliIstek = 0;

function hizliKapat() {
  document.getElementById('hizliSonuc')?.classList.add('hidden');
}

function hizliAra() {
  clearTimeout(hizliZaman);
  const q = document.getElementById('hizliAra').value.trim();
  if (!q) return hizliKapat();
  // Yazmayı kesmeden sonuç gelsin diye kısa gecikme (her tuşta istek atma)
  hizliZaman = setTimeout(() => hizliCalistir(q), 180);
}

async function hizliCalistir(q) {
  const sira = ++hizliIstek;
  let d;
  try { d = await api('/assets/ara?limit=8&q=' + encodeURIComponent(q)); }
  catch { return; }
  // Geç dönen eski istek, yeni sonucun üstüne yazmasın
  if (sira !== hizliIstek) return;

  const kutu = document.getElementById('hizliSonuc');
  if (!kutu) return;
  const parcalar = [];

  // Lokasyon/proje en üstte: en dar ve en kesin eşleşme burasıdır. Proje
  // kodu ("U026") aynı zamanda personelin departmanı olduğu için, kişi
  // listesi önce gelseydi şantiyeyi onlarca satırın altına iterdi.
  if (d.lokasyonlar.length) {
    parcalar.push('<div class="baslik">Lokasyon / Proje</div>');
    parcalar.push(d.lokasyonlar.map(l => `
      <div class="satir" onclick="hizliLokasyon(${l.id}, '${
          encodeURIComponent(l.proje_kodu || '')}')">
        <span>📍 ${kacir(l.ad)}${l.proje_kodu
          ? ` <span class="pill">${kacir(l.proje_kodu)}</span>` : ''}</span>
        <span class="ikincil">${l.cihaz_sayisi} cihaz</span>
      </div>`).join(''));
  }

  if (d.personel.length) {
    parcalar.push('<div class="baslik">Personel</div>');
    parcalar.push(d.personel.map(k => `
      <div class="satir" onclick="hizliSec('kisi', ${k.id})">
        <span>👤 ${kacir(k.ad)}</span>
        <span class="ikincil">${kacir([k.employee_num, k.department]
          .filter(Boolean).join(' · '))}</span>
      </div>`).join(''));
    if (d.personel_toplam > d.personel.length) {
      parcalar.push(`<div class="baslik">+${d.personel_toplam - d.personel.length}
                     kişi daha</div>`);
    }
  }

  if (d.cihazlar.length) {
    parcalar.push('<div class="baslik">Cihazlar</div>');
    parcalar.push(d.cihazlar.map(c => `
      <div class="satir" onclick="hizliSec('cihaz', ${c.id})">
        <span>💻 <b>${kacir(c.asset_tag)}</b> ${kacir(c.name || '')}</span>
        <span class="ikincil">${kacir([c.serial, c.zimmetli, c.lokasyon]
          .filter(Boolean).join(' · '))}</span>
      </div>`).join(''));
    if (d.cihaz_toplam > d.cihazlar.length) {
      parcalar.push(`<div class="satir" onclick="hizliTumu()">
        <span class="ikincil">↳ ${d.cihaz_toplam} cihazın tümünü listede göster</span>
        </div>`);
    }
  }

  kutu.innerHTML = parcalar.length ? parcalar.join('')
    : '<div class="bos">Sonuç yok</div>';
  kutu.classList.remove('hidden');
}

function hizliSec(tur, id) {
  hizliKapat();
  document.getElementById('hizliAra').value = '';
  if (tur === 'kisi') kisiDetay(id); else cihazDetay(id);
}

// Lokasyon seçilince listeyi o lokasyona (proje kodu varsa projeye) filtreler.
// Filtre açılır listeleri sunucudan asenkron doldurulduğu için seçim hemen
// yapılamayabilir; istek burada bekletilir ve seçenekler gelince uygulanır.
let bekleyenFiltre = null;

function hizliLokasyon(lokasyonId, projeKodu) {
  const kod = decodeURIComponent(projeKodu || '');
  hizliKapat();
  document.getElementById('hizliAra').value = '';
  // Proje kodu varsa proje filtresi tüm şantiyeyi kapsar; yoksa lokasyon
  bekleyenFiltre = kod ? { alan: 'fProje', deger: kod }
                       : { alan: 'fLokasyon', deger: String(lokasyonId) };
  if (activeTab === 'assets') {
    filtreleriSifirla();
    bekleyenFiltreyiUygula();
  } else {
    selectTab('assets');   // görünüm + seçenekler yüklenince uygulanır
  }
}

function bekleyenFiltreyiUygula() {
  if (!bekleyenFiltre) return;
  const el = document.getElementById(bekleyenFiltre.alan);
  if (!el) return;                       // görünüm henüz oluşmadı
  el.value = bekleyenFiltre.deger;
  // Seçenek listesi henüz gelmediyse atama tutmaz; sonraki denemeye bırak
  if (el.value !== bekleyenFiltre.deger) return;
  bekleyenFiltre = null;
  loadAssets();
}

// Arama terimini varlık listesi filtresine taşır
function hizliTumu() {
  const q = document.getElementById('hizliAra').value.trim();
  hizliKapat();
  selectTab('assets');
  setTimeout(() => {
    const el = document.getElementById('fAra');
    if (el) { el.value = q; loadAssets(); }
  }, 120);
}

// Kutunun dışına tıklanınca kapat
document.addEventListener('click', (e) => {
  if (!e.target.closest('#hizliKutu')) hizliKapat();
});

// ---------- Teknik özellik ekleme / düzenleme ----------
let ozellikSablonu = null;

async function ozellikAc(assetId, grupKodlu = '', adKodlu = '') {
  // Öznitelikten URL kodlu geliyorlar (bkz. cihazDetay)
  const grup = decodeURIComponent(grupKodlu);
  const ad = decodeURIComponent(adKodlu);
  if (!ozellikSablonu) {
    try { ozellikSablonu = await api('/assets/ozellik-sablonu'); }
    catch { ozellikSablonu = []; }
  }
  let mevcut = '';
  if (grup && ad) {
    const d = await api('/detay/asset/' + assetId).catch(() => null);
    mevcut = d?.ozellikler?.[grup]?.[ad] ?? '';
  }
  const gruplar = ozellikSablonu.map(s => s.grup);
  // Şablonda olmayan (elle açılmış) gruplar da listede çıksın
  if (grup && !gruplar.includes(grup)) gruplar.push(grup);

  modalAc(ad ? `Özellik: ${kacir(ad)}` : 'Teknik özellik ekle', `
    <div class="form-grid">
      <label>Grup
        <input id="ozGrup" list="ozGrupListe" value="${kacir(grup)}"
               placeholder="örn. İşlemci" />
        <datalist id="ozGrupListe">
          ${gruplar.map(g => `<option value="${kacir(g)}"></option>`).join('')}
        </datalist>
      </label>
      <label>Alan adı
        <input id="ozAd" list="ozAdListe" value="${kacir(ad)}"
               placeholder="örn. İşlemci Markası" />
        <datalist id="ozAdListe"></datalist>
      </label>
      <label style="grid-column:1/-1">Değer
        <input id="ozDeger" value="${kacir(mevcut)}"
               onkeydown="if(event.key==='Enter')ozellikKaydet(${assetId})" />
      </label>
    </div>
    <div class="row" style="margin-top:14px">
      <button class="primary" onclick="ozellikKaydet(${assetId})">Kaydet</button>
      <button class="ghost" onclick="cihazDetay(${assetId})">Vazgeç</button>
    </div>`);
  document.getElementById('ozGrup').oninput = ozellikAlanOner;
  ozellikAlanOner();
  setTimeout(() => document.getElementById(grup ? 'ozDeger' : 'ozGrup')?.focus(), 60);
}

function ozellikAlanOner() {
  const grup = document.getElementById('ozGrup')?.value.trim();
  const liste = document.getElementById('ozAdListe');
  if (!liste) return;
  const s = (ozellikSablonu || []).find(x => x.grup === grup);
  liste.innerHTML = (s?.alanlar || [])
    .map(a => `<option value="${kacir(a)}"></option>`).join('');
}

async function ozellikKaydet(assetId) {
  const grup = document.getElementById('ozGrup').value.trim();
  const ad = document.getElementById('ozAd').value.trim();
  if (!grup || !ad) return alert('⚠ Grup ve alan adı zorunlu.');
  try {
    await api(`/assets/${assetId}/ozellik`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grup, ad,
                             deger: document.getElementById('ozDeger').value }),
    });
    cihazDetay(assetId);
  } catch (e) { alert('⚠ ' + (e.detail || 'Özellik kaydedilemedi')); }
}

async function ozellikSil(assetId, grupKodlu, adKodlu) {
  const grup = decodeURIComponent(grupKodlu), ad = decodeURIComponent(adKodlu);
  if (!confirm(`"${grup} / ${ad}" özelliği silinsin mi?`)) return;
  try {
    await api(`/assets/${assetId}/ozellik?grup=${grupKodlu}&ad=${adKodlu}`,
              { method: 'DELETE' });
    cihazDetay(assetId);
  } catch (e) { alert('⚠ ' + (e.detail || 'Silinemedi')); }
}

// ---------- Dosya yükleme (cihaz görseli / imzalı zimmet formu) ----------
// Dosya türü adları cihaz ve kişi ekranlarının ikisinde de kullanılır
const TUR_ADI = { gorsel: 'Görsel', zimmet_formu: 'İmzalı zimmet formu',
                  fatura: 'Fatura', diger: 'Diğer' };

function dosyaSec(assetId, tur) {
  const girdi = document.createElement('input');
  girdi.type = 'file';
  if (tur === 'gorsel') girdi.accept = 'image/*';
  girdi.onchange = () => girdi.files[0] && dosyaYukle(assetId, tur, girdi.files[0]);
  girdi.click();
}

async function dosyaYukle(assetId, tur, dosya) {
  const veri = new FormData();
  veri.append('file', dosya);
  veri.append('tur', tur);
  try {
    // FormData'da Content-Type'ı tarayıcı belirlemeli (boundary için)
    await api(`/assets/${assetId}/dosyalar`, { method: 'POST', body: veri });
    cihazDetay(assetId);
  } catch (e) { alert('⚠ ' + (e.detail || 'Dosya yüklenemedi')); }
}

async function dosyaAc(dosyaId) {
  try {
    const r = await fetch(url('/dosyalar/' + dosyaId),
                          { headers: { 'Authorization': `Bearer ${token}` } });
    if (!r.ok) throw await r.json().catch(() => ({ detail: 'Açılamadı' }));
    pdfAc(await r.blob());
  } catch (e) { alert('⚠ ' + (e.detail || e.message || 'Dosya açılamadı')); }
}

async function dosyaSil(dosyaId, assetId) {
  if (!confirm('Dosya silinsin mi?')) return;
  try {
    await api('/dosyalar/' + dosyaId, { method: 'DELETE' });
    cihazDetay(assetId);
  } catch (e) { alert('⚠ ' + (e.detail || 'Silinemedi')); }
}

// Kişi ekleri: imzalı zimmet formu tek cihaza değil KİŞİYE aittir
function kisiDosyaSec(kisiId, tur) {
  const girdi = document.createElement('input');
  girdi.type = 'file';
  if (tur === 'gorsel') girdi.accept = 'image/*';
  girdi.onchange = () => girdi.files[0] &&
    kisiDosyaYukle(kisiId, tur, girdi.files[0]);
  girdi.click();
}

async function kisiDosyaYukle(kisiId, tur, dosya) {
  const veri = new FormData();
  veri.append('file', dosya);
  veri.append('tur', tur);
  try {
    await api(`/users/${kisiId}/dosyalar`, { method: 'POST', body: veri });
    kisiDetay(kisiId);
  } catch (e) { alert('⚠ ' + (e.detail || 'Dosya yüklenemedi')); }
}

async function kisiDosyaAc(dosyaId) {
  try {
    const r = await fetch(url('/kisi-dosyalari/' + dosyaId),
                          { headers: { 'Authorization': `Bearer ${token}` } });
    if (!r.ok) throw await r.json().catch(() => ({ detail: 'Açılamadı' }));
    pdfAc(await r.blob());
  } catch (e) { alert('⚠ ' + (e.detail || e.message || 'Dosya açılamadı')); }
}

async function kisiDosyaSil(dosyaId, kisiId) {
  if (!confirm('Dosya silinsin mi?')) return;
  try {
    await api('/kisi-dosyalari/' + dosyaId, { method: 'DELETE' });
    kisiDetay(kisiId);
  } catch (e) { alert('⚠ ' + (e.detail || 'Silinemedi')); }
}

// ---------- Kişi detayı ----------
async function kisiDetay(id) {
  let d;
  try { d = await api('/detay/user/' + id); }
  catch (e) { return alert('⚠ ' + (e.detail || 'Detay alınamadı')); }
  const k = d.kisi;
  const kisiDosyalar = await api(`/users/${id}/dosyalar`).catch(() => []);

  const dagilim = Object.entries(d.tur_dagilimi || {})
    .map(([t, n]) => `<span class="pill">${t}: <b>${n}</b></span>`).join(' ');

  const tablo = d.cihazlar.length ? `
    <table><thead><tr><th>Cihaz NO</th><th class="gizle-mobil">Tip</th>
      <th>Marka/Model</th>
      <th class="gizle-mobil">Seri No</th><th>Durum</th>
      ${canWrite() ? '<th></th>' : ''}</tr></thead><tbody>
    ${d.cihazlar.map(c => `<tr class="tikla"
        onclick="if(!event.target.closest('button'))cihazDetay(${c.id})">
      <td><b>${c.asset_tag}</b></td>
      <td class="gizle-mobil">${esc(c.kategori)}</td>
      <td>${esc([c.marka, c.model].filter(Boolean).join(' '))}</td>
      <td class="muted gizle-mobil">${esc(c.serial)}</td>
      <td>${c.durum ? `<span class="tag">${kacir(c.durum)}</span>` : '—'}</td>
      ${canWrite() ? `<td><button class="ghost" title="İade al"
         onclick="zimmetGeriAl(${c.id}, ${id})">↩</button></td>` : ''}
      </tr>`).join('')}</tbody></table>`
    : '<div class="muted">Zimmetli cihaz yok</div>';

  modalAc(`👤 ${k.ad}`, `
    <div class="bolum"><h4>Personel</h4>${alanlar(k, [
      ['employee_num','Sicil No'],['department','Departman'],['job_title','Unvan'],
      ['sube','Şube'],['email','E-posta'],['telefon','Telefon'],
      ['lokasyon','Lokasyon'],
    ])}</div>
    <div class="stats" style="margin-top:16px">
      <div class="stat"><div class="stat-v">${d.cihaz_sayisi}</div>
        <div class="stat-l">Zimmetli cihaz</div></div>
      ${d.toplam_deger ? `<div class="stat"><div class="stat-v">${
          tl(d.toplam_deger)}</div>
        <div class="stat-l">Toplam bedel</div></div>`
        : `<div class="stat"><div class="stat-v">${
          Object.keys(d.tur_dagilimi || {}).length}</div>
        <div class="stat-l">Cihaz çeşidi</div></div>`}
    </div>
    ${dagilim ? `<div class="row" style="margin-bottom:14px">${dagilim}</div>` : ''}
    <div class="bolum">
      <div class="row" style="align-items:center; margin-bottom:8px">
        <h4 style="margin:0; flex:1">Cihazlar (${d.cihaz_sayisi})</h4>
        ${canWrite() ? `<button class="primary" onclick="zimmetPaneliAc(${id}, '${
            encodeURIComponent(k.ad || '')}')">+ Zimmet ekle</button>` : ''}
      </div>
      ${tablo}
    </div>
    <div class="bolum">
      <h4>Belgeler (${kisiDosyalar.length})</h4>
      ${kisiDosyalar.length ? `<table><tbody>
        ${kisiDosyalar.map(f => `<tr>
          <td>${TUR_ADI[f.tur] || f.tur}</td>
          <td><a href="#" onclick="kisiDosyaAc(${f.id});return false">${
            kacir(f.dosya_adi)}</a></td>
          <td class="muted">${(f.boyut / 1024).toFixed(0)} KB</td>
          <td class="muted">${f.created_at
            ? new Date(f.created_at).toLocaleDateString('tr-TR') : '—'}</td>
          ${canWrite() ? `<td><button class="ghost mini" title="Sil"
             onclick="kisiDosyaSil(${f.id}, ${id})">🗑</button></td>` : ''}
        </tr>`).join('')}</tbody></table>`
        : '<div class="muted">Yüklenmiş belge yok</div>'}
      ${canWrite() ? `<div class="row" style="margin-top:10px">
        <button class="ghost" onclick="kisiDosyaSec(${id}, 'zimmet_formu')">
          ✍️ İmzalı zimmet formu yükle</button>
        <button class="ghost" onclick="kisiDosyaSec(${id}, 'diger')">
          📎 Diğer belge</button>
      </div>` : ''}
    </div>`,
    (d.cihaz_sayisi ? `<button class="ghost" title="Zimmet fişi"
      onclick="openPdf('/documents/zimmet/user/${id}.pdf')">📄</button>` : '') +
    (canWrite() ? `<button class="ghost" onclick="kisiDuzenle(${id})">✏️ Düzenle</button>` : ''));
}

// ---------- Cihaz düzenleme ----------
function secenekler(liste, secili) {
  return '<option value="">— seçilmedi —</option>' + liste
    .slice().sort((a, b) => a.name.localeCompare(b.name, 'tr'))
    .map(x => `<option value="${x.id}"${x.id === secili ? ' selected' : ''}>
               ${x.name}</option>`).join('');
}

async function cihazDuzenle(id) {
  const [a, modeller, lokasyonlar, durumlar, tedarikciler, sirketler] =
    await Promise.all([
      api('/assets/' + id), api('/models?limit=1000'), api('/locations?limit=500'),
      api('/status-labels?limit=200'), api('/suppliers?limit=500'),
      api('/companies?limit=500'),
    ]);

  const metinAlanlar = [
    ['asset_tag','Cihaz NO','text'],['name','Ad','text'],['serial','Seri No','text'],
    ['demirbas_no','Demirbaş No','text'],['muhasebe_kodu','IFS Kodu','text'],
    ['barkod','Barkod','text'],['ip_address','IP','text'],['hostname','Hostname','text'],
    ['mac_address','MAC','text'],['imei','IMEI','text'],
    ['telefon_no','Telefon','text'],['sim_no','SIM','text'],['operator','Operatör','text'],
    ['fatura_no','Fatura No','text'],['purchase_date','Alım Tarihi','date'],
    ['warranty_end','Garanti Bitiş','date'],['purchase_cost','Bedel (TL)','number'],
    ['notes','Açıklama','text'],
  ];
  const iliskiAlanlar = [
    ['model_id','Model (tür/marka buradan gelir)', modeller],
    ['location_id','Lokasyon', lokasyonlar],
    ['status_id','Durum', durumlar],
    ['supplier_id','Tedarikçi', tedarikciler],
    ['company_id','Şirket', sirketler],
  ];

  modalAc(`✏️ ${a.asset_tag} düzenle`, `
    <div class="bolum"><h4>İlişkiler</h4><div class="alan-grid">
      ${iliskiAlanlar.map(([k, l, liste]) => `<div>
        <div class="stat-l" style="margin-bottom:3px">${l}</div>
        <select id="s_${k}" style="width:100%">${secenekler(liste, a[k])}</select>
        </div>`).join('')}
    </div></div>
    <div class="bolum"><h4>Bilgiler</h4><div class="alan-grid">
      ${metinAlanlar.map(([k, l, t]) => `<div>
        <div class="stat-l" style="margin-bottom:3px">${l}</div>
        <input id="e_${k}" type="${t}" style="width:100%"
          value="${a[k] ?? ''}" /></div>`).join('')}
    </div></div>
    <div class="row" style="margin-top:16px">
      <button class="primary" onclick="cihazKaydet(${id})">Kaydet</button>
      <button class="ghost" onclick="cihazDetay(${id})">Vazgeç</button>
    </div>
    <div id="duzInfo" class="note"></div>`);
}

async function cihazKaydet(id) {
  const govde = {};
  for (const el of document.querySelectorAll('[id^="e_"]')) {
    const k = el.id.slice(2);
    const v = el.value.trim();
    govde[k] = v === '' ? null : (el.type === 'number' ? Number(v) : v);
  }
  for (const el of document.querySelectorAll('[id^="s_"]')) {
    govde[el.id.slice(2)] = el.value ? Number(el.value) : null;
  }
  try {
    await api('/assets/' + id, { method: 'PUT',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(govde) });
    cihazDetay(id);
    if (activeTab === 'assets') loadAssets(true);
  } catch (e) {
    document.getElementById('duzInfo').innerHTML =
      `<span style="color:var(--err)">⚠ ${e.detail || 'Kaydedilemedi'}</span>`;
  }
}

// ---------- Personel düzenleme ----------
async function kisiDuzenle(id) {
  const [k, lokasyonlar] = await Promise.all([
    api('/users/' + id), api('/locations?limit=500'),
  ]);
  const alanlarListe = [
    ['first_name','Ad','text'],['last_name','Soyad','text'],
    ['employee_num','Sicil No','text'],['department','Departman','text'],
    ['job_title','Unvan','text'],['sube','Şube','text'],
    ['email','E-posta','text'],['telefon','Telefon','text'],
    ['tckn','TCKN','text'],['ise_giris','İşe Giriş','date'],
    ['username','Kullanıcı Adı (giriş için)','text'],
  ];
  modalAc(`✏️ ${k.first_name} ${k.last_name ?? ''} düzenle`, `
    <div class="alan-grid">
      ${alanlarListe.map(([a, l, t]) => `<div>
        <div class="stat-l" style="margin-bottom:3px">${l}</div>
        <input id="u_${a}" type="${t}" style="width:100%"
          value="${k[a] ?? ''}" /></div>`).join('')}
      <div><div class="stat-l" style="margin-bottom:3px">Lokasyon</div>
        <select id="ul_location_id" style="width:100%">
          ${secenekler(lokasyonlar, k.location_id)}</select></div>
    </div>
    <div class="row" style="margin-top:16px">
      <button class="primary" onclick="kisiKaydet(${id})">Kaydet</button>
      <button class="ghost" onclick="kisiDetay(${id})">Vazgeç</button>
    </div>
    <div id="kisiDuzInfo" class="note"></div>`);
}

async function kisiKaydet(id) {
  const govde = {};
  for (const el of document.querySelectorAll('[id^="u_"]')) {
    const v = el.value.trim();
    govde[el.id.slice(2)] = v === '' ? null : v;
  }
  const lok = document.getElementById('ul_location_id');
  govde.location_id = lok?.value ? Number(lok.value) : null;
  try {
    await api('/users/' + id, { method: 'PUT',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(govde) });
    kisiDetay(id);
    if (activeTab === 'personel') loadPersonel();
  } catch (e) {
    document.getElementById('kisiDuzInfo').innerHTML =
      `<span style="color:var(--err)">⚠ ${e.detail || 'Kaydedilemedi'}</span>`;
  }
}

// ---------- Varlıklar ----------
function renderAssetsView() {
  document.getElementById('view').innerHTML =
    sayfaBasligi('💻', 'Varlıklar', 'Tüm cihazlar — filtreleyin, zimmetleyin, düzenleyin') + `
    <div class="panel">
      <h2>Barkod / QR okut</h2>
      <div class="row">
        <input id="scan" class="grow" placeholder="Barkod okuyucuyla okutun veya kodu yazıp Enter'a basın"
               onkeydown="if(event.key==='Enter')scanCode()" />
        <button class="primary" onclick="scanCode()">Bul</button>
        <button class="ghost" onclick="printLabels()">Etiket bas (tümü)</button>
      </div>
      <div id="scanInfo" class="note"></div>
    </div>
    <div class="panel">
      <h2>Doğal dil arama</h2>
      <div class="row">
        <input id="q" class="grow" placeholder="örn: depodaki boştaki Dell laptoplar"
               onkeydown="if(event.key==='Enter')doSearch()" />
        <button class="primary" onclick="doSearch()">Ara</button>
        <button class="ghost" onclick="loadAssets()">Tümünü göster</button>
        <a class="pill" href="#" onclick="downloadCsv(event)">CSV indir</a>
      </div>
      <div id="searchInfo" class="note"></div>
    </div>
    ${canWrite() ? `<div class="panel">
      <h2>Hızlı varlık ekle</h2>
      <div class="row">
        <input id="newTag" placeholder="Etiket (örn. BT-0001)" />
        <input id="newName" class="grow" placeholder="Ad" />
        <input id="newSerial" placeholder="Seri no" />
        <input id="newDemirbas" placeholder="Demirbaş no" />
        <input id="newBarkod" placeholder="Barkod" />
        <button class="primary" onclick="addAsset()">Ekle</button>
      </div>
      <div id="addInfo" class="note"></div>
    </div>` : ''}
    <div class="panel">
      <h2>Filtreler</h2>
      <div class="row">
        <select id="fProje" onchange="loadAssets()"><option value="">Tüm projeler</option></select>
        <select id="fKategori" onchange="loadAssets()"><option value="">Tüm türler</option></select>
        <select id="fLokasyon" onchange="loadAssets()"><option value="">Tüm lokasyonlar</option></select>
        <select id="fMarka" onchange="loadAssets()"><option value="">Tüm markalar</option></select>
        <select id="fDurum" onchange="loadAssets()"><option value="">Tüm durumlar</option></select>
        <select id="fZimmet" onchange="loadAssets()">
          <option value="">Zimmet: hepsi</option>
          <option value="true">Sadece zimmetli</option>
          <option value="false">Sadece boşta</option>
        </select>
        <input id="fAra" class="grow"
               placeholder="Etiket / seri / demirbaş / kişi / şantiye ara…"
               oninput="gecikmeliAra()" />
        <button class="ghost" onclick="filtreTemizle()">Temizle</button>
      </div>
      <div id="filtreBilgi" class="note"></div>
    </div>
    <div class="panel">
      <h2>Varlıklar (<span id="count">0</span><span id="toplamBilgi"></span>)</h2>
      <table><thead><tr><th>Etiket</th><th class="gizle-mobil">Demirbaş</th>
        <th>Ad</th><th class="gizle-mobil">Tür</th>
        <th>Lokasyon</th><th class="gizle-mobil">Seri</th>
        <th>Zimmet</th><th></th></tr></thead>
      <tbody id="rows"></tbody></table>
      <div id="dahaFazla" class="row" style="margin-top:12px"></div>
    </div>`;
  filtreSecenekleriDoldur();
  loadAssets();
}

// Filtre açılır listelerini referans tablolardan doldur
let refKategori = {}, refLokasyon = {}, refMarka = {}, refModelKat = {};
async function filtreSecenekleriDoldur() {
  const [kat, lok, mar, dur] = await Promise.all([
    api('/categories?limit=500'), api('/locations?limit=500'),
    api('/manufacturers?limit=500'), api('/status-labels?limit=200'),
  ]);
  refKategori = Object.fromEntries(kat.map(x => [x.id, x.name]));
  refLokasyon = Object.fromEntries(lok.map(x => [x.id, x.name]));
  refMarka = Object.fromEntries(mar.map(x => [x.id, x.name]));
  const doldur = (id, liste, bos) => {
    const el = document.getElementById(id);
    if (!el) return;
    const secili = el.value;
    el.innerHTML = `<option value="">${bos}</option>` + liste
      .slice().sort((a, b) => a.name.localeCompare(b.name, 'tr'))
      .map(x => `<option value="${x.id}">${x.name}</option>`).join('');
    el.value = secili;
  };
  // Proje kodları ayrı uçtan gelir (cihaz sayısıyla birlikte)
  const projeler = await api('/assets/proje-kodlari').catch(() => []);
  const pEl = document.getElementById('fProje');
  if (pEl) {
    const secili = pEl.value;
    pEl.innerHTML = '<option value="">Tüm projeler</option>' + projeler
      .map(x => `<option value="${x.proje_kodu}">${x.proje_kodu}` +
                ` (${x.cihaz_sayisi})</option>`).join('');
    pEl.value = secili;
  }
  doldur('fKategori', kat, 'Tüm türler');
  doldur('fLokasyon', lok, 'Tüm lokasyonlar');
  doldur('fMarka', mar, 'Tüm markalar');
  doldur('fDurum', dur, 'Tüm durumlar');
  // Seçenekler hazır; hızlı aramadan gelen filtre isteği varsa şimdi uygula
  bekleyenFiltreyiUygula();
  // Model -> kategori/marka eşlemesi (listede tür göstermek için)
  const modeller = await api('/models?limit=1000');
  refModelKat = Object.fromEntries(modeller.map(m => [m.id, m]));
}

let araZaman = null;
function gecikmeliAra() {
  clearTimeout(araZaman);
  araZaman = setTimeout(loadAssets, 350);
}

function filtreleriSifirla() {
  ['fProje','fKategori','fLokasyon','fMarka','fDurum','fZimmet','fAra']
    .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
}

function filtreTemizle() {
  filtreleriSifirla();
  loadAssets();
}

function filtreSorgusu() {
  const p = new URLSearchParams();
  const ekle = (id, ad) => {
    const v = document.getElementById(id)?.value;
    if (v) p.set(ad, v);
  };
  ekle('fProje', 'proje_kodu');
  ekle('fKategori', 'category_id');
  ekle('fLokasyon', 'location_id');
  ekle('fMarka', 'manufacturer_id');
  ekle('fDurum', 'status_id');
  ekle('fZimmet', 'assigned');
  ekle('fAra', 'q');
  return p;
}

function renderAssets(assets) {
  document.getElementById('count').textContent = assets.length;
  document.getElementById('rows').innerHTML = assets.map(a => {
    const assigned = a.assigned_type
      ? `<span class="tag used">zimmetli</span>` : `<span class="tag free">boşta</span>`;
    let btn = '';
    if (canWrite()) btn = a.assigned_type
      ? `<button class="ghost" onclick="checkin(${a.id})">İade al</button>`
      : `<button class="ghost" onclick="checkoutPrompt(${a.id}, '${
          encodeURIComponent(a.asset_tag)}')">Zimmetle</button>`;
    if (a.assigned_type === 'user')
      btn += ` <button class="ghost" title="Zimmet fişi (PDF)"
                 onclick="openPdf('/documents/zimmet/asset/${a.id}.pdf')">📄</button>`;
    btn += ` <button class="ghost" title="Etiket bas (QR + barkod)"
               onclick="openPdf('/documents/etiket/asset/${a.id}.pdf')">🏷️</button>`;
    const mdl = refModelKat[a.model_id];
    const tur = mdl ? refKategori[mdl.category_id] : null;
    return `<tr class="tikla" onclick="if(!event.target.closest('button'))cihazDetay(${a.id})">
      <td><b>${a.asset_tag}</b></td>
      <td class="muted gizle-mobil">${esc(a.demirbas_no)}</td>
      <td>${esc(a.name)}</td><td class="gizle-mobil">${esc(tur)}</td>
      <td class="muted">${esc(refLokasyon[a.location_id])}</td>
      <td class="muted">${esc(a.serial)}</td>
      <td>${assigned}</td><td>${btn}</td></tr>`;
  }).join('');
}

let gosterilenSayi = 200;

async function loadAssets(devam = false) {
  const info = document.getElementById('searchInfo'); if (info) info.textContent = '';
  if (!devam) gosterilenSayi = 200;
  const p = filtreSorgusu();
  p.set('limit', gosterilenSayi);
  const [liste, sayi] = await Promise.all([
    api('/assets?' + p.toString()),
    api('/assets/sayi?' + filtreSorgusu().toString()).catch(() => null),
  ]);
  renderAssets(liste);

  const bilgi = document.getElementById('filtreBilgi');
  const etiketler = [];
  const ekle = (id, on) => {
    const el = document.getElementById(id);
    if (el?.value) etiketler.push(`${on}: ${el.selectedOptions?.[0]?.text ?? el.value}`);
  };
  ekle('fProje', 'Proje'); ekle('fKategori', 'Tür'); ekle('fLokasyon', 'Lokasyon');
  ekle('fMarka', 'Marka'); ekle('fDurum', 'Durum');
  ekle('fZimmet', 'Zimmet'); ekle('fAra', 'Arama');
  if (bilgi) bilgi.innerHTML = etiketler.length
    ? etiketler.map(e => `<span class="pill">${e}</span>`).join(' ')
    : '<span class="muted">Filtre yok — tüm kayıtlar</span>';

  const toplam = sayi?.toplam;
  const bilgiEl = document.getElementById('toplamBilgi');
  if (bilgiEl && toplam != null && toplam > liste.length)
    bilgiEl.textContent = ` / ${toplam}`;
  else if (bilgiEl) bilgiEl.textContent = '';

  const daha = document.getElementById('dahaFazla');
  if (daha) daha.innerHTML = (toplam != null && liste.length < toplam)
    ? `<button class="ghost" onclick="dahaGoster()">↓ Daha fazla göster
         (${liste.length}/${toplam})</button>` : '';
}

function dahaGoster() { gosterilenSayi += 300; loadAssets(true); }

async function doSearch() {
  const q = document.getElementById('q').value.trim();
  if (!q) return loadAssets();
  const res = await api('/search', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ q }) });
  const f = res.interpreted_filter;
  const used = res.used_ai ? '🤖 Claude yorumladı' : '🔤 metin araması';
  const parts = Object.entries(f).filter(([k, v]) => v !== null && v !== false && k !== 'limit')
    .map(([k, v]) => `${k}=${v}`);
  document.getElementById('searchInfo').innerHTML =
    `${used} · <span class="pill">${parts.join(' · ') || 'filtre yok'}</span> · ${res.count} sonuç`;
  renderAssets(res.results);
}

async function addAsset() {
  const body = { asset_tag: newTag.value.trim(), name: newName.value.trim() || null,
                 serial: newSerial.value.trim() || null,
                 demirbas_no: newDemirbas.value.trim() || null,
                 barkod: newBarkod.value.trim() || null };
  if (!body.asset_tag) { addInfo.textContent = 'Etiket zorunlu.'; return; }
  try {
    await api('/assets', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body) });
    addInfo.textContent = '✓ Eklendi.'; loadAssets();
  } catch (e) { addInfo.textContent = '⚠ ' + (e.detail || 'Hata'); }
}

// ---------- Zimmetleme: kişi seçme penceresi ----------
// Kimse kullanıcı kimliğini ezbere bilmez; kişi ada göre aranıp seçilir.
let zimmetCihaz = null;      // {id, etiket}
let zimmetSonra = null;      // işlem bitince çağrılacak tazeleme
let kisiAraZaman = null;

async function checkoutPrompt(id, etiketKodlu = '', sonra = null) {
  const etiket = decodeURIComponent(etiketKodlu);
  zimmetCihaz = { id, etiket };
  zimmetSonra = sonra || (() => loadAssets());
  modalAc(`Zimmetle${etiket ? ' — ' + kacir(etiket) : ''}`, `
    <div class="row">
      <input id="zkAra" class="grow" autocomplete="off"
             placeholder="Personel ara: ad soyad, sicil no, departman…"
             oninput="kisiAraGecikmeli()" />
      ${canWrite() ? `<button class="ghost" onclick="zimmetYeniPersonel()">
         + Yeni personel</button>` : ''}
    </div>
    <div id="zkSonuc" class="note">Yükleniyor…</div>
    <div class="bolum">
      <h4>Kişi yerine yere zimmetle</h4>
      <div class="row">
        <select id="zkLokasyon" class="grow"><option value="">— lokasyon seç —</option></select>
        <button class="ghost" onclick="zimmetLokasyona()">Lokasyona zimmetle</button>
      </div>
    </div>`);
  setTimeout(() => document.getElementById('zkAra')?.focus(), 60);
  kisiAra();
  // Lokasyon listesini doldur
  api('/locations?limit=500').then(lok => {
    const el = document.getElementById('zkLokasyon');
    if (!el) return;
    el.innerHTML = '<option value="">— lokasyon seç —</option>' + lok
      .slice().sort((a, b) => a.name.localeCompare(b.name, 'tr'))
      .map(l => `<option value="${l.id}">${kacir(l.name)}${
        l.proje_kodu ? ' (' + kacir(l.proje_kodu) + ')' : ''}</option>`).join('');
  }).catch(() => {});
}

function kisiAraGecikmeli() {
  clearTimeout(kisiAraZaman);
  kisiAraZaman = setTimeout(kisiAra, 180);
}

async function kisiAra() {
  const kutu = document.getElementById('zkSonuc');
  if (!kutu) return;
  const q = document.getElementById('zkAra')?.value.trim() || '';
  let liste;
  try { liste = await api('/users/ara?limit=15&q=' + encodeURIComponent(q)); }
  catch { kutu.textContent = 'Personel listesi alınamadı.'; return; }

  if (!liste.length) {
    kutu.innerHTML = `<div class="muted">Eşleşen personel yok.
      ${canWrite() ? '“+ Yeni personel” ile ekleyebilirsin.' : ''}</div>`;
    return;
  }
  kutu.innerHTML = `<div class="muted" style="margin-bottom:6px">
      ${q ? 'Sonuçlar' : 'En çok cihaz taşıyanlar'} — seçmek için tıkla</div>
    <table><tbody>${liste.map(k => `
      <tr class="tikla" onclick="zimmetKisiye(${k.id})">
        <td><b>👤 ${kacir(k.ad)}</b></td>
        <td class="muted">${esc(k.employee_num)}</td>
        <td class="muted">${esc(k.department || k.sube)}</td>
        <td class="muted">${k.cihaz_sayisi} cihaz</td>
        <td><button class="primary">Seç</button></td>
      </tr>`).join('')}</tbody></table>`;
}

async function zimmetKisiye(kisiId) {
  await zimmetVerGenel('user', kisiId);
}

async function zimmetLokasyona() {
  const el = document.getElementById('zkLokasyon');
  if (!el?.value) return alert('⚠ Önce bir lokasyon seç.');
  await zimmetVerGenel('location', Number(el.value));
}

async function zimmetVerGenel(tur, hedefId) {
  if (!zimmetCihaz) return;
  try {
    await api(`/assets/${zimmetCihaz.id}/checkout`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assigned_type: tur, assigned_id: hedefId }),
    });
    modalKapat();
    zimmetSonra?.();
  } catch (e) { alert('⚠ ' + (e.detail || 'Zimmet verilemedi')); }
}

// Aranan kişi kayıtlı değilse pencereden çıkmadan ekle.
// Arama kutusuna yazılan metin ad/soyad olarak hazır gelir.
function zimmetYeniPersonel() {
  const tam = (document.getElementById('zkAra')?.value || '').trim();
  const parca = tam.split(/\s+/).filter(Boolean);
  const kutu = document.getElementById('zkSonuc');
  if (!kutu) return;
  kutu.innerHTML = `
    <div class="bolum"><h4>Yeni personel</h4>
    <div class="form-grid">
      <label>Ad <input id="ypAd" value="${kacir(parca[0] || '')}" /></label>
      <label>Soyad <input id="ypSoyad"
             value="${kacir(parca.slice(1).join(' '))}" /></label>
      <label>Sicil No <input id="ypSicil" /></label>
      <label>Departman <input id="ypDepartman" /></label>
    </div>
    <div class="row" style="margin-top:12px">
      <button class="primary" onclick="yeniPersonelKaydet()">
        Ekle ve zimmetle</button>
      <button class="ghost" onclick="kisiAra()">Vazgeç</button>
    </div></div>`;
  setTimeout(() => document.getElementById('ypAd')?.focus(), 60);
}

async function yeniPersonelKaydet() {
  const ad = document.getElementById('ypAd').value.trim();
  if (!ad) return alert('⚠ Ad zorunlu.');
  try {
    const k = await api('/users', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        first_name: ad,
        last_name: document.getElementById('ypSoyad').value.trim() || null,
        employee_num: document.getElementById('ypSicil').value.trim() || null,
        department: document.getElementById('ypDepartman').value.trim() || null,
      }),
    });
    await zimmetKisiye(k.id);       // eklenen kişiye hemen zimmetle
  } catch (e) { alert('⚠ ' + (e.detail || 'Personel eklenemedi')); }
}

// Detay penceresinden iade — pencere açık kalsın, içerik tazelensin
async function cihazIadeAl(id) {
  try {
    await api(`/assets/${id}/checkin`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: '{}' });
    cihazDetay(id);
  } catch (e) { alert('⚠ ' + (e.detail || 'İade alınamadı')); }
}

async function checkin(id) {
  try {
    await api(`/assets/${id}/checkin`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: '{}' });
    loadAssets();
  } catch (e) { alert('⚠ ' + (e.detail || 'Hata')); }
}

// Barkod/QR okutma — okuyucular genelde kodu yazıp Enter gönderir
async function scanCode() {
  const el = document.getElementById('scan');
  const kod = el.value.trim();
  const info = document.getElementById('scanInfo');
  if (!kod) return;
  try {
    const a = await api('/documents/tara?kod=' + encodeURIComponent(kod));
    info.innerHTML = `✓ <b>${a.asset_tag}</b> — ${a.name ?? ''} ` +
      `<span class="pill">${a.assigned_type ? 'zimmetli' : 'boşta'}</span>`;
    renderAssets([a]);
    document.getElementById('count').textContent = 1;
  } catch (e) {
    info.innerHTML = `<span style="color:var(--err)">⚠ ${e.detail || 'Bulunamadı'}</span>`;
  }
  el.value = ''; el.focus();
}

// Listedeki tüm varlıklar için etiket sayfası
async function printLabels() {
  const assets = await api('/assets?limit=500');
  if (!assets.length) return alert('Etiket basılacak varlık yok.');
  try {
    const r = await fetch(url('/documents/etiketler.pdf'), {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_ids: assets.map(a => a.id) })
    });
    if (!r.ok) throw await r.json().catch(() => ({ detail: 'Hata' }));
    pdfAc(await r.blob());
  } catch (e) { alert('⚠ ' + (e.detail || e.message || 'Etiket üretilemedi')); }
}

// PDF blob'unu yeni sekmede gösterir. DİKKAT: buradaki değişken adı asla
// `url` olmamalı — global url() yardımcısını gölgeler ve aynı fonksiyondaki
// önceki url(...) çağrısı temporal dead zone'a düşüp ReferenceError atar.
function pdfAc(blob) {
  const baglanti = URL.createObjectURL(blob);
  const sekme = window.open(baglanti, '_blank');
  if (!sekme) {           // açılır pencere engellendiyse indirmeye düş
    const a = document.createElement('a');
    a.href = baglanti; a.download = 'belge.pdf'; a.click();
  }
  setTimeout(() => URL.revokeObjectURL(baglanti), 60000);
}

// Korumalı PDF uçlarını token ile açar (yeni sekmede gösterir)
async function openPdf(path) {
  try {
    const r = await fetch(url(path), { headers: { 'Authorization': `Bearer ${token}` } });
    if (!r.ok) throw await r.json().catch(() => ({ detail: 'Hata' }));
    pdfAc(await r.blob());
  } catch (e) { alert('⚠ ' + (e.detail || e.message || 'PDF açılamadı')); }
}

async function downloadCsv(ev) {
  ev.preventDefault();
  const blob = await (await fetch(url('/io/assets.csv'),
    { headers: { 'Authorization': `Bearer ${token}` } })).blob();
  const baglanti = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = baglanti; a.download = 'varliklar.csv'; a.click();
  URL.revokeObjectURL(baglanti);
}

// ---------- Adet bazlı türler (genel) ----------
function renderStockView(tab) {
  const cfg = STOCK[tab];
  const head = cfg.cols.map(([, l]) => `<th>${l}</th>`).join('') +
    (canWrite() ? '<th></th>' : '');
  const addForm = canWrite() ? `<div class="panel">
    <h2>${cfg.label} — hızlı ekle</h2>
    <div class="row">
      ${cfg.add.map(([k, l, t]) =>
        `<input id="f_${k}" type="${t}" placeholder="${l}" class="${k === 'name' ? 'grow' : ''}" />`).join('')}
      <button class="primary" onclick="addStock('${tab}')">Ekle</button>
    </div>
    <div id="stockInfo" class="note"></div>
  </div>` : '';
  document.getElementById('view').innerHTML =
    sayfaBasligi(cfg.ikon || '📦', cfg.label, cfg.alt || '') + `${addForm}
    <div class="panel">
      <h2>${cfg.label} (<span id="scount">0</span>)</h2>
      <table><thead><tr>${head}</tr></thead><tbody id="srows"></tbody></table>
    </div>`;
  loadStock(tab);
}

async function loadStock(tab) {
  const cfg = STOCK[tab];
  const items = await api(cfg.endpoint + '?limit=500');
  document.getElementById('scount').textContent = items.length;
  document.getElementById('srows').innerHTML = items.map(it => {
    const low = cfg.lowStock && it.min_qty != null && it.qty != null && it.qty <= it.min_qty;
    const cells = cfg.cols.map(([k]) => {
      let v = esc(it[k]);
      if (k === 'qty' && low) v = `${it[k]} <span class="tag low">düşük stok</span>`;
      return `<td>${v}</td>`;
    }).join('');
    return `<tr class="tikla" onclick="stokDetay('${tab}', ${it.id})">${cells}</tr>`;
  }).join('');
}

async function addStock(tab) {
  const cfg = STOCK[tab];
  const body = {};
  for (const [k, , t] of cfg.add) {
    const el = document.getElementById('f_' + k);
    let v = el.value.trim();
    if (v === '') continue;
    body[k] = t === 'number' ? Number(v) : v;
  }
  if (!body.name) { stockInfo.textContent = 'Ad zorunlu.'; return; }
  try {
    await api(cfg.endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body) });
    stockInfo.textContent = '✓ Eklendi.'; loadStock(tab);
  } catch (e) { stockInfo.textContent = '⚠ ' + (e.detail || 'Hata'); }
}

// ---------- Raporlar ----------
function renderRaporlarView() {
  const RAPORLAR = [
    ['genel', '📗', 'Genel rapor',
     'Hepsi tek kitapta: Özet + aşağıdaki tüm sayfalar', 'primary'],
    ['cihazlar', '💻', 'Cihaz listesi',
     'Tüm varlıklar, tam künye — marka, model, seri, lokasyon, durum, bedel'],
    ['zimmet', '🤝', 'Zimmet raporu',
     'Yalnızca zimmetli cihazlar + sicil, departman, unvan, zimmet tarihi'],
    ['lokasyon', '🏗️', 'Lokasyon raporu',
     'Şantiye başına cihaz / zimmetli / boşta sayıları'],
    ['stok', '📦', 'Stok raporu',
     'Aksesuar, sarf, bileşen, lisans — azalanlar "DÜŞÜK" işaretli'],
    ['sistem', '🌐', 'Sistem ürünleri',
     'Ağ, yangın, alarm, geçiş, kantar — teknik özellikler tek sütunda'],
  ];
  document.getElementById('view').innerHTML =
    sayfaBasligi('📈', 'Raporlar',
      'Başlıklı, süzgeçli, yazdırmaya hazır Excel dosyaları — tek tıkla iner') + `
    <div class="kisayollar">
      ${RAPORLAR.map(([tip, ikon, ad, alt, birincil]) => `
        <button class="kisayol${birincil ? ' onemli' : ''}"
                onclick="indirDosya('/reports/excel?tip=${tip}')">
          <span class="ikon">${ikon}</span><b>${ad}</b>
          <small>${alt}</small>
        </button>`).join('')}
    </div>
    <div class="panel">
      <h2>Dosya düzeni</h2>
      <div class="note" style="margin-top:0">
        Her sayfada kurum başlığı ve tarih bulunur; üst satır sabitlenmiştir,
        sütunlarda süzgeç okları açıktır. Tarihler GG.AA.YYYY, tutarlar ₺
        biçimindedir. Dosya adı raporun adını ve günün tarihini taşır —
        örn. <b>"Zimmet Raporu ${new Date().toLocaleDateString('tr-TR')}.xlsx"</b>.
      </div>
    </div>`;
}

// ---------- Stok kaydı detayı: bilgiler + dosya ekleri ----------
async function stokDetay(tab, id) {
  const cfg = STOCK[tab];
  let kayit, dosyalar;
  try {
    [kayit, dosyalar] = await Promise.all([
      api(`${cfg.endpoint}/${id}`),
      api(`/stok/${cfg.kayitTuru}/${id}/dosyalar`).catch(() => []),
    ]);
  } catch (e) { return alert('⚠ ' + (e.detail || 'Kayıt alınamadı')); }

  const gorseller = dosyalar.filter(f => f.tur === 'gorsel');
  const belgeler = dosyalar.filter(f => f.tur !== 'gorsel');
  const yaz = canWrite();

  modalAc(`${cfg.ikon} ${kacir(kayit.name)}`, `
    <div class="bolum"><h4>${kacir(cfg.label)}</h4>${alanlar(kayit,
      cfg.cols.filter(([k]) => k !== 'name'))}</div>
    <div class="bolum">
      <h4>Görseller ve Belgeler</h4>
      ${gorseller.length ? `<div class="gorsel-serit">
        ${gorseller.map(f => `<figure>
          <img data-stok-dosya="${f.id}" alt="${kacir(f.dosya_adi)}"
               onclick="stokDosyaAc(${f.id})" title="Büyüt" />
          ${yaz ? `<button class="ghost mini" title="Sil"
             onclick="stokDosyaSil(${f.id}, '${tab}', ${id})">🗑</button>` : ''}
        </figure>`).join('')}</div>` : ''}
      ${belgeler.length ? `<table><tbody>
        ${belgeler.map(f => `<tr>
          <td>${TUR_ADI[f.tur] || f.tur}</td>
          <td><a href="#" onclick="stokDosyaAc(${f.id});return false">${
            kacir(f.dosya_adi)}</a></td>
          <td class="muted">${(f.boyut / 1024).toFixed(0)} KB</td>
          ${yaz ? `<td><button class="ghost mini" title="Sil"
             onclick="stokDosyaSil(${f.id}, '${tab}', ${id})">🗑</button></td>` : ''}
        </tr>`).join('')}</tbody></table>` : ''}
      ${!dosyalar.length ? '<div class="muted">Yüklenmiş dosya yok</div>' : ''}
      ${yaz ? `<div class="row" style="margin-top:10px">
        <button class="ghost" onclick="stokDosyaSec('${tab}', ${id}, 'gorsel')">
          📷 Ürün görseli</button>
        <button class="ghost" onclick="stokDosyaSec('${tab}', ${id}, 'fatura')">
          🧾 Fatura</button>
        <button class="ghost" onclick="stokDosyaSec('${tab}', ${id}, 'diger')">
          📎 Diğer belge</button>
      </div>` : ''}
    </div>`);
  stokGorselleriYukle();
}

// Görsel ucu Authorization ister; <img src> başlık gönderemez
async function stokGorselleriYukle() {
  for (const el of document.querySelectorAll('[data-stok-dosya]')) {
    try {
      const r = await fetch(url('/stok/dosyalari/' + el.dataset.stokDosya),
                            { headers: { 'Authorization': `Bearer ${token}` } });
      if (r.ok) el.src = URL.createObjectURL(await r.blob());
    } catch { /* görsel yüklenemezse boş kalsın */ }
  }
}

function stokDosyaSec(tab, id, tur) {
  const girdi = document.createElement('input');
  girdi.type = 'file';
  if (tur === 'gorsel') girdi.accept = 'image/*';
  girdi.onchange = () => girdi.files[0] &&
    stokDosyaYukle(tab, id, tur, girdi.files[0]);
  girdi.click();
}

async function stokDosyaYukle(tab, id, tur, dosya) {
  const veri = new FormData();
  veri.append('file', dosya);
  veri.append('tur', tur);
  try {
    await api(`/stok/${STOCK[tab].kayitTuru}/${id}/dosyalar`,
              { method: 'POST', body: veri });
    stokDetay(tab, id);
  } catch (e) { alert('⚠ ' + (e.detail || 'Dosya yüklenemedi')); }
}

async function stokDosyaAc(dosyaId) {
  try {
    const r = await fetch(url('/stok/dosyalari/' + dosyaId),
                          { headers: { 'Authorization': `Bearer ${token}` } });
    if (!r.ok) throw await r.json().catch(() => ({ detail: 'Açılamadı' }));
    pdfAc(await r.blob());
  } catch (e) { alert('⚠ ' + (e.detail || e.message || 'Dosya açılamadı')); }
}

async function stokDosyaSil(dosyaId, tab, id) {
  if (!confirm('Dosya silinsin mi?')) return;
  try {
    await api('/stok/dosyalari/' + dosyaId, { method: 'DELETE' });
    stokDetay(tab, id);
  } catch (e) { alert('⚠ ' + (e.detail || 'Silinemedi')); }
}

// ---------- Ayarlar: profil, parola, hesap yönetimi ----------
let ayarBolum = 'profil';

function renderAyarlarView() {
  const sekmeler = [['profil', '👤 Profilim'], ['parola', '🔒 Parola']];
  if (me.role === 'admin') {
    sekmeler.push(['hesaplar', '🛡️ Kullanıcı hesapları']);
    sekmeler.push(['yedek', '💾 Yedekleme']);
  }

  document.getElementById('view').innerHTML =
    sayfaBasligi('⚙️', 'Ayarlar', 'Hesabınızı ve kullanıcı yetkilerini yönetin') + `
    <div class="panel">
      <div class="row">${sekmeler.map(([k, l]) =>
        `<button class="ghost ${k === ayarBolum ? 'sec' : ''}"
           onclick="ayarSec('${k}')">${l}</button>`).join('')}</div>
    </div>
    <div id="ayarIcerik"></div>`;
  ayarIcerikCiz();
}

function ayarSec(bolum) { ayarBolum = bolum; renderAyarlarView(); }

function ayarIcerikCiz() {
  if (ayarBolum === 'profil') return ayarProfil();
  if (ayarBolum === 'parola') return ayarParola();
  if (ayarBolum === 'yedek') return ayarYedek();   // mesajsız
  return ayarHesaplar();
}

function ayarProfil() {
  document.getElementById('ayarIcerik').innerHTML = `
    <div class="panel">
      <h2>Kişisel bilgiler</h2>
      <div class="form-grid">
        <label>Ad <input id="pfAd" value="${kacir(me.first_name || '')}" /></label>
        <label>Soyad <input id="pfSoyad" value="${kacir(me.last_name || '')}" /></label>
        <label>E-posta <input id="pfMail" type="email"
               value="${kacir(me.email || '')}" /></label>
        <label>Telefon <input id="pfTel" value="${kacir(me.telefon || '')}" /></label>
      </div>
      <div class="row" style="margin-top:14px">
        <button class="primary" onclick="profilKaydet()">Kaydet</button>
        <span id="pfBilgi" class="note"></span>
      </div>
    </div>
    <div class="panel">
      <h2>Hesap</h2>
      <div class="alan-grid">
        <div class="alan"><span class="et">Kullanıcı adı</span>
          <span class="dg">${esc(me.username)}</span></div>
        <div class="alan"><span class="et">Yetki</span>
          <span class="dg"><span class="tag role">${ROL_ADI[me.role] || me.role}</span></span></div>
        <div class="alan"><span class="et">Departman</span>
          <span class="dg">${esc(me.department)}</span></div>
      </div>
      <div class="note">Kullanıcı adı ve yetki yalnızca yönetici tarafından
        değiştirilebilir.</div>
    </div>`;
}

async function profilKaydet() {
  const bilgi = document.getElementById('pfBilgi');
  try {
    me = await api('/auth/me', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        first_name: document.getElementById('pfAd').value.trim(),
        last_name: document.getElementById('pfSoyad').value.trim() || null,
        email: document.getElementById('pfMail').value.trim() || null,
        telefon: document.getElementById('pfTel').value.trim() || null,
      }),
    });
    localStorage.setItem('me', JSON.stringify(me));
    bilgi.innerHTML = '<span style="color:var(--ok)">✓ Kaydedildi.</span>';
    // Menüdeki ve üst bardaki ad da güncellensin
    const ad = [me.first_name, me.last_name].filter(Boolean).join(' ');
    for (const id of ['yanAd', 'ustAd']) document.getElementById(id).textContent = ad;
    for (const id of ['yanAvatar', 'ustAvatar'])
      document.getElementById(id).textContent = bashharfler(ad);
  } catch (e) {
    bilgi.innerHTML = `<span style="color:var(--err)">⚠ ${e.detail || 'Kaydedilemedi'}</span>`;
  }
}

function ayarParola() {
  document.getElementById('ayarIcerik').innerHTML = `
    <div class="panel">
      <h2>Parola değiştir</h2>
      <div class="form-grid">
        <label>Mevcut parola
          <input id="paEski" type="password" autocomplete="current-password" /></label>
        <label>Yeni parola (en az 8 karakter)
          <input id="paYeni" type="password" autocomplete="new-password" /></label>
        <label>Yeni parola (tekrar)
          <input id="paYeni2" type="password" autocomplete="new-password" /></label>
      </div>
      <div class="row" style="margin-top:14px">
        <button class="primary" onclick="parolaKaydet()">Parolayı değiştir</button>
        <span id="paBilgi" class="note"></span>
      </div>
    </div>`;
}

async function parolaKaydet() {
  const bilgi = document.getElementById('paBilgi');
  const yeni = document.getElementById('paYeni').value;
  if (yeni !== document.getElementById('paYeni2').value) {
    bilgi.innerHTML = '<span style="color:var(--err)">⚠ Yeni parolalar aynı değil.</span>';
    return;
  }
  if (yeni.length < 8) {
    bilgi.innerHTML = '<span style="color:var(--err)">⚠ Parola en az 8 karakter olmalı.</span>';
    return;
  }
  try {
    await api('/auth/parola', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mevcut_parola: document.getElementById('paEski').value,
        yeni_parola: yeni,
      }),
    });
    bilgi.innerHTML = '<span style="color:var(--ok)">✓ Parola değiştirildi.</span>';
    ['paEski', 'paYeni', 'paYeni2'].forEach(i =>
      document.getElementById(i).value = '');
  } catch (e) {
    bilgi.innerHTML = `<span style="color:var(--err)">⚠ ${e.detail || 'Değiştirilemedi'}</span>`;
  }
}

async function ayarHesaplar() {
  const kutu = document.getElementById('ayarIcerik');
  kutu.innerHTML = '<div class="panel"><h2>Kullanıcı hesapları</h2>Yükleniyor…</div>';
  let liste;
  try { liste = await api('/users/hesaplar'); }
  catch (e) {
    kutu.innerHTML = `<div class="panel">⚠ ${e.detail || 'Alınamadı'}</div>`;
    return;
  }
  kutu.innerHTML = `
    <div class="panel">
      <div class="row" style="align-items:center; margin-bottom:12px">
        <h2 style="margin:0; flex:1">Kullanıcı hesapları (${liste.length})</h2>
        <button class="primary" onclick="hesapAc()">+ Kullanıcı ekle</button>
      </div>
      <table><thead><tr>
        <th>Kullanıcı adı</th><th>Ad Soyad</th><th>E-posta</th>
        <th>Yetki</th><th>Durum</th><th></th></tr></thead><tbody>
      ${liste.map(h => `<tr>
        <td><b>${esc(h.username)}</b></td>
        <td>${kacir([h.first_name, h.last_name].filter(Boolean).join(' '))}</td>
        <td class="muted">${esc(h.email)}</td>
        <td>
          <select data-onceki="${h.role}"
                  onchange="rolDegistir(${h.id}, this.value, this)"
                  ${h.id === me.id ? 'disabled title="Kendi yetkinizi buradan değiştiremezsiniz"' : ''}>
            <option value="viewer"${h.role === 'viewer' ? ' selected' : ''}>Görüntüleyici</option>
            <option value="editor"${h.role === 'editor' ? ' selected' : ''}>Düzenleyici</option>
            <option value="admin"${h.role === 'admin' ? ' selected' : ''}>Yönetici</option>
          </select>
        </td>
        <td>${h.active
              ? (h.girebilir ? '<span class="tag free">etkin</span>'
                             : '<span class="tag used">parolasız</span>')
              : '<span class="tag used">kapalı</span>'}</td>
        <td><button class="ghost mini"
              onclick="hesapDuzenle(${h.id})">✏️ Düzenle</button></td>
      </tr>`).join('')}</tbody></table>
      <div class="note">Yetkiyi listeden doğrudan değiştirebilirsiniz —
        birini <b>yönetici</b> yapmak için yetki kutusundan “Yönetici”yi seçin.</div>
      <div class="note">
        <b>Yönetici</b>: her şey + kullanıcı yönetimi ve yedekleme ·
        <b>Düzenleyici</b>: kayıt ekler/değiştirir, zimmet verir ·
        <b>Görüntüleyici</b>: yalnızca okur.</div>
    </div>`;
}

// Listeden tek adımda yetki değiştirme (yönetici yapma dahil)
async function rolDegistir(kisiId, rol, secim) {
  // Önceki değer data-onceki'de duruyor: onchange tetiklendiğinde
  // selectedIndex zaten yeni değeri gösterdiği için oradan okunamaz.
  const onceki = secim.dataset.onceki;
  secim.disabled = true;
  try {
    await api(`/users/${kisiId}/hesap`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: rol }),
    });
    ayarHesaplar();          // durumu tazele
  } catch (e) {
    alert('⚠ ' + (e.detail || 'Yetki değiştirilemedi'));
    secim.value = onceki;    // eski yetkiye dön
    secim.disabled = false;
  }
}

// ---------- Sistem ürünleri (ağ / yangın / alarm) ----------
// Aynı ekran her aileye hizmet eder; menü girişleri AILE_BILGI'den okunur
let agSablon = null;        // seçili ailenin tür/alan tanımları
let agAile = 'ag';          // hangi aile gösteriliyor
let agTur = '';             // seçili alt kategori ('' = tümü)
let agAraZaman = null;

const AILE_BILGI = {
  ag: { ikon: '🌐', ad: 'Ağ Ürünleri',
        alt: 'Switch, SFP modül, access point ve diğer ağ donanımı',
        marka: 'HUAWEI', model: 'S5735-L24T4S-A' },
  yangin: { ikon: '🔥', ad: 'Yangın Sistemleri',
            alt: 'Yangın alarm paneli, dedektörler, butonlar ve sirenler',
            ekle: 'Yangın ekipmanı', ilk: 'dedektor',
            marka: 'Mavigard', model: 'MG-1130' },
  alarm: { ikon: '🔐', ad: 'Alarm Sistemleri',
           alt: 'Hırsız alarm panelleri, kablolu/kablosuz dedektörler, '
                + 'tuş takımları, sirenler ve modüller',
           ekle: 'Alarm ekipmanı', ilk: 'alarm_dedektor',
           marka: 'Paradox', model: 'SP6000' },
  gecis: { ikon: '🚧', ad: 'Geçiş Sistemleri',
           alt: 'Kart okuyucu ve yazıcıları, bariyerler ve parçaları, '
                + 'plaka tanıma sistemi ve kameraları',
           ekle: 'Geçiş ekipmanı', ilk: 'kart_okuyucu',
           marka: 'CAME', model: 'Gard 4040' },
  kantar: { ikon: '⚖️', ad: 'Kantar Sistemi',
            alt: 'Araç kantarları, yük hücreleri, terminaller ve '
                 + 'yardımcı ekipman',
            ekle: 'Kantar ekipmanı', ilk: 'kantar_platform',
            marka: 'Baykon', model: 'BX24' },
};

async function renderAgView(aile = agAile) {
  if (aile !== agAile) { agAile = aile; agTur = ''; agSablon = null; }
  if (!agSablon) {
    try { agSablon = await api('/ag/sablon?aile=' + agAile); }
    catch { agSablon = []; }
  }
  const ozet = await api('/ag/ozet?aile=' + agAile).catch(() => null);
  const turBilgi = (k) => agSablon.find(s => s.tur === k) || {};

  const sekmeler = [['', `${AILE_BILGI[agAile].ikon} Tümü` +
                      (ozet ? ` (${ozet.toplam})` : '')]]
    .concat((ozet?.tur_dagilimi || []).map(d =>
      [d.tur, `${d.ikon} ${d.ad} (${d.adet})`]));
  // Henüz ürünü olmayan türler de eklenebilsin diye listede dursun
  for (const s of agSablon) {
    if (!sekmeler.some(([k]) => k === s.tur)) {
      sekmeler.push([s.tur, `${s.ikon} ${s.ad} (0)`]);
    }
  }

  const bilgi = AILE_BILGI[agAile];
  // Yangın tarafında port/PoE anlamsız; onun yerine tür çeşitliliği
  const ekKart = agAile === 'ag'
    ? statCard('Toplam port', ozet?.toplam_port ?? 0, '🔀', 'mavi') +
      statCard('PoE besleyen', ozet?.poe_cihaz ?? 0, '⚡', 'sari')
    : statCard('Ürün çeşidi', (ozet?.tur_dagilimi || []).length, '🧩', 'mavi');

  document.getElementById('view').innerHTML =
    sayfaBasligi(bilgi.ikon, bilgi.ad, bilgi.alt) + `
    ${ozet ? `<div class="stats">
      ${statCard('Toplam ürün', ozet.toplam, bilgi.ikon)}
      ${ekKart}
      ${statCard('Lokasyon', ozet.lokasyon_dagilimi.length, '📍', 'mor')}
    </div>` : ''}
    <div class="panel">
      <div class="row" style="align-items:center; margin-bottom:10px">
        <h2 style="margin:0; flex:1">Alt kategoriler</h2>
        ${canWrite() ? `<button class="primary" onclick="agUrunEkleAc()">
          + ${bilgi.ekle || 'Ağ ürünü'} ekle</button>` : ''}
        <button class="ghost" onclick="agTransferler()">🔄 Transferler</button>
      </div>
      <div class="row">${sekmeler.map(([k, l]) =>
        `<button class="ghost ${k === agTur ? 'sec' : ''}"
           onclick="agTurSec('${k}')">${l}</button>`).join('')}</div>
      <div class="row" style="margin-top:12px">
        <input id="agAra" class="grow" autocomplete="off"
               placeholder="Marka, model, parça no, seri no, özellik ara…"
               oninput="agAraGecikmeli()" />
        <select id="agLokasyon" onchange="agListele()">
          <option value="">Tüm lokasyonlar</option></select>
      </div>
    </div>
    <div id="agListe"><div class="panel">Yükleniyor…</div></div>
    ${ozet && ozet.lokasyon_dagilimi.length ? `<div class="panel">
      <h2>Lokasyona göre</h2>
      ${barList(ozet.lokasyon_dagilimi.map(d => ({ ad: d.lokasyon, adet: d.adet })),
                Math.max(...ozet.lokasyon_dagilimi.map(d => d.adet)))}
    </div>` : ''}`;

  // Lokasyon listesi
  api('/locations?limit=500').then(lok => {
    const el = document.getElementById('agLokasyon');
    if (!el) return;
    const secili = el.value;
    el.innerHTML = '<option value="">Tüm lokasyonlar</option>' + lok
      .slice().sort((a, b) => a.name.localeCompare(b.name, 'tr'))
      .map(l => `<option value="${l.id}">${kacir(l.name)}</option>`).join('');
    el.value = secili;
  }).catch(() => {});

  agListele();
}

function agTurSec(tur) { agTur = tur; renderAgView(agAile); }

function agAraGecikmeli() {
  clearTimeout(agAraZaman);
  agAraZaman = setTimeout(agListele, 200);
}

async function agListele() {
  const kutu = document.getElementById('agListe');
  if (!kutu) return;
  const p = new URLSearchParams({ aile: agAile });
  if (agTur) p.set('tur', agTur);
  const q = document.getElementById('agAra')?.value.trim();
  if (q) p.set('q', q);
  const lok = document.getElementById('agLokasyon')?.value;
  if (lok) p.set('location_id', lok);

  let liste;
  try { liste = await api('/ag/urunler?' + p.toString()); }
  catch (e) {
    kutu.innerHTML = `<div class="panel">⚠ ${e.detail || 'Alınamadı'}</div>`;
    return;
  }
  if (!liste.length) {
    kutu.innerHTML = '<div class="panel"><div class="muted">Eşleşen ürün yok.</div></div>';
    return;
  }

  // Seçili türün alanlarından sütun üret; "Tümü"nde genel sütunlar
  const s = agSablon.find(x => x.tur === agTur);
  const sutunlar = s ? s.alanlar.slice(0, 5).map(a => a.ad) : [];
  // SIM'li cihazlarda hat künyesi özellik değil, kaydın kendi alanı
  const hatSutun = s?.hat ? [['Operatör', 'operator'], ['Hat No', 'telefon_no']]
                          : [];

  kutu.innerHTML = `<div class="panel">
    <h2>${liste.length} ürün</h2>
    <table><thead><tr>
      <th></th><th>Cihaz No</th><th>Marka / Model</th>
      <th class="gizle-mobil">Seri No</th>
      ${hatSutun.map(([b]) => `<th>${b}</th>`).join('')}
      ${sutunlar.map(a => `<th>${kacir(a)}</th>`).join('')}
      <th>Lokasyon</th><th>Durum</th></tr></thead><tbody>
    ${liste.map(u => `<tr class="tikla" onclick="cihazDetay(${u.id})">
      <td>${u.gorsel_id
            ? `<img class="ag-kucuk" data-dosya="${u.gorsel_id}" alt="" />`
            : '<span class="ag-kucuk bos">📷</span>'}</td>
      <td><b>${kacir(u.asset_tag)}</b>
          ${u.tur && !agTur ? `<div class="muted" style="font-size:11.5px">${
            kacir((agSablon.find(x => x.tur === u.tur) || {}).ad || u.tur)}</div>` : ''}</td>
      <td>${kacir([u.marka, u.model].filter(Boolean).join(' '))}
          ${u.ozellikler['Parça No'] ? `<div class="muted" style="font-size:11.5px">${
            kacir(u.ozellikler['Parça No'])}</div>` : ''}</td>
      <td class="muted gizle-mobil">${esc(u.serial)}</td>
      ${hatSutun.map(([, k]) => `<td class="muted">${esc(u[k])}</td>`).join('')}
      ${sutunlar.map(a => `<td class="muted">${esc(u.ozellikler[a])}</td>`).join('')}
      <td>${esc(u.lokasyon)}${u.proje_kodu
            ? ` <span class="pill">${kacir(u.proje_kodu)}</span>` : ''}</td>
      <td>${u.zimmetli ? `<span class="tag used">${kacir(u.zimmetli)}</span>`
                       : esc(u.durum)}</td>
    </tr>`).join('')}</tbody></table></div>`;
  gorselleriYukle();
}

async function agTransferler() {
  let liste;
  try { liste = await api('/ag/transferler?limit=200'); }
  catch (e) { return alert('⚠ ' + (e.detail || 'Alınamadı')); }

  modalAc('🔄 Lokasyon transferleri', liste.length ? `
    <div class="note" style="margin-top:0">Hangi cihaz hangi şantiyeden
      hangisine gitti — en yeniler üstte.</div>
    <table><thead><tr><th>Cihaz</th><th>Nereden</th><th></th><th>Nereye</th>
      <th>Tarih</th></tr></thead><tbody>
    ${liste.map(t => `<tr class="tikla" onclick="cihazDetay(${t.asset_id})">
      <td><b>${esc(t.asset_tag)}</b></td>
      <td>${esc(t.nereden)}</td>
      <td class="muted">→</td>
      <td>${esc(t.nereye)}</td>
      <td class="muted">${t.tarih
          ? new Date(t.tarih).toLocaleDateString('tr-TR') : '—'}</td>
    </tr>`).join('')}</tbody></table>`
    : '<div class="muted">Henüz kayıtlı lokasyon değişikliği yok.</div>');
}

// Sistem ürünü ekleme — türe göre alanlar
function agUrunEkleAc(tur = agTur || AILE_BILGI[agAile].ilk || 'switch') {
  const s = agSablon.find(x => x.tur === tur) || agSablon[0];
  if (!s) return alert('⚠ Tür şablonu alınamadı.');

  // Kimlik alan adından değil indeksten üretilir: alan adları boşluk ve
  // Türkçe karakter içeriyor, CSS seçicisinde kullanılamıyor.
  const alanKutu = (a, i) => a.tip === 'secim'
    ? `<label>${kacir(a.etiket)}
         <select id="af_${i}" data-alan="${kacir(a.ad)}">
           <option value="">— seçilmedi —</option>
           ${a.secenekler.map(o => `<option value="${kacir(o)}">${kacir(o)}</option>`).join('')}
         </select></label>`
    : `<label>${kacir(a.etiket)}
         <input id="af_${i}" data-alan="${kacir(a.ad)}"
                ${a.tip === 'number' ? 'type="number"' : ''}
                placeholder="${kacir(a.ipucu || '')}" /></label>`;

  modalAc(`${AILE_BILGI[agAile].ad} — ürün ekle`, `
    <div class="row" style="margin-bottom:14px">
      ${agSablon.map(x => `<button class="ghost ${x.tur === tur ? 'sec' : ''}"
         onclick="agUrunEkleAc('${x.tur}')">${x.ikon} ${kacir(x.ad)}</button>`).join('')}
    </div>
    <div class="note" style="margin-top:0">${kacir(s.aciklama)}</div>
    <div class="bolum"><h4>Künye</h4>
      <div class="form-grid">
        <label>Cihaz No / Etiket <input id="auEtiket"
               placeholder="boş bırakılırsa seri no kullanılır" /></label>
        <label>Seri No <input id="auSeri" /></label>
        <label>Marka <input id="auMarka"
               placeholder="örn. ${AILE_BILGI[agAile].marka}" /></label>
        <label>Model <input id="auModel"
               placeholder="örn. ${AILE_BILGI[agAile].model}" /></label>
        <label>Demirbaş No <input id="auDemirbas" /></label>
        <label>Yönetim IP <input id="auIp" placeholder="örn. 10.0.0.2" /></label>
        <label>Lokasyon <select id="auLokasyon"></select></label>
        <label>Durum <select id="auDurum"></select></label>
        ${s.hat ? `
        <label>Operatör <select id="auOperator">
          <option value="">— seçilmedi —</option>
          ${['Turkcell', 'Vodafone', 'Türk Telekom', 'Diğer'].map(o =>
            `<option>${o}</option>`).join('')}
        </select></label>
        <label>Hat No <input id="auTelefon" placeholder="örn. 05xx xxx xx xx" /></label>
        <label>SIM No <input id="auSim" /></label>
        <label>IMEI <input id="auImei" /></label>` : ''}
      </div>
    </div>
    <div class="bolum"><h4>${kacir(s.ad)} özellikleri</h4>
      <div class="form-grid">${s.alanlar.map(alanKutu).join('')}</div>
    </div>
    <div class="row" style="margin-top:14px">
      <button class="primary" onclick="agUrunKaydet('${s.tur}')">Kaydet</button>
      <button class="ghost" onclick="modalKapat()">Vazgeç</button>
      <span id="auBilgi" class="note"></span>
    </div>`);

  // Lokasyon ve durum listeleri
  api('/locations?limit=500').then(l => {
    const el = document.getElementById('auLokasyon');
    if (el) el.innerHTML = secenekler(l, null);
  }).catch(() => {});
  api('/status-labels').then(l => {
    const el = document.getElementById('auDurum');
    if (el) el.innerHTML = secenekler(l, null);
  }).catch(() => {});
  setTimeout(() => document.getElementById('auSeri')?.focus(), 60);
}

async function agUrunKaydet(tur) {
  const bilgi = document.getElementById('auBilgi');
  const s = agSablon.find(x => x.tur === tur);
  const deger = (id) => document.getElementById(id)?.value.trim() || '';

  const ozellikler = {};
  document.querySelectorAll('[data-alan]').forEach(el => {
    const v = el.value.trim();
    if (v) ozellikler[el.dataset.alan] = v;
  });
  const govde = {
    tur,
    asset_tag: deger('auEtiket') || null,
    serial: deger('auSeri') || null,
    marka: deger('auMarka') || null,
    model: deger('auModel') || null,
    demirbas_no: deger('auDemirbas') || null,
    ip_address: deger('auIp') || null,
    location_id: Number(deger('auLokasyon')) || null,
    status_id: Number(deger('auDurum')) || null,
    operator: deger('auOperator') || null,
    telefon_no: deger('auTelefon') || null,
    sim_no: deger('auSim') || null,
    imei: deger('auImei') || null,
    ozellikler,
  };
  if (!govde.asset_tag && !govde.serial) {
    bilgi.innerHTML = '<span style="color:var(--err)">⚠ Cihaz no ya da seri no zorunlu.</span>';
    return;
  }
  try {
    await api('/ag/urunler', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(govde),
    });
    modalKapat();
    agTur = tur;
    renderAgView(agAile);
  } catch (e) {
    bilgi.innerHTML = `<span style="color:var(--err)">⚠ ${e.detail || 'Eklenemedi'}</span>`;
  }
}

// ---------- Yedekleme ----------
function boyutYaz(bayt) {
  if (!bayt) return '—';
  const birim = ['B', 'KB', 'MB', 'GB'];
  let i = 0, n = bayt;
  while (n >= 1024 && i < birim.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i ? 1 : 0)} ${birim[i]}`;
}

async function ayarYedek(mesaj = '') {
  const kutu = document.getElementById('ayarIcerik');
  kutu.innerHTML = '<div class="panel"><h2>Yedekleme</h2>Yükleniyor…</div>';
  let d;
  try { d = await api('/yedek'); }
  catch (e) {
    kutu.innerHTML = `<div class="panel">⚠ ${e.detail || 'Alınamadı'}</div>`;
    return;
  }
  const TUR_ADI = { veritabani: '🗄️ Veritabanı', dosyalar: '📎 Yüklenen dosyalar' };

  kutu.innerHTML = `
    <div class="panel">
      <div class="row" style="align-items:center; margin-bottom:6px">
        <h2 style="margin:0; flex:1">Yedek al</h2>
        <button class="primary" id="ydDug" onclick="yedekAl()">
          💾 Şimdi yedek al</button>
      </div>
      <div class="note">Veritabanının tamamı ve yüklenen dosyalar
        (görseller, imzalı formlar) ayrı dosyalar hâlinde arşivlenir.
        Yedekler <code>${kacir(d.klasor)}</code> klasöründe tutulur ve
        ${d.saklama_gun} günden eskiler otomatik silinir.</div>
      <div id="ydBilgi" class="note">${mesaj}</div>
    </div>
    <div class="panel">
      <h2>Mevcut yedekler (${d.yedekler.length})</h2>
      ${d.yedekler.length ? `<table><thead><tr>
        <th>Dosya</th><th>İçerik</th><th>Boyut</th><th>Tarih</th><th></th>
        </tr></thead><tbody>
        ${d.yedekler.map(y => `<tr>
          <td><b>${kacir(y.ad)}</b></td>
          <td>${TUR_ADI[y.tur] || y.tur}</td>
          <td class="muted">${boyutYaz(y.boyut)}</td>
          <td class="muted">${new Date(y.tarih).toLocaleString('tr-TR')}</td>
          <td>
            <button class="ghost mini" onclick="yedekIndir('${
              encodeURIComponent(y.ad)}')">⬇ İndir</button>
            <button class="ghost mini tehlike" onclick="yedekSil('${
              encodeURIComponent(y.ad)}')">🗑</button>
          </td></tr>`).join('')}</tbody></table>`
        : '<div class="muted">Henüz yedek alınmamış.</div>'}
    </div>
    <div class="panel">
      <h2>Otomatik yedek</h2>
      <div class="note">Her gece otomatik yedek için sunucuda bir kez
        şu komutu çalıştırın:</div>
      <pre style="background:var(--cizgi2); padding:12px; border-radius:9px;
                  overflow-x:auto; font-size:12.5px"><code>sudo cp deploy/yedek.sh /usr/local/bin/envanter-yedek
sudo chmod +x /usr/local/bin/envanter-yedek
echo "0 3 * * * /usr/local/bin/envanter-yedek" | sudo crontab -</code></pre>
      <div class="note">⚠ Yedekler sunucunun kendi diskinde durur. Disk
        arızasına karşı düzenli olarak başka bir yere (harici disk, bulut)
        kopyalayın.</div>
    </div>`;
}

async function yedekAl() {
  const dug = document.getElementById('ydDug');
  const bilgi = document.getElementById('ydBilgi');
  dug.disabled = true;
  dug.textContent = '⏳ Yedek alınıyor…';
  bilgi.textContent = '';
  try {
    const s = await api('/yedek', { method: 'POST' });
    // Mesajı tazelemeye taşı: panel yeniden çizilince kaybolmasın
    const metin = `<span style="color:var(--ok)">✓ Yedek alındı:
      ${kacir(s.veritabani)} (${boyutYaz(s.veritabani_boyut)})` +
      (s.dosyalar ? ` · ${kacir(s.dosyalar)} (${boyutYaz(s.dosyalar_boyut)})` : '') +
      (s.silinen_eski ? ` · ${s.silinen_eski} eski yedek silindi` : '') + '</span>';
    bilgi.innerHTML = metin;
    ayarYedek(metin);
  } catch (e) {
    bilgi.innerHTML = `<span style="color:var(--err)">⚠ ${
      e.detail || 'Yedek alınamadı'}</span>`;
  } finally {
    dug.disabled = false;
    dug.textContent = '💾 Şimdi yedek al';
  }
}

async function yedekIndir(adKodlu) {
  try {
    const r = await fetch(url('/yedek/' + adKodlu),
                          { headers: { 'Authorization': `Bearer ${token}` } });
    if (!r.ok) throw await r.json().catch(() => ({ detail: 'İndirilemedi' }));
    const baglanti = URL.createObjectURL(await r.blob());
    const a = document.createElement('a');
    a.href = baglanti; a.download = decodeURIComponent(adKodlu); a.click();
    setTimeout(() => URL.revokeObjectURL(baglanti), 60000);
  } catch (e) { alert('⚠ ' + (e.detail || e.message || 'İndirilemedi')); }
}

async function yedekSil(adKodlu) {
  if (!confirm(`"${decodeURIComponent(adKodlu)}" silinsin mi?`)) return;
  try {
    await api('/yedek/' + adKodlu, { method: 'DELETE' });
    ayarYedek();
  } catch (e) { alert('⚠ ' + (e.detail || 'Silinemedi')); }
}

// Personel kaydına giriş yetkisi verme (kişi arayarak)
// İki yol tek pencerede: kayıtlı personele yetki ver, ya da kişiyi de
// burada oluştur. Aranan kişi sistemde yoksa çıkmaza girilmesin.
function hesapAc(mod = 'mevcut') {
  modalAc('Kullanıcı ekle', `
    <div class="row" style="margin-bottom:14px">
      <button class="ghost ${mod === 'mevcut' ? 'sec' : ''}"
              onclick="hesapAc('mevcut')">👤 Kayıtlı personele yetki ver</button>
      <button class="ghost ${mod === 'yeni' ? 'sec' : ''}"
              onclick="hesapAc('yeni')">➕ Yeni kişi oluştur</button>
    </div>
    <div id="hyGovde"></div>`);
  if (mod === 'yeni') return hesapYeniKisiFormu();

  document.getElementById('hyGovde').innerHTML = `
    <div class="row">
      <input id="hyAra" class="grow" autocomplete="off"
             placeholder="Personel ara: ad soyad, sicil no, departman…"
             oninput="hesapKisiAra()" />
    </div>
    <div id="hySonuc" class="note">Yükleniyor…</div>`;
  setTimeout(() => document.getElementById('hyAra')?.focus(), 60);
  hesapKisiAra();
}

// Kişi kaydı + giriş bilgileri tek formda
function hesapYeniKisiFormu() {
  document.getElementById('hyGovde').innerHTML = `
    <div class="bolum" style="margin-top:0"><h4>Kişi bilgileri</h4>
      <div class="form-grid">
        <label>Ad <input id="ykAd" /></label>
        <label>Soyad <input id="ykSoyad" /></label>
        <label>Sicil No <input id="ykSicil" /></label>
        <label>Departman <input id="ykDepartman" /></label>
        <label>E-posta <input id="ykMail" type="email" /></label>
        <label>Telefon <input id="ykTelefon" /></label>
      </div>
    </div>
    <div class="bolum"><h4>Giriş bilgileri</h4>
      <div class="form-grid">
        <label>Kullanıcı adı <input id="ykKadi" autocomplete="off"
               placeholder="örn. mehmet" /></label>
        <label>Parola (en az 8 karakter) <input id="ykParola" type="password"
               autocomplete="new-password" /></label>
        <label>Yetki
          <select id="ykRol">
            <option value="viewer">Görüntüleyici — yalnızca okur</option>
            <option value="editor" selected>Düzenleyici — kayıt ekler/değiştirir</option>
            <option value="admin">Yönetici — her şey + kullanıcı yönetimi</option>
          </select></label>
      </div>
      <div class="note">Giriş bilgilerini boş bırakırsan kişi yalnızca
        personel olarak eklenir, sisteme giriş yapamaz.</div>
    </div>
    <div class="row" style="margin-top:14px">
      <button class="primary" onclick="yeniKullaniciKaydet()">Kaydet</button>
      <button class="ghost" onclick="modalKapat()">Vazgeç</button>
      <span id="ykBilgi" class="note"></span>
    </div>`;
  setTimeout(() => document.getElementById('ykAd')?.focus(), 60);
}

async function yeniKullaniciKaydet() {
  const bilgi = document.getElementById('ykBilgi');
  const deger = (id) => document.getElementById(id).value.trim();
  const hata = (m) => {
    bilgi.innerHTML = `<span style="color:var(--err)">⚠ ${m}</span>`;
  };

  // Pencere kapandıktan sonra alanlar DOM'dan silinir; değerleri şimdi al
  const ad = deger('ykAd');
  const kadi = deger('ykKadi');
  const parola = document.getElementById('ykParola').value;
  const rol = document.getElementById('ykRol').value;
  if (!ad) return hata('Ad zorunlu.');
  if (kadi && parola.length < 8) return hata('Parola en az 8 karakter olmalı.');
  if (parola && !kadi) return hata('Parola için kullanıcı adı da gerekli.');

  let kisi;
  try {
    kisi = await api('/users', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        first_name: ad,
        last_name: deger('ykSoyad') || null,
        employee_num: deger('ykSicil') || null,
        department: deger('ykDepartman') || null,
        email: deger('ykMail') || null,
        telefon: deger('ykTelefon') || null,
      }),
    });
  } catch (e) { return hata(e.detail || 'Personel eklenemedi'); }

  const bitir = () => { modalKapat(); ayarBolum = 'hesaplar'; renderAyarlarView(); };

  // Giriş bilgisi verilmediyse kişi yalnızca personel olarak eklendi
  if (!kadi) {
    bitir();
    alert(`✓ ${ad} personel olarak eklendi (giriş yetkisi yok).`);
    return;
  }
  try {
    await api(`/users/${kisi.id}/hesap`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: kadi, yeni_parola: parola, role: rol }),
    });
    bitir();
  } catch (e) {
    // Hesap açılamadı (ör. kullanıcı adı alınmış). Yeni açılan kişi kaydını
    // geri al ki yetim personel kalmasın; form açık kalsın, düzeltip
    // yeniden denesin.
    await api(`/users/${kisi.id}`, { method: 'DELETE' }).catch(() => {});
    hata(`${e.detail || 'Hesap açılamadı'} — düzeltip tekrar deneyin.`);
  }
}

let hyZaman = null;
function hesapKisiAra() {
  clearTimeout(hyZaman);
  hyZaman = setTimeout(async () => {
    const kutu = document.getElementById('hySonuc');
    if (!kutu) return;
    const q = document.getElementById('hyAra')?.value.trim() || '';
    const liste = await api('/users/ara?limit=15&q=' + encodeURIComponent(q))
      .catch(() => []);
    kutu.innerHTML = liste.length
      ? `<table><tbody>${liste.map(k => `
          <tr class="tikla" onclick="hesapDuzenle(${k.id})">
            <td><b>👤 ${kacir(k.ad)}</b></td>
            <td class="muted">${esc(k.employee_num)}</td>
            <td class="muted">${esc(k.department)}</td>
            <td><button class="primary">Seç</button></td></tr>`).join('')}</tbody></table>`
      : '<div class="muted">Eşleşen personel yok.</div>';
  }, 180);
}

async function hesapDuzenle(kisiId) {
  const k = await api('/users/' + kisiId).catch(() => null);
  if (!k) return alert('⚠ Personel bulunamadı.');
  const ad = [k.first_name, k.last_name].filter(Boolean).join(' ');
  const benim = me.id === kisiId;

  modalAc(`Hesap — ${kacir(ad)}`, `
    <div class="form-grid">
      <label>Kullanıcı adı
        <input id="hsKadi" value="${kacir(k.username || '')}"
               placeholder="örn. tayyar" /></label>
      <label>Yetki
        <select id="hsRol" ${benim ? 'disabled' : ''}>
          <option value="viewer"${k.role === 'viewer' ? ' selected' : ''}>Görüntüleyici</option>
          <option value="editor"${k.role === 'editor' ? ' selected' : ''}>Düzenleyici</option>
          <option value="admin"${k.role === 'admin' ? ' selected' : ''}>Yönetici</option>
        </select></label>
      <label>Yeni parola (boş bırakılırsa değişmez)
        <input id="hsParola" type="password" autocomplete="new-password"
               placeholder="en az 8 karakter" /></label>
      <label>Hesap durumu
        <select id="hsAktif" ${benim ? 'disabled' : ''}>
          <option value="true"${k.active ? ' selected' : ''}>Etkin</option>
          <option value="false"${!k.active ? ' selected' : ''}>Kapalı</option>
        </select></label>
    </div>
    ${benim ? `<div class="note">Kendi yetkinizi ve hesap durumunuzu buradan
       değiştiremezsiniz — sistemin yöneticisiz kalmaması için.</div>` : ''}
    <div class="row" style="margin-top:14px">
      <button class="primary" onclick="hesapKaydet(${kisiId})">Kaydet</button>
      <button class="ghost" onclick="modalKapat()">Vazgeç</button>
      <span id="hsBilgi" class="note"></span>
    </div>`);
}

async function hesapKaydet(kisiId) {
  const bilgi = document.getElementById('hsBilgi');
  const govde = {};
  const kadi = document.getElementById('hsKadi').value.trim();
  if (kadi) govde.username = kadi;
  const parola = document.getElementById('hsParola').value;
  if (parola) {
    if (parola.length < 8) {
      bilgi.innerHTML = '<span style="color:var(--err)">⚠ Parola en az 8 karakter.</span>';
      return;
    }
    govde.yeni_parola = parola;
  }
  const rolEl = document.getElementById('hsRol');
  const aktifEl = document.getElementById('hsAktif');
  if (!rolEl.disabled) govde.role = rolEl.value;
  if (!aktifEl.disabled) govde.active = aktifEl.value === 'true';

  try {
    await api(`/users/${kisiId}/hesap`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(govde),
    });
    modalKapat();
    ayarBolum = 'hesaplar';
    renderAyarlarView();
  } catch (e) {
    bilgi.innerHTML = `<span style="color:var(--err)">⚠ ${e.detail || 'Kaydedilemedi'}</span>`;
  }
}

// ---------- Açılış ----------
temaUygula(localStorage.getItem('tema') || 'acik');
(async () => {
  if (!token || !me) return girisSayfasi();
  try {
    me = await api('/auth/me');            // jeton hâlâ geçerli mi?
    localStorage.setItem('me', JSON.stringify(me));
    showApp();
  } catch { logout(); }
})();
