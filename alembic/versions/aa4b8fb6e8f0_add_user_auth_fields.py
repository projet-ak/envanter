"""add user auth fields

Revision ID: aa4b8fb6e8f0
Revises: 4045f1e83d90
Create Date: 2026-06-11 21:21:35.358225

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'aa4b8fb6e8f0'
down_revision: Union[str, Sequence[str], None] = '4045f1e83d90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROL_DEGERLERI = ('admin', 'editor', 'viewer')


def _rol_tipi():
    """Rol sütununun tipini üretir.

    PostgreSQL'de ENUM ayrı bir veritabanı nesnesidir ve sütun eklemeden ÖNCE
    açıkça oluşturulmalıdır (`create_table` bunu kendi yapar, `add_column`
    yapmaz). SQLite'ta enum yalnızca metin + CHECK olduğu için bu adım gerekmez.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Tip zaten varsa hata vermeden geç (script tekrar çalıştırılabilsin)
        sa.Enum(*ROL_DEGERLERI, name="userrole").create(bind, checkfirst=True)
        # create_type=False: tipi yukarıda oluşturduk, tekrar oluşturma
        return postgresql.ENUM(*ROL_DEGERLERI, name="userrole", create_type=False)
    return sa.Enum(*ROL_DEGERLERI, name="userrole")


def upgrade() -> None:
    """Upgrade schema."""
    rol_tipi = _rol_tipi()
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('password_hash', sa.String(length=255), nullable=True))
        # server_default: mevcut kullanıcı satırları için varsayılan rol ('viewer').
        batch_op.add_column(sa.Column('role', rol_tipi, nullable=False,
                                      server_default='viewer'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('role')
        batch_op.drop_column('password_hash')

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="userrole").drop(bind, checkfirst=True)
