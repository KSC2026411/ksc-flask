"""Update user model

Revision ID: a0bd8b37cd8f
Revises: 9b0b57e61704
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a0bd8b37cd8f"
down_revision = "9b0b57e61704"
branch_labels = None
depends_on = None


def upgrade():

    # --------------------------------
    # FIX EXISTING NULL VALUES
    # --------------------------------
    op.execute(
        """
        UPDATE "user"
        SET failed_attempts = 0
        WHERE failed_attempts IS NULL
        """
    )

    op.execute(
        """
        UPDATE "user"
        SET role = 'customer'
        WHERE role IS NULL
        """
    )

    op.execute(
        """
        UPDATE "user"
        SET active = true
        WHERE active IS NULL
        """
    )

    with op.batch_alter_table("user", schema=None) as batch_op:

        # --------------------------------
        # ACTIVE COLUMN FIX
        # --------------------------------
        batch_op.alter_column(
            "active",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text("true")
        )

        # --------------------------------
        # CREATED_AT
        # --------------------------------
        batch_op.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP")
            )
        )

        # --------------------------------
        # UPDATED_AT
        # --------------------------------
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP")
            )
        )

        # --------------------------------
        # FAILED ATTEMPTS FIX
        # --------------------------------
        batch_op.alter_column(
            "failed_attempts",
            existing_type=sa.Integer(),
            nullable=False,
            server_default="0"
        )

        # --------------------------------
        # ROLE FIX
        # --------------------------------
        batch_op.alter_column(
            "role",
            existing_type=sa.String(length=20),
            nullable=False,
            server_default="customer"
        )


def downgrade():

    with op.batch_alter_table("user", schema=None) as batch_op:

        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")

        batch_op.alter_column(
            "role",
            existing_type=sa.String(length=20),
            nullable=True,
            server_default=None
        )

        batch_op.alter_column(
            "failed_attempts",
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None
        )

        batch_op.alter_column(
            "active",
            existing_type=sa.Boolean(),
            nullable=True,
            server_default=None
        )