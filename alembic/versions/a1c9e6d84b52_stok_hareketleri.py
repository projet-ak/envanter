"""stok hareketleri: giriş (+) ve kişiye zimmet (−) kayıtları

Klavye/fare gibi hep aynı kalemler alınıp dağıtılıyor; `qty` yalnızca kalanı
söyler. Bu tablo her hareketi tutar: kim, ne zaman, kaç adet. Sahip, dosya
eklerindeki gibi `kayit_turu + kayit_id` (yabancı anahtar yok); temizlik
uygulamadaki `after_delete` dinleyicisiyle.

Revision ID: a1c9e6d84b52
Revises: f8b4d1c95a27
Create Date: 2026-08-09 10:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1c9e6d84b52'
down_revision: Union[str, Sequence[str], None] = 'f8b4d1c95a27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STOK_DEGERLERI = ("accessory", "consumable", "component", "license")
HAREKET_DEGERLERI = ("giris", "zimmet")


def _enum(degerler, ad: str):
    """PostgreSQL'de ENUM tipini gerektiğinde oluşturur.

    `stokturu` stok dosya ekleriyle ORTAK olduğu için checkfirst yeniden
    yaratmaz; `hareketturu` bu göçle gelir.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*degerler, name=ad).create(bind, checkfirst=True)
        return postgresql.ENUM(*degerler, name=ad, create_type=False)
    return sa.Enum(*degerler, name=ad)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'stock_moves',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kayit_turu', _enum(STOK_DEGERLERI, 'stokturu'),
                  nullable=False),
        sa.Column('kayit_id', sa.Integer(), nullable=False),
        sa.Column('islem', _enum(HAREKET_DEGERLERI, 'hareketturu'),
                  nullable=False),
        sa.Column('adet', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('aciklama', sa.String(length=500), nullable=True),
        sa.Column('yapan', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    with op.batch_alter_table('stock_moves', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_stock_moves_kayit_turu'),
                              ['kayit_turu'], unique=False)
        batch_op.create_index(batch_op.f('ix_stock_moves_kayit_id'),
                              ['kayit_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_stock_moves_islem'),
                              ['islem'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('stock_moves', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stock_moves_islem'))
        batch_op.drop_index(batch_op.f('ix_stock_moves_kayit_id'))
        batch_op.drop_index(batch_op.f('ix_stock_moves_kayit_turu'))
    op.drop_table('stock_moves')
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # `hareketturu` yalnızca bu tabloda; `stokturu` dosya ekleriyle kalır.
        sa.Enum(*HAREKET_DEGERLERI, name="hareketturu").drop(bind,
                                                             checkfirst=True)
