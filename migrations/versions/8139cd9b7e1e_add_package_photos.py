"""Add package photos

Revision ID: 8139cd9b7e1e
Revises: a0bd8b37cd8f
Create Date: 2026-08-09 15:57:06.695320
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "8139cd9b7e1e"
down_revision = "a0bd8b37cd8f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "package_photo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("delete_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["package.id"]
        ),
        sa.PrimaryKeyConstraint("id")
    )


def downgrade():
    op.drop_table("package_photo")