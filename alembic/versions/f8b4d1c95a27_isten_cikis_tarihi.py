"""personelde işten çıkış tarihi

Revision ID: f8b4d1c95a27
Revises: e5b2c8d43f19
Create Date: 2026-08-08 18:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f8b4d1c95a27'
down_revision: Union[str, Sequence[str], None] = 'e5b2c8d43f19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('isten_cikis', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('isten_cikis')
