"""personel dahili numarası (telefon rehberi)

Santral dahili numarası kişinin künyesinde tutulur; cep/sabit telefondan
ayrıdır ve telefon rehberi ile aramada bu alan kullanılır.

Revision ID: d3f6b8c04e19
Revises: c5a2e7b31d84
Create Date: 2026-09-04 13:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd3f6b8c04e19'
down_revision: Union[str, Sequence[str], None] = 'c5a2e7b31d84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('dahili', sa.String(length=20), nullable=True))
    op.create_index(op.f('ix_users_dahili'), 'users', ['dahili'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_dahili'), table_name='users')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('dahili')
