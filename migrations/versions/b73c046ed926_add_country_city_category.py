"""add country city category

Revision ID: b73c046ed926
Revises: bc6117e20c1d   # ← your previous revision ID; leave as-is
Create Date: 2025-06-12 10:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b73c046ed926"
down_revision = "bc6117e20c1d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # add columns with safe server_default so existing rows pass NOT NULL
    with op.batch_alter_table("job_offer") as batch_op:
        batch_op.add_column(
            sa.Column("country", sa.String(80), nullable=False, server_default="Unknown")
        )
        batch_op.add_column(
            sa.Column("city", sa.String(80), nullable=False, server_default="Unknown")
        )
        batch_op.add_column(
            sa.Column("category", sa.String(40), nullable=False, server_default="Other")
        )

    # optional: drop the server_default so future inserts must supply a value
    with op.batch_alter_table("job_offer") as batch_op:
        batch_op.alter_column("country", server_default=None)
        batch_op.alter_column("city",    server_default=None)
        batch_op.alter_column("category",server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("job_offer") as batch_op:
        batch_op.drop_column("category")
        batch_op.drop_column("city")
        batch_op.drop_column("country")
