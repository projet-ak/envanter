"""cihaz dosya ekleri (görsel, imzalı zimmet formu)

Revision ID: b1c4a7f20e91
Revises: e7e251e1fd54
Create Date: 2026-08-07 13:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b1c4a7f20e91'
down_revision: Union[str, Sequence[str], None] = 'e7e251e1fd54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TUR_DEGERLERI = ("gorsel", "zimmet_formu", "fatura", "diger")


def _tur_tipi():
    """PostgreSQL'de ENUM tipini önce oluşturur.

    PostgreSQL'de bir ENUM sütunu kullanmadan önce tipin var olması gerekir;
    `checkfirst=True` ile tekrar çalıştırmaya da dayanıklıdır. Diğer
    veritabanlarında (SQLite/MySQL) sa.Enum yeterli.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*TUR_DEGERLERI, name="dosyaturu").create(bind, checkfirst=True)
        return postgresql.ENUM(*TUR_DEGERLERI, name="dosyaturu", create_type=False)
    return sa.Enum(*TUR_DEGERLERI, name="dosyaturu")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'asset_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('tur', _tur_tipi(), nullable=False),
        sa.Column('dosya_adi', sa.String(length=255), nullable=False),
        sa.Column('saklama_adi', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=120), nullable=True),
        sa.Column('boyut', sa.Integer(), nullable=False),
        sa.Column('aciklama', sa.String(length=500), nullable=True),
        sa.Column('yukleyen', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('saklama_adi'),
    )
    with op.batch_alter_table('asset_files', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_asset_files_asset_id'),
                              ['asset_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_asset_files_tur'),
                              ['tur'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('asset_files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_asset_files_tur'))
        batch_op.drop_index(batch_op.f('ix_asset_files_asset_id'))
    op.drop_table('asset_files')

    # PostgreSQL'de ENUM tipi tabloyla birlikte silinmez; kalırsa tekrar
    # upgrade "type already exists" ile patlar.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="dosyaturu").drop(bind, checkfirst=True)
