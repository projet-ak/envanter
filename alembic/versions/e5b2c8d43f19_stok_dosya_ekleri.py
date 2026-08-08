"""aksesuar/sarf/bileşen/lisans dosya ekleri

Dört tür için dört tablo yerine tek tablo: sahibi `kayit_turu + kayit_id`.
Yabancı anahtar yok (tek sütun dört tabloya bakamaz); temizlik uygulama
tarafındaki `after_delete` dinleyicisiyle yapılır.

Revision ID: e5b2c8d43f19
Revises: d4f1a6c72e83
Create Date: 2026-08-08 12:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5b2c8d43f19'
down_revision: Union[str, Sequence[str], None] = 'd4f1a6c72e83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TUR_DEGERLERI = ("gorsel", "zimmet_formu", "fatura", "diger")
STOK_DEGERLERI = ("accessory", "consumable", "component", "license")


def _enum(degerler, ad: str, yeni: bool):
    """PostgreSQL'de ENUM tipini gerektiğinde oluşturur.

    `dosyaturu` cihaz/kişi ekleriyle ORTAK olduğu için yeniden yaratılmaz;
    `stokturu` bu göçle gelir.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*degerler, name=ad).create(bind, checkfirst=True)
        return postgresql.ENUM(*degerler, name=ad, create_type=False)
    return sa.Enum(*degerler, name=ad)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'stock_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kayit_turu', _enum(STOK_DEGERLERI, 'stokturu', True),
                  nullable=False),
        sa.Column('kayit_id', sa.Integer(), nullable=False),
        sa.Column('tur', _enum(TUR_DEGERLERI, 'dosyaturu', False), nullable=False),
        sa.Column('dosya_adi', sa.String(length=255), nullable=False),
        sa.Column('yol', sa.String(length=500), nullable=False),
        sa.Column('content_type', sa.String(length=120), nullable=True),
        sa.Column('boyut', sa.Integer(), nullable=False),
        sa.Column('aciklama', sa.String(length=500), nullable=True),
        sa.Column('yukleyen', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('yol'),
    )
    with op.batch_alter_table('stock_files', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_stock_files_kayit_turu'),
                              ['kayit_turu'], unique=False)
        batch_op.create_index(batch_op.f('ix_stock_files_kayit_id'),
                              ['kayit_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_stock_files_tur'),
                              ['tur'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('stock_files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stock_files_tur'))
        batch_op.drop_index(batch_op.f('ix_stock_files_kayit_id'))
        batch_op.drop_index(batch_op.f('ix_stock_files_kayit_turu'))
    op.drop_table('stock_files')
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # `stokturu` yalnızca bu tabloda kullanılıyor; `dosyaturu` kalır.
        sa.Enum(*STOK_DEGERLERI, name="stokturu").drop(bind, checkfirst=True)
