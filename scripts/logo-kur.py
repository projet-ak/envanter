#!/usr/bin/env python3
"""Kurum logolarını hazırlar: hangi zeminde gelirse gelsin doğru üretir.

`app/logo/` içine atılmış logo dosyalarını okur, her birinden mürekkep
MASKESİ çıkarır ve üç hedefi üretir:

    app/static/logo.png        beyaz Holding   → giriş + sol menü (koyu zemin)
    app/static/logo2.png       beyaz Taahhüt   → giriş ekranı ikinci rozet
    app/static/logo-rapor.png  yeşil Holding   → Excel raporlarının başlığı

Neden maske: eldeki dosyalar karışık geliyor — beyaz logo siyah zeminde,
yeşil logo beyaz zeminde, kimi saydam. Zemin rengine bakarak mürekkep alfa
maskesi çıkarılır; sonra maske istenen renkle doldurulur. Böylece siyah
kutulu logo diye bir sorun kalmaz, kaynak dosya ne olursa olsun çıktı hep
saydam zeminli ve tek renktir.

Şirket ayrımı dosya adından: "taah" geçen Taahhüt, "holding" geçen Holding
sayılır; hiçbiri geçmiyorsa dosya listelenir ve adlandırmanız istenir.

Kullanım:
    ./.venv/bin/python scripts/logo-kur.py            # app/logo/ içinden
    ./.venv/bin/python scripts/logo-kur.py /baska/yol
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageOps

KOK = Path(__file__).resolve().parent.parent
HEDEF = KOK / "app" / "static"
YESIL = (0, 61, 53)                      # ERN koyu yeşili (#003D35)
UZANTILAR = {".png", ".jpg", ".jpeg", ".webp"}


def maske_cikar(yol: Path) -> Image.Image:
    """Logodan mürekkep maskesi (L modu: 255 = tam mürekkep).

    - Saydam dosyada alfa kanalı zaten maskedir.
    - Koyu zeminde (siyah kutu) mürekkep açık renktir: maske = parlaklık.
    - Açık zeminde mürekkep koyudur: maske = parlaklığın tersi.
    """
    im = Image.open(yol).convert("RGBA")
    im.thumbnail((1600, 1600))
    alfa = im.getchannel("A")
    if alfa.getextrema()[0] < 250:            # gerçek saydamlık var
        maske = alfa
    else:
        gri = ImageOps.grayscale(im)
        kose = gri.getpixel((1, 1))
        maske = gri if kose < 128 else ImageOps.invert(gri)
    # JPEG'de mürekkep tam siyah/beyaz olmaz; maske 0–255 aralığına gerilir,
    # zayıf gürültü sıfırlanır — yoksa logo yarı saydam ve soluk çıkar.
    maske = ImageOps.autocontrast(maske)
    # Gövde tam opak olsun, kenar yumuşaklığı korunsun
    return maske.point(lambda v: 0 if v < 20 else min(255, int(v * 1.15)))


def boya(maske: Image.Image, renk: tuple[int, int, int]) -> Image.Image:
    """Maskeyi tek renkle doldurur; zemin tamamen saydam kalır."""
    cikti = Image.new("RGBA", maske.size, renk + (0,))
    cikti.putalpha(maske)
    return kirp(cikti)


def kirp(im: Image.Image) -> Image.Image:
    """Boş kenarları atar, çevresine küçük pay bırakır."""
    kutu = im.getbbox()
    if not kutu:
        return im
    im = im.crop(kutu)
    pay = max(im.width, im.height) // 25
    tuval = Image.new("RGBA", (im.width + 2 * pay, im.height + 2 * pay),
                      (0, 0, 0, 0))
    tuval.paste(im, (pay, pay), im)
    return tuval


def main() -> int:
    kaynak = Path(sys.argv[1]) if len(sys.argv) > 1 else KOK / "app" / "logo"
    if not kaynak.is_dir():
        print(f"Kaynak klasör yok: {kaynak}")
        return 1

    dosyalar = sorted(f for f in kaynak.iterdir()
                      if f.suffix.lower() in UZANTILAR)
    if not dosyalar:
        print(f"{kaynak} içinde logo dosyası yok (png/jpg/webp).")
        return 1

    maskeler: dict[str, Image.Image] = {}
    print("Bulunan dosyalar:")
    for f in dosyalar:
        ad = f.name.lower()
        sirket = ("taahhut" if "taah" in ad
                  else "holding" if "holding" in ad else None)
        print(f"  {f.name:<44} → {sirket or 'adından şirket anlaşılmadı'}")
        if sirket and sirket not in maskeler:
            maskeler[sirket] = maske_cikar(f)

    if "holding" not in maskeler and len(dosyalar) == 1:
        # Tek dosya varsa holding kabul et — küçük kurulum kolaylığı
        maskeler["holding"] = maske_cikar(dosyalar[0])

    yapilan = 0
    if "holding" in maskeler:
        boya(maskeler["holding"], (255, 255, 255)).save(HEDEF / "logo.png")
        boya(maskeler["holding"], YESIL).save(HEDEF / "logo-rapor.png")
        print("✓ app/static/logo.png        (beyaz Holding — giriş + menü)")
        print("✓ app/static/logo-rapor.png  (yeşil Holding — Excel raporları)")
        yapilan += 2
    else:
        print("! Holding logosu bulunamadı: dosya adında 'holding' geçmeli")

    if "taahhut" in maskeler:
        boya(maskeler["taahhut"], (255, 255, 255)).save(HEDEF / "logo2.png")
        print("✓ app/static/logo2.png       (beyaz Taahhüt — giriş ekranı)")
        yapilan += 1
    else:
        print("! Taahhüt logosu bulunamadı: dosya adında 'taah' geçmeli")

    return 0 if yapilan else 1


if __name__ == "__main__":
    sys.exit(main())
