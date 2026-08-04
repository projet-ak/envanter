"""Zimmet / teslim tutanağı PDF üretimi (Türkçe karakter destekli)."""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import settings

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


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName=_FONT_BOLD, fontSize=15,
            alignment=TA_CENTER, spaceAfter=2 * mm,
        ),
        "org": ParagraphStyle(
            "org", parent=base["Normal"], fontName=_FONT_BOLD, fontSize=11,
            alignment=TA_CENTER, textColor=colors.HexColor("#333333"),
        ),
        "normal": ParagraphStyle(
            "normal", parent=base["Normal"], fontName=_FONT, fontSize=9.5,
            leading=13,
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"], fontName=_FONT, fontSize=8,
            textColor=colors.HexColor("#666666"),
        ),
    }


def _fmt(value) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime("%d.%m.%Y")
    return str(value)


def _info_table(rows: list[tuple[str, str]], st) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", st["normal"]), Paragraph(v, st["normal"])]
            for k, v in rows]
    table = Table(data, colWidths=[38 * mm, None])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#DDDDDD")),
    ]))
    return table


def build_zimmet_pdf(
    *,
    assets: list,
    user=None,
    doc_type: str = "zimmet",  # "zimmet" | "iade"
    org_name: str | None = None,
    note: str | None = None,
) -> bytes:
    """Zimmet veya iade tutanağını PDF (bytes) olarak üretir."""
    st = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="Zimmet Tutanağı" if doc_type == "zimmet" else "İade Tutanağı",
    )

    org = org_name or settings.org_name
    baslik = "ZİMMET TESLİM TUTANAĞI" if doc_type == "zimmet" else "İADE TESLİM TUTANAĞI"
    flow = [
        Paragraph(org, st["org"]),
        Spacer(1, 3 * mm),
        Paragraph(baslik, st["title"]),
        Spacer(1, 4 * mm),
    ]

    # Personel bilgileri
    if user is not None:
        ad = " ".join(filter(None, [user.first_name, user.last_name]))
        flow += [
            Paragraph("<b>Personel Bilgileri</b>", st["normal"]),
            Spacer(1, 1.5 * mm),
            _info_table([
                ("Ad Soyad", _fmt(ad)),
                ("Sicil No", _fmt(user.employee_num)),
                ("Departman", _fmt(user.department)),
                ("Şube", _fmt(getattr(user, "sube", None))),
                ("E-posta", _fmt(user.email)),
                ("Telefon", _fmt(getattr(user, "telefon", None))),
            ], st),
            Spacer(1, 5 * mm),
        ]

    # Varlık tablosu
    header = ["#", "Etiket", "Demirbaş No", "Cihaz", "Seri No", "Barkod"]
    data = [[Paragraph(f"<b>{h}</b>", st["normal"]) for h in header]]
    for i, a in enumerate(assets, start=1):
        data.append([
            Paragraph(str(i), st["normal"]),
            Paragraph(_fmt(a.asset_tag), st["normal"]),
            Paragraph(_fmt(a.demirbas_no), st["normal"]),
            Paragraph(_fmt(a.name), st["normal"]),
            Paragraph(_fmt(a.serial), st["normal"]),
            Paragraph(_fmt(a.barkod), st["normal"]),
        ])

    table = Table(data, colWidths=[8 * mm, 26 * mm, 28 * mm, None, 30 * mm, 28 * mm],
                  repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow += [Paragraph("<b>Teslim Edilen Cihazlar</b>", st["normal"]),
             Spacer(1, 1.5 * mm), table, Spacer(1, 6 * mm)]

    # Metin
    if doc_type == "zimmet":
        metin = ("Yukarıda bilgileri yer alan cihaz(lar) tarafıma çalışır durumda "
                 "teslim edilmiştir. Cihaz(lar)ı özenle kullanacağımı, kurum "
                 "dışına izinsiz çıkarmayacağımı, arıza, kayıp veya hasar "
                 "durumunda derhal bilgi vereceğimi ve görevimden ayrılmam "
                 "hâlinde eksiksiz iade edeceğimi kabul ve beyan ederim.")
    else:
        metin = ("Yukarıda bilgileri yer alan cihaz(lar) tarafımdan eksiksiz "
                 "olarak iade edilmiş ve teslim alınmıştır.")
    flow += [Paragraph(metin, st["normal"]), Spacer(1, 4 * mm)]

    if note:
        flow += [Paragraph(f"<b>Not:</b> {note}", st["normal"]), Spacer(1, 4 * mm)]

    flow += [Paragraph(f"<b>Tarih:</b> {dt.date.today().strftime('%d.%m.%Y')}",
                       st["normal"]), Spacer(1, 8 * mm)]

    # İmza alanları
    sign = Table([
        [Paragraph("<b>Teslim Eden</b><br/><br/>Ad Soyad:<br/><br/>İmza:", st["normal"]),
         Paragraph("<b>Teslim Alan</b><br/><br/>Ad Soyad:<br/><br/>İmza:", st["normal"])],
    ], colWidths=[None, None], rowHeights=[32 * mm])
    sign.setStyle(TableStyle([
        ("BOX", (0, 0), (0, 0), 0.4, colors.HexColor("#BBBBBB")),
        ("BOX", (1, 0), (1, 0), 0.4, colors.HexColor("#BBBBBB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    flow += [sign, Spacer(1, 4 * mm),
             Paragraph("Bu belge envanter sistemi tarafından üretilmiştir.", st["small"])]

    doc.build(flow)
    return buffer.getvalue()
