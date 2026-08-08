"""Demirbaş zimmet / iade formu (PDF, Türkçe karakter destekli).

Yerleşim, kurumun kullandığı örnek "DEMİRBAŞ ZİMMET FORMU"nu izler:
künye (Nesne No / Açıklama / Tür), Özellikler tablosu, Notlar, Kullanıcı
Bilgileri, taahhüt metni ve TESLİM EDEN / TESLİM ALAN imza bloğu.
Her cihaz kendi sayfasına basılır — her biri ayrı imzalanır.
"""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import settings

# Kurum logosu (yeşil versiyon — beyaz kâğıda göre). scripts/logo-kur.py
# üretir; dosya yoksa form logosuz, aynı düzende basılır.
LOGO_YOLU = Path(__file__).resolve().parent.parent / "static" / "logo-rapor.png"


def _logo_blogu(olcek: float) -> list:
    """Başlığın üstüne ortalanmış logo; boyut sayfa ölçeğiyle birlikte küçülür.

    Yükseklik eklenince tek sayfaya sığdırma mekanizması (_sigdir) gerekirse
    bir alt ölçeğe iner — sayfa taşması logo yüzünden oluşmaz.
    """
    if not LOGO_YOLU.exists():
        return []
    iw, ih = ImageReader(str(LOGO_YOLU)).getSize()
    h = 12 * mm * olcek
    img = RLImage(str(LOGO_YOLU), width=iw / ih * h, height=h)
    img.hAlign = "CENTER"
    return [img, Spacer(1, 2 * mm * olcek)]

# --------------------------------------------------------------------------- #
# Font kaydı — Türkçe karakterler (ğ, ş, ı, İ, ç, ö, ü) için TTF şart.
# --------------------------------------------------------------------------- #
_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"

_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
]

for regular, bold in _CANDIDATES:
    if Path(regular).exists() and Path(bold).exists():
        try:
            pdfmetrics.registerFont(TTFont("TR", regular))
            pdfmetrics.registerFont(TTFont("TR-Bold", bold))
            _FONT, _FONT_BOLD = "TR", "TR-Bold"
        except Exception:
            pass
        break

_CIZGI = colors.HexColor("#999999")
_BASLIK_ZEMIN = colors.HexColor("#E8E8E8")


def _styles(olcek: float = 1.0):
    """Stil sözlüğü. `olcek` < 1 iken yazı ve satır aralığı küçülür.

    Çok özellikli cihazlarda (uzun ekran kartı / anakart metinleri) form ikinci
    sayfaya taşabiliyor; `build_zimmet_pdf` böyle durumlarda ölçeği düşürerek
    formu tek sayfada tutar.
    """
    base = getSampleStyleSheet()
    p = lambda x: x * olcek  # noqa: E731 — punto kısaltması
    return {
        "olcek": olcek,
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName=_FONT_BOLD, fontSize=p(13),
            alignment=TA_CENTER, spaceAfter=0,
        ),
        "org": ParagraphStyle(
            "org", parent=base["Normal"], fontName=_FONT_BOLD, fontSize=p(10),
            alignment=TA_CENTER, textColor=colors.HexColor("#444444"),
        ),
        "etiket": ParagraphStyle(
            "etiket", parent=base["Normal"], fontName=_FONT_BOLD, fontSize=p(8.5),
            leading=p(10),
        ),
        "deger": ParagraphStyle(
            "deger", parent=base["Normal"], fontName=_FONT, fontSize=p(8.5),
            leading=p(10),
        ),
        "bolum": ParagraphStyle(
            "bolum", parent=base["Normal"], fontName=_FONT_BOLD, fontSize=p(9),
            leading=p(12),
        ),
        "taahhut": ParagraphStyle(
            "taahhut", parent=base["Normal"], fontName=_FONT, fontSize=p(8.5),
            leading=p(12), alignment=TA_JUSTIFY,
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"], fontName=_FONT, fontSize=p(7),
            textColor=colors.HexColor("#888888"),
        ),
    }


def _fmt(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime("%d.%m.%Y")
    return str(value)


def ozellik(asset, *adlar: str) -> str:
    """Cihazın `custom` JSON'undan ilk dolu özelliği getirir.

    Özellikler gruplara ayrılmış olarak saklanır ({"İşlemci": {...}}), bu
    yüzden grup adını bilmeden alan adına göre arıyoruz.
    """
    ozel = asset.custom or {}
    for ad in adlar:
        for grup in ozel.values():
            if isinstance(grup, dict) and grup.get(ad) not in (None, ""):
                return str(grup[ad])
    return ""


def _kunye_satirlari(asset) -> list[tuple[str, str]]:
    """Örnek formun üst künyesi."""
    model = getattr(asset, "model", None)
    kategori = getattr(model, "category", None) if model else None
    return [
        ("Nesne No", _fmt(asset.asset_tag)),
        ("Nesne Açıklama", _fmt(asset.name or (model.name if model else ""))),
        ("Nesne Türü / Kategori", _fmt(kategori.name if kategori else "")),
    ]


def _ozellik_satirlari(asset, user) -> list[tuple[str, str]]:
    """Örnek formdaki "Özellikler" bölümü."""
    model = getattr(asset, "model", None)
    uretici = getattr(model, "manufacturer", None) if model else None
    lokasyon = getattr(asset, "location", None)
    durum = getattr(asset, "status", None)
    sirket = getattr(asset, "company", None)

    yer = lokasyon.name if lokasyon else ""
    if lokasyon is not None and lokasyon.proje_kodu and lokasyon.proje_kodu not in yer:
        yer = f"{yer} ({lokasyon.proje_kodu})"

    kisi = ""
    if user is not None:
        kisi = " ".join(filter(None, [user.first_name, user.last_name]))

    satirlar = [
        ("MARKA", _fmt(uretici.name if uretici else ozellik(asset, "Marka"))),
        ("MODEL", _fmt(model.name if model else "")),
        ("ŞASİ NO / SERİ NO", _fmt(asset.serial)),
        ("KULLANIM DURUMU", _fmt(durum.name if durum else "")),
        ("ZİMMETLENEN PERSONEL", _fmt(kisi)),
        ("LOKASYON", _fmt(yer)),
        ("KİRALANAN FİRMA", _fmt(sirket.name if sirket else "")),
        ("KAPASİTE", ozellik(asset, "Harddisk Kapasitesi", "Ram Kapasitesi (mB)")),
        ("İŞLEMCİ MARKA / MODEL",
         ozellik(asset, "İşlemci (Bütün)", "İşlemci Modeli", "İşlemci Markası")),
        ("RAM TİPİ", ozellik(asset, "Ram (Bütün)", "Ram DDR", "Ram Markası")),
        ("EKRAN KARTI",
         ozellik(asset, "Ekran Kartı (Bütün)", "Ekran Kartı Marka")),
        ("HDD BİLGİSİ",
         ozellik(asset, "Harddisk (Bütün)", "Harddisk Modeli", "Harddisk Tipi")),
        ("ANAKART", ozellik(asset, "Ana Kart")),
        ("EKRAN BOYUTU",
         ozellik(asset, "Dizüstü Ekran Boyut", "1. Ekran Boyutu")),
        ("İŞLETİM SİSTEMİ", ozellik(asset, "İşletim Sistemi")),
    ]
    # IMEI/hat yalnızca telefon ve hatlarda anlamlı; boşken satır israfı olur
    if asset.imei or asset.telefon_no:
        satirlar.append(("IMEI / HAT NO", _fmt(asset.imei or asset.telefon_no)))
    satirlar.append(("CİHAZ KODU", _fmt(asset.demirbas_no)))
    return satirlar


def _tablo(satirlar: list[tuple[str, str]], st, *, etiket_gen=46 * mm) -> Table:
    data = [[Paragraph(k, st["etiket"]), Paragraph(v or "", st["deger"])]
            for k, v in satirlar]
    t = Table(data, colWidths=[etiket_gen, None])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, _CIZGI),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F5F5")),
    ]))
    return t


def _serbest_kutu(metin: str, st, *, yukseklik=12 * mm) -> Table:
    """Tek sütunlu, elle doldurulabilecek boş alan (Notlar gibi)."""
    t = Table([[Paragraph(metin or "", st["deger"])]], colWidths=[None],
              rowHeights=[yukseklik * st["olcek"]])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, _CIZGI),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _bolum_basligi(metin: str, st) -> Table:
    t = Table([[Paragraph(metin, st["bolum"])]], colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _BASLIK_ZEMIN),
        ("BOX", (0, 0), (-1, -1), 0.4, _CIZGI),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


TAAHHUT_ZIMMET = (
    "{org}'a ait yukarıda özellikleri yazılı araç/cihaz/telefon hattını sağlam ve "
    "çalışır vaziyette teslim aldım. Garanti kapsamına girmeyen ve kullanıcı "
    "hatasından kaynaklanan arızaların tamirinden sorumlu olacağımı; demirbaş "
    "olarak aldığım bu malzemeyi emeklilik, istifa veya görevden ayrılma gibi "
    "durumlarda eksiksiz ve çalışır durumda ilgili görevlilere teslim edeceğimi "
    "kabul ediyorum."
)

TAAHHUT_IADE = (
    "{org}'a ait yukarıda özellikleri yazılı araç/cihaz/telefon hattı tarafımdan "
    "eksiksiz ve çalışır durumda iade edilmiş, ilgili görevlilerce teslim "
    "alınmıştır."
)


def _imza_blogu(st) -> Table:
    """TESLİM EDEN / TESLİM ALAN — Ad Soyad, İmza, Tarih satırları."""
    bos = Paragraph("", st["deger"])
    data = [
        [Paragraph("TESLİM EDEN", st["bolum"]), Paragraph("TESLİM ALAN", st["bolum"])],
        [Paragraph("Ad Soyad", st["etiket"]), Paragraph("Ad Soyad", st["etiket"])],
        [bos, bos],
        [Paragraph("İmza", st["etiket"]), Paragraph("İmza", st["etiket"])],
        [bos, bos],
        [Paragraph("Tarih", st["etiket"]), Paragraph("Tarih", st["etiket"])],
        [bos, bos],
    ]
    o = st["olcek"]
    t = Table(data, colWidths=[None, None],
              rowHeights=[y * mm * o for y in (7, 5, 8, 5, 14, 5, 8)])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, _CIZGI),
        ("BACKGROUND", (0, 0), (-1, 0), _BASLIK_ZEMIN),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("SPAN", (0, 0), (0, 0)),
    ]))
    return t


def _sayfa(asset, user, *, org: str, doc_type: str, note: str | None, st) -> list:
    """Tek cihaz için form sayfası."""
    kisi_ad = ""
    if user is not None:
        kisi_ad = " ".join(filter(None, [user.first_name, user.last_name]))

    taahhut = (TAAHHUT_ZIMMET if doc_type == "zimmet" else TAAHHUT_IADE).format(org=org)
    baslik = ("DEMİRBAŞ ZİMMET FORMU" if doc_type == "zimmet"
              else "DEMİRBAŞ İADE FORMU")

    o = st["olcek"]
    return [
        *_logo_blogu(o),
        Paragraph(org, st["org"]),
        Spacer(1, 1.5 * mm * o),
        Paragraph(baslik, st["title"]),
        Spacer(1, 4 * mm * o),

        _tablo(_kunye_satirlari(asset), st),
        Spacer(1, 2.5 * mm * o),

        _bolum_basligi("Özellikler", st),
        _tablo(_ozellik_satirlari(asset, user), st),
        Spacer(1, 2.5 * mm * o),

        _bolum_basligi("Notlar", st),
        _serbest_kutu(_fmt(note or asset.notes), st),
        Spacer(1, 2.5 * mm * o),

        _bolum_basligi("Kullanıcı Bilgileri", st),
        _tablo([
            ("Ad Soyad", _fmt(kisi_ad)),
            ("Sicil No", _fmt(getattr(user, "employee_num", None))),
            ("Departman", _fmt(getattr(user, "department", None))),
            ("Mail Adresi", _fmt(getattr(user, "email", None))),
        ], st),
        Spacer(1, 4 * mm * o),

        Paragraph(taahhut, st["taahhut"]),
        Spacer(1, 4 * mm * o),

        KeepTogether(_imza_blogu(st)),
    ]


# Denenecek küçültme oranları. Çoğu cihaz 1.0'da sığar; uzun ekran kartı /
# anakart metni olanlar için kademeli olarak küçültülür.
_OLCEKLER = (1.0, 0.94, 0.88, 0.82, 0.76)


def _yukseklik(flow: list, genislik: float) -> float:
    """Akışın toplam yüksekliğini ölçer (sayfaya sığıp sığmadığını anlamak için)."""
    toplam = 0.0
    for f in flow:
        try:
            toplam += f.wrap(genislik, 0)[1]
        except Exception:
            return float("inf")   # ölçemiyorsak sığmıyor say, küçültmeye devam
    return toplam


def _sigdir(asset, user, *, org: str, doc_type: str, note: str | None,
            genislik: float, yukseklik: float) -> list:
    """Formu tek sayfaya sığdıracak en büyük ölçekle üretir."""
    sayfa = None
    for olcek in _OLCEKLER:
        sayfa = _sayfa(asset, user, org=org, doc_type=doc_type, note=note,
                       st=_styles(olcek))
        if _yukseklik(sayfa, genislik) <= yukseklik:
            return sayfa
    return sayfa   # en küçük ölçekte bile sığmıyorsa taşmasına izin ver


def build_zimmet_pdf(
    *,
    assets: list,
    user=None,
    doc_type: str = "zimmet",  # "zimmet" | "iade"
    org_name: str | None = None,
    note: str | None = None,
) -> bytes:
    """Zimmet/iade formunu PDF (bytes) olarak üretir — cihaz başına bir sayfa."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title="Demirbaş Zimmet Formu" if doc_type == "zimmet"
              else "Demirbaş İade Formu",
    )
    org = org_name or settings.org_name

    flow: list = []
    for i, asset in enumerate(assets):
        sayfa = _sigdir(asset, user, org=org, doc_type=doc_type, note=note,
                        genislik=doc.width, yukseklik=doc.height)
        flow += sayfa
        if i < len(assets) - 1:
            flow.append(PageBreak())

    doc.build(flow)
    return buffer.getvalue()
