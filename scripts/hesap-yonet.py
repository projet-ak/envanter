#!/usr/bin/env python3
"""Giriş hesaplarını listeler, parola atar, kilidi açar.

Parolalar geri döndürülemez biçimde (hash) saklanır — unutulan parola
okunamaz, yenisi atanır. Bu betik sunucuda çalıştırılır:

    ./.venv/bin/python scripts/hesap-yonet.py                 # hesapları listele
    ./.venv/bin/python scripts/hesap-yonet.py --parola tayyar # yeni parola üret ve ata
    ./.venv/bin/python scripts/hesap-yonet.py --parola tayyar --deger "Gizli.2026"
    ./.venv/bin/python scripts/hesap-yonet.py --parola tayyar --admin
    ./.venv/bin/python scripts/hesap-yonet.py --kilidi-ac tayyar
    ./.venv/bin/python scripts/hesap-yonet.py --parola akbulut --kisi "Akbulut" --admin

Kullanıcı adı henüz tanımlı değilse `--kisi` ile personel kaydını arayın:
o kişiye kullanıcı adı verilir (yeni kişi kaydı AÇILMAZ — zimmetleri,
geçmişi ve lokasyonu olduğu gibi kalır).

`--admin` hesabı yönetici yapar ve kapalıysa açar. Art arda hatalı parola
girilen hesap geçici olarak KİLİTLİ olur (listede DURUM sütununda görünür);
süre dolunca kendiliğinden açılır, beklemek istemezseniz `--kilidi-ac`
kullanın. Parola atamak da kilidi kaldırır.

Üretilen parola yalnızca ekrana yazılır; kaydedip kullanıcıya güvenli bir
yolla iletin, ilk girişten sonra Ayarlar → Parola'dan değiştirmesini
söyleyin.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.auth import hash_password, kilit_kalan_saniye  # noqa: E402
from app.excel.sema import _sadelestir  # noqa: E402
from app.models import User, UserRole  # noqa: E402

M, Y, S, N = '\033[36m', '\033[32m', '\033[33m', '\033[0m'

# Karışabilen karakterler (O/0, l/1/I) yok: parola telefonda okunabilsin
HARF = "abcdefghijkmnopqrstuvwxyz"
BUYUK = "ABCDEFGHJKLMNPQRSTUVWXYZ"
RAKAM = "23456789"
SIMGE = "!@#$%*?-_+="


def parola_uret(uzunluk: int = 14) -> str:
    """Her türden en az bir karakter içeren rastgele parola."""
    havuz = HARF + BUYUK + RAKAM + SIMGE
    parcalar = [secrets.choice(HARF), secrets.choice(BUYUK),
                secrets.choice(RAKAM), secrets.choice(SIMGE)]
    parcalar += [secrets.choice(havuz) for _ in range(uzunluk - len(parcalar))]
    secrets.SystemRandom().shuffle(parcalar)
    return "".join(parcalar)


def kisi_ara(db, terim: str) -> list[User]:
    """Ada/soyada göre personel arar (Türkçe karakter duyarsız).

    Kullanıcı adı olanlar da dahildir; arayan zaten kime yetki vereceğini
    biliyor. Eşleşme sıralı: önce tam ad, sonra parça içerenler.
    """
    sade = _sadelestir(terim)
    if not sade:
        return []
    bulunan = []
    for k in db.scalars(select(User)).all():
        ad = _sadelestir(" ".join(filter(None, [k.first_name, k.last_name])))
        if sade in ad:
            bulunan.append((0 if ad == sade else 1, ad, k))
    return [k for _, _, k in sorted(bulunan, key=lambda x: (x[0], x[1]))]


def hesaplari_listele(db) -> list[User]:
    """Kullanıcı adı olan (yani giriş yapabilen) kayıtlar."""
    return db.scalars(
        select(User).where(User.username.is_not(None))
        .order_by(User.username)).all()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parola", metavar="KULLANICI",
                    help="bu kullanıcıya yeni parola ata")
    ap.add_argument("--deger", metavar="PAROLA",
                    help="atanacak parola (verilmezse güçlü bir tane üretilir)")
    ap.add_argument("--admin", action="store_true",
                    help="--parola ile birlikte: hesabı yönetici yap ve aç")
    ap.add_argument("--kilidi-ac", metavar="KULLANICI", dest="kilidi_ac",
                    help="hatalı denemeler yüzünden kilitlenen hesabı açar")
    ap.add_argument("--kisi", metavar="AD",
                    help="--parola ile: kullanıcı adı yoksa bu personele verilir")
    args = ap.parse_args()

    from app.database import SessionLocal  # noqa: E402
    from app.ortam_uyari import uyar  # noqa: E402

    uyar()
    db = SessionLocal()
    try:
        hesaplar = hesaplari_listele(db)

        if args.kilidi_ac:
            kisi = db.scalar(select(User).where(User.username == args.kilidi_ac))
            if kisi is None:
                print(f"\n{S}'{args.kilidi_ac}' adında bir hesap yok.{N}")
                return 1
            kalan = kilit_kalan_saniye(kisi)
            kisi.basarisiz_giris = 0
            kisi.kilit_bitis = None
            db.commit()
            print(f"\n{Y}✓ {kisi.username} hesabının kilidi açıldı"
                  f"{f' ({(kalan + 59) // 60} dk kalmıştı)' if kalan else ''}.{N}")
            return 0

        if not args.parola:
            if not hesaplar:
                print(f"\n{S}Giriş yapabilen hesap yok.{N}")
                print("  Yönetici açmak için:")
                print("  ./.venv/bin/python scripts/create_admin.py "
                      "--username admin --password 'GucluParola'")
                return 0
            print(f"\n{M}Giriş hesapları ({len(hesaplar)}){N}")
            print(f"  {'KULLANICI ADI':<22}{'AD SOYAD':<28}{'YETKİ':<14}DURUM")
            for k in hesaplar:
                ad = " ".join(filter(None, [k.first_name, k.last_name])) or "—"
                kalan = kilit_kalan_saniye(k)
                if not k.active:
                    durum = f"{S}KAPALI{N}"
                elif kalan:
                    durum = f"{S}KİLİTLİ ({(kalan + 59) // 60} dk){N}"
                else:
                    durum = f"{Y}etkin{N}"
                print(f"  {k.username:<22}{ad:<28}{k.role.value:<14}{durum}")
            print(f"\n  Parola atamak için: ./.venv/bin/python "
                  f"scripts/hesap-yonet.py --parola {hesaplar[0].username}")
            return 0

        kisi = db.scalar(select(User).where(User.username == args.parola))
        yeni_kadi = False
        if kisi is None and args.kisi:
            adaylar = kisi_ara(db, args.kisi)
            if not adaylar:
                print(f"\n{S}'{args.kisi}' aramasıyla personel bulunamadı.{N}")
                return 1
            if len(adaylar) > 1 and not any(
                    _sadelestir(" ".join(filter(None, [a.first_name, a.last_name])))
                    == _sadelestir(args.kisi) for a in adaylar):
                print(f"\n{S}'{args.kisi}' birden çok kişiyle eşleşti — "
                      f"daha belirgin yazın:{N}")
                for a in adaylar[:15]:
                    ad = " ".join(filter(None, [a.first_name, a.last_name]))
                    print(f"  · {ad}"
                          + (f"  (kullanıcı adı: {a.username})" if a.username else ""))
                return 1
            kisi = adaylar[0]
            if kisi.username and kisi.username != args.parola:
                print(f"\n{S}Bu kişinin kullanıcı adı zaten "
                      f"'{kisi.username}'.{N}")
                print(f"  Parolasını yenilemek için: --parola {kisi.username}")
                return 1
            kisi.username = args.parola
            yeni_kadi = True
        if kisi is None:
            print(f"\n{S}'{args.parola}' adında bir hesap yok.{N}")
            if hesaplar:
                print("  Mevcut kullanıcı adları: "
                      + ", ".join(k.username for k in hesaplar))
            print(f"\n  Kayıtlı bir personele giriş yetkisi vermek için:")
            print(f"  ./.venv/bin/python scripts/hesap-yonet.py "
                  f"--parola {args.parola} --kisi \"Ad Soyad\" --admin")
            return 1

        yeni = args.deger or parola_uret()
        if len(yeni) < 8:
            print(f"\n{S}Parola en az 8 karakter olmalı.{N}")
            return 1

        kisi.password_hash = hash_password(yeni)
        if kilit_kalan_saniye(kisi):
            print(f"\n{S}Not: hesap kilitliydi, kilit kaldırıldı.{N}")
        kisi.basarisiz_giris = 0     # yeni parolayla eski kilit sürmesin
        kisi.kilit_bitis = None
        if args.admin:
            kisi.role = UserRole.admin
            kisi.active = True
        elif not kisi.active:
            kisi.active = True
            print(f"\n{S}Not: hesap kapalıydı, açıldı.{N}")
        db.commit()

        ad = " ".join(filter(None, [kisi.first_name, kisi.last_name])) or "—"
        print(f"\n{Y}✓ {'Giriş yetkisi verildi' if yeni_kadi else 'Parola atandı'}{N}")
        print(f"  Kullanıcı adı : {M}{kisi.username}{N}")
        print(f"  Parola        : {M}{yeni}{N}")
        print(f"  Ad Soyad      : {ad}")
        print(f"  Yetki         : {kisi.role.value}")
        print(f"\n  Bu parolayı güvenli bir yolla iletin; ilk girişten sonra "
              f"Ayarlar → Parola'dan\n  değiştirilmesi önerilir. Ekran "
              f"geçmişinizde kalmasın diye terminali temizleyin.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
