"""giriş deneme sayacı ve geçici hesap kilidi

Art arda hatalı denemelerden sonra hesap belirli süre kilitlenir; sayaç ve
kilit bitişi kullanıcıda tutulur ki sunucu yeniden başlasa da kilit sürsün.

Revision ID: c5a2e7b31d84
Revises: b2d7f3a91c64
Create Date: 2026-08-11 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c5a2e7b31d84'
down_revision: Union[str, Sequence[str], None] = 'b2d7f3a91c64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('basarisiz_giris', sa.Integer(),
                                     nullable=False, server_default='0'))
    op.add_column('users', sa.Column('kilit_bitis', sa.DateTime(timezone=True),
                                     nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('kilit_bitis')
        batch_op.drop_column('basarisiz_giris')
