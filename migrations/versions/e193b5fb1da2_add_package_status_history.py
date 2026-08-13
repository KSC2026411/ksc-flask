"""add package status history

Revision ID: e193b5fb1da2
Revises: d28ce257c62f
Create Date: 2026-08-12 18:33:23.505829

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.

revision = "e193b5fb1da2"
down_revision = "d28ce257c62f"
branch_labels = None
depends_on = None


def upgrade():
    # Create containers
    op.create_table(
        "container",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=50), nullable=False),
        sa.Column("carrier", sa.String(length=50), nullable=False),
        sa.Column("booking_number", sa.String(length=100), nullable=True),
        sa.Column("container_number", sa.String(length=100), nullable=True),
        sa.Column("bill_of_lading", sa.String(length=100), nullable=True),
        sa.Column("vessel_name", sa.String(length=255), nullable=True),
        sa.Column("voyage_number", sa.String(length=100), nullable=True),
        sa.Column("origin", sa.String(length=255), nullable=True),
        sa.Column("destination", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference")
    )

    # Create container events
    op.create_table(
        "container_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("container_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("event_code", sa.String(length=100), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_time", sa.DateTime(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["container_id"],
            ["container.id"]
        ),
        sa.PrimaryKeyConstraint("id")
    )

    # Link packages to containers
    op.create_table(
        "package_container",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("container_id", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["container_id"],
            ["container.id"]
        ),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["package.id"]
        ),
        sa.PrimaryKeyConstraint("id")
    )

    # Package status history
    op.create_table(
        "package_status_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["package.id"]
        ),
        sa.PrimaryKeyConstraint("id")
    )


def downgrade():
    # Remove package status history
    op.drop_table("package_status_history")

    # Remove package/container relationships
    op.drop_table("package_container")

    # Remove container events
    op.drop_table("container_event")

    # Remove containers
    op.drop_table("container")