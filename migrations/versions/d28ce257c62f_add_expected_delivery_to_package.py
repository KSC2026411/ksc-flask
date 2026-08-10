
"""add expected delivery to package

Revision ID: d28ce257c62f
Revises: 8139cd9b7e1e
Create Date: 2026-08-09 23:44:49.030377
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d28ce257c62f"
down_revision = "8139cd9b7e1e"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "package",
        sa.Column("expected_delivery", sa.Date(), nullable=True)
    )

def downgrade():
    op.drop_column("package", "expected_delivery")