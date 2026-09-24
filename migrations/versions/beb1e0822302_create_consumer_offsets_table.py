"""create consumer offsets table

Revision ID: beb1e0822302
Revises: 76d283d4db3d
Create Date: 2026-09-23 21:23:38.425540

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'beb1e0822302'
down_revision: Union[str, Sequence[str], None] = '76d283d4db3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
def upgrade() -> None:
    op.create_table(
        "consumer_offsets",
        sa.Column(
            "consumer_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "last_processed_event_seq",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.Text(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("consumer_id"),
        sa.CheckConstraint(
            "last_processed_event_seq >= 0",
            name="ck_consumer_offsets_last_processed_event_seq",
        ),
    )


def downgrade() -> None:
    op.drop_table("consumer_offsets")