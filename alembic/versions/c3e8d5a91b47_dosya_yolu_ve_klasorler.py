"""dosya eklerini klasörlere ayır (saklama_adi -> yol)

Dosyalar tek bir düz klasördeydi ve veritabanında yalnızca dosya adı vardı.
Artık türe ve aya göre alt klasörler kullanılıyor; veritabanında göreli yol
saklanıyor. Bu göç sütunu dönüştürür ve **diskteki mevcut dosyaları da**
yeni yerlerine taşır.

Revision ID: c3e8d5a91b47
Revises: b1c4a7f20e91
Create Date: 2026-08-07 17:05:00.000000

"""
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3e8d5a91b47'
down_revision: Union[str, Sequence[str], None] = 'b1c4a7f20e91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tür -> klasör (app/routers/dosyalar.py ile aynı olmalı)
KLASORLER = {
    "gorsel": "gorseller",
    "zimmet_formu": "belgeler",
    "fatura": "faturalar",
    "diger": "belgeler",
}


def _yil_ay(deger) -> str:
    """created_at'tan "YYYY/MM" üretir.

    Sürücüye göre datetime ya da metin gelebilir (SQLite ham sorguda metin
    döndürür). Çözülemezse boş döner; dosya tür klasörünün köküne konur.
    """
    if hasattr(deger, "year"):
        return f"{deger.year}/{deger.month:02d}"
    metin = str(deger or "")
    if len(metin) >= 7 and metin[4] == "-":
        return f"{metin[:4]}/{metin[5:7]}"
    return ""


def _yukleme_dizini() -> Path:
    """Ayarlardaki yükleme klasörü. Ayarlar okunamazsa varsayılana düşer."""
    try:
        from app.config import settings
        return Path(settings.upload_dir)
    except Exception:
        return Path("yuklemeler")


def _dosyalari_tasi(satirlar, ileri: bool) -> None:
    """Diskteki dosyaları düz klasörle alt klasörler arasında taşır.

    Taşıma başarısız olursa (dosya yok, izin yok) sessizce geçilir: veritabanı
    tutarlılığı dosya sisteminden daha önemli, eksik dosya zaten 404 verir.
    """
    kok = _yukleme_dizini()
    for eski, yeni in satirlar:
        kaynak, hedef = (kok / eski, kok / yeni) if ileri else (kok / eski, kok / yeni)
        try:
            if kaynak.exists() and not hedef.exists():
                hedef.parent.mkdir(parents=True, exist_ok=True)
                kaynak.rename(hedef)
        except OSError:
            pass


def upgrade() -> None:
    """Upgrade schema."""
    baglanti = op.get_bind()

    # 1) Yeni sütun (önce nullable — mevcut satırlar doldurulacak)
    with op.batch_alter_table('asset_files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('yol', sa.String(length=500), nullable=True))

    # 2) Mevcut kayıtlar için göreli yol üret: <klasör>/<yıl>/<ay>/<dosya adı>
    kayitlar = baglanti.execute(sa.text(
        "SELECT id, tur, saklama_adi, created_at FROM asset_files"
    )).all()
    tasinacak = []
    for kid, tur, saklama_adi, olusturma in kayitlar:
        tur_adi = getattr(tur, "value", tur) or "diger"
        klasor = KLASORLER.get(str(tur_adi), "belgeler")
        yil_ay = _yil_ay(olusturma)
        yeni = f"{klasor}/{yil_ay}/{saklama_adi}" if yil_ay else f"{klasor}/{saklama_adi}"
        baglanti.execute(
            sa.text("UPDATE asset_files SET yol = :yol WHERE id = :id"),
            {"yol": yeni, "id": kid},
        )
        tasinacak.append((saklama_adi, yeni))

    _dosyalari_tasi(tasinacak, ileri=True)

    # 3) Eski sütunu bırak, yeniyi zorunlu yap
    with op.batch_alter_table('asset_files', schema=None) as batch_op:
        batch_op.alter_column('yol', existing_type=sa.String(length=500),
                              nullable=False)
        batch_op.create_unique_constraint('uq_asset_files_yol', ['yol'])
        batch_op.drop_column('saklama_adi')


def downgrade() -> None:
    """Downgrade schema."""
    baglanti = op.get_bind()

    with op.batch_alter_table('asset_files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('saklama_adi', sa.String(length=255),
                                      nullable=True))

    kayitlar = baglanti.execute(sa.text("SELECT id, yol FROM asset_files")).all()
    tasinacak = []
    for kid, yol in kayitlar:
        ad = Path(yol).name
        baglanti.execute(
            sa.text("UPDATE asset_files SET saklama_adi = :ad WHERE id = :id"),
            {"ad": ad, "id": kid},
        )
        tasinacak.append((yol, ad))

    _dosyalari_tasi(tasinacak, ileri=False)

    with op.batch_alter_table('asset_files', schema=None) as batch_op:
        batch_op.alter_column('saklama_adi', existing_type=sa.String(length=255),
                              nullable=False)
        batch_op.create_unique_constraint('uq_asset_files_saklama_adi',
                                          ['saklama_adi'])
        batch_op.drop_constraint('uq_asset_files_yol', type_='unique')
        batch_op.drop_column('yol')
