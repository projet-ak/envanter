"""Fatura / irsaliye görselinden ürün kalemlerini çıkarma (Claude vision).

Görsel veya PDF, Claude'a gönderilir; yapılandırılmış çıktı (`InvoiceExtraction`)
olarak kalemler döner. Hiçbir şey otomatik kaydedilmez — kullanıcı önizleyip
onayladıktan sonra envantere eklenir.
"""

from __future__ import annotations

import base64

from app.config import settings
from app.schemas import InvoiceExtraction

SUPPORTED_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
}
SUPPORTED_PDF_TYPE = "application/pdf"

_SYSTEM = """Sen bir BT envanter sisteminin fatura okuma yardımcısısın.
Sana verilen fatura veya irsaliye görüntüsünden bilgileri çıkar.

Kurallar:
- Sadece görselde gerçekten yazan bilgileri çıkar; tahmin etme, uydurma.
- Yalnızca envantere girecek fiziksel ürün/cihaz kalemlerini listele.
  Hizmet, kargo, montaj, iskonto, KDV gibi satırları kalem olarak ekleme.
- Fiyatlar KDV hariç birim fiyat olmalı. Toplam tutarı birim fiyat sanma:
  satırda adet > 1 ise ve yalnızca toplam varsa, toplamı adede böl.
- Marka ve model ürün adının içinde geçiyorsa ayrıştır
  (örn. "Dell Latitude 5440 Notebook" → marka: Dell, model: Latitude 5440).
- Kategoriyi cihaz türünden tahmin et: Dizüstü, Masaüstü, Monitör, Telefon,
  Tablet, Yazıcı, Ağ Cihazı, Sunucu, Aksesuar gibi.
- Tarihi YYYY-AA-GG biçiminde ver. Belirsizse boş bırak.
- Türkçe fatura biçimlerinde ondalık ayırıcı virgül, binlik ayırıcı noktadır
  (1.250,50 → 1250.50). Buna dikkat et.
"""


class AIUnavailable(RuntimeError):
    """ANTHROPIC_API_KEY tanımlı değil veya AI çağrısı başarısız."""


def extract_invoice(file_bytes: bytes, media_type: str) -> InvoiceExtraction:
    """Fatura görselinden/PDF'inden kalemleri çıkarır."""
    if not settings.anthropic_api_key:
        raise AIUnavailable(
            "Fatura okuma için ANTHROPIC_API_KEY ayarlanmalı (.env dosyasına ekle)."
        )

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    encoded = base64.standard_b64encode(file_bytes).decode()

    if media_type == SUPPORTED_PDF_TYPE:
        document_block: dict = {
            "type": "document",
            "source": {"type": "base64", "media_type": media_type, "data": encoded},
        }
    else:
        document_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": encoded},
        }

    response = client.messages.parse(
        model=settings.anthropic_model,
        max_tokens=8000,
        system=_SYSTEM,
        thinking={"type": "adaptive"},
        messages=[{
            "role": "user",
            "content": [
                document_block,
                {"type": "text",
                 "text": "Bu faturadaki envantere girecek ürün kalemlerini çıkar."},
            ],
        }],
        output_format=InvoiceExtraction,
    )

    parsed = response.parsed_output
    if parsed is None:
        raise AIUnavailable("Fatura okunamadı; görüntü net değil veya biçim tanınmadı.")
    return parsed
