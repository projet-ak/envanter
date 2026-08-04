"""Varlık etiketi üretimi: QR kod (PNG) ve yazdırılabilir etiket sayfası (PDF).

Etiket üzerinde: kurum adı, varlık etiketi (asset_tag), demirbaş no, cihaz adı
ve QR kod bulunur. QR kod varlığın etiketini içerir — okutunca arama kutusuna
yazılır ve cihaz anında bulunur.
"""

from __future__ import annotations

import io

import qrcode
from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas

from app.config import settings
from app.pdf.zimmet import _FONT, _FONT_BOLD

# A4 üzerinde 3 sütun x 8 satır = sayfa başına 24 etiket (70 x 33 mm)
COLS, ROWS = 3, 8
LABEL_W, LABEL_H = 63 * mm, 33 * mm
MARGIN_X, MARGIN_Y = 8 * mm, 10 * mm
GAP_X, GAP_Y = 2 * mm, 1.5 * mm


def qr_png(data: str, box_size: int = 8, border: int = 2) -> bytes:
    """Verilen metin için QR kod PNG'si üretir."""
    qr = qrcode.QRCode(box_size=box_size, border=border,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _truncate(c: pdfcanvas.Canvas, text: str, font: str, size: float,
              max_width: float) -> str:
    """Metni etikete sığacak şekilde kısaltır."""
    if c.stringWidth(text, font, size) <= max_width:
        return text
    while text and c.stringWidth(text + "…", font, size) > max_width:
        text = text[:-1]
    return text + "…"


def _draw_label(c: pdfcanvas.Canvas, x: float, y: float, asset,
                org: str, show_barcode: bool) -> None:
    """Tek bir etiketi (x, y) sol-alt köşesinden çizer."""
    c.setStrokeColor(colors.HexColor("#CCCCCC"))
    c.setLineWidth(0.4)
    c.rect(x, y, LABEL_W, LABEL_H)

    pad = 2.5 * mm
    qr_size = 22 * mm
    text_x = x + pad
    text_w = LABEL_W - qr_size - 3 * pad

    # Kurum adı
    c.setFont(_FONT, 6)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawString(text_x, y + LABEL_H - pad - 4, _truncate(c, org, _FONT, 6, text_w))

    # Varlık etiketi (büyük)
    c.setFillColor(colors.black)
    c.setFont(_FONT_BOLD, 11)
    c.drawString(text_x, y + LABEL_H - pad - 15,
                 _truncate(c, asset.asset_tag or "-", _FONT_BOLD, 11, text_w))

    # Cihaz adı
    c.setFont(_FONT, 7)
    if asset.name:
        c.drawString(text_x, y + LABEL_H - pad - 24,
                     _truncate(c, asset.name, _FONT, 7, text_w))

    # Demirbaş no
    if asset.demirbas_no:
        c.setFillColor(colors.HexColor("#444444"))
        c.drawString(text_x, y + LABEL_H - pad - 32,
                     _truncate(c, f"Demirbaş: {asset.demirbas_no}", _FONT, 7, text_w))

    # QR kod (sağ tarafta)
    qr_data = asset.asset_tag or asset.demirbas_no or str(asset.id)
    img = ImageReader(io.BytesIO(qr_png(qr_data, box_size=6, border=1)))
    c.drawImage(img, x + LABEL_W - qr_size - pad, y + (LABEL_H - qr_size) / 2,
                qr_size, qr_size, preserveAspectRatio=True, mask="auto")

    # Alt kısımda Code128 barkod (opsiyonel)
    if show_barcode and qr_data:
        try:
            bc = code128.Code128(qr_data, barHeight=6 * mm, barWidth=0.33,
                                 humanReadable=False)
            bc.drawOn(c, text_x, y + pad)
        except Exception:
            pass  # barkoda uygun olmayan karakterler varsa atla


def labels_pdf(assets: list, *, org_name: str | None = None,
               show_barcode: bool = True, start_offset: int = 0) -> bytes:
    """Yazdırılabilir etiket sayfası (A4, sayfa başına 24 etiket) üretir.

    `start_offset`: yarım kullanılmış etiket kağıdı için baştan kaç etiket
    atlanacağı.
    """
    org = org_name or settings.org_name
    buffer = io.BytesIO()
    c = pdfcanvas.Canvas(buffer, pagesize=A4)
    per_page = COLS * ROWS
    page_h = A4[1]

    slot = start_offset % per_page
    for asset in assets:
        if slot and slot % per_page == 0:
            c.showPage()
            slot = 0
        row, col = divmod(slot, COLS)
        x = MARGIN_X + col * (LABEL_W + GAP_X)
        y = page_h - MARGIN_Y - (row + 1) * LABEL_H - row * GAP_Y
        _draw_label(c, x, y, asset, org, show_barcode)
        slot += 1
        if slot % per_page == 0:
            c.showPage()
            slot = 0

    if slot % per_page != 0:
        c.showPage()
    c.save()
    return buffer.getvalue()
