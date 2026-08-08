"""kişi dosya ekleri (imzalı zimmet formu kişiye bağlanır)

Zimmet formu tek bir cihaza değil kişiye aittir: bir form o kişinin birden çok
cihazını listeler. Snipe-IT'te de dosyaların çoğu (171/208) kişiye bağlıydı.

Revision ID: d4f1a6c72e83
Revises: c3e8d5a91b47
Create Date: 2026-08-08 09:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4f1a6c72e83'
down_revision: Union[str, Sequence[str], None] = 'c3e8d5a91b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TUR_DEGERLERI = ("gorsel", "zimmet_formu", "fatura", "diger")


def _tur_tipi():
    """`dosyaturu` ENUM'u cihaz ekleriyle ORTAK — PostgreSQL'de yeniden
    oluşturulmaz, var olan tip kullanılır."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*TUR_DEGERLERI, name="dosyaturu").create(bind, checkfirst=True)
        return postgresql.ENUM(*TUR_DEGERLERI, name="dosyaturu", create_type=False)
    return sa.Enum(*TUR_DEGERLERI, name="dosyaturu")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tur', _tur_tipi(), nullable=False),
        sa.Column('dosya_adi', sa.String(length=255), nullable=False),
        sa.Column('yol', sa.String(length=500), nullable=False),
        sa.Column('content_type', sa.String(length=120), nullable=True),
        sa.Column('boyut', sa.Integer(), nullable=False),
        sa.Column('aciklama', sa.String(length=500), nullable=True),
        sa.Column('yukleyen', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('yol'),
    )
    with op.batch_alter_table('user_files', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_files_user_id'),
                              ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_files_tur'),
                              ['tur'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('user_files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_files_tur'))
        batch_op.drop_index(batch_op.f('ix_user_files_user_id'))
    op.drop_table('user_files')
    # `dosyaturu` tipi cihaz ekleri tarafından da kullanılıyor: silinmez.
