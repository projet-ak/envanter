"""lokasyon rengi: arayüzde ayırt edici #RRGGBB

Revision ID: b2d7f3a91c64
Revises: a1c9e6d84b52
Create Date: 2026-08-10 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2d7f3a91c64'
down_revision: Union[str, Sequence[str], None] = 'a1c9e6d84b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('locations', sa.Column('renk', sa.String(length=7),
                                         nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_column('renk')
