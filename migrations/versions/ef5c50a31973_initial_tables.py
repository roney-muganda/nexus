"""initial tables

Revision ID: ef5c50a31973
Revises: 4cafd5baa38f
Create Date: 2026-05-17 13:12:12.201365

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef5c50a31973'
down_revision: Union[str, Sequence[str], None] = '4cafd5baa38f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
