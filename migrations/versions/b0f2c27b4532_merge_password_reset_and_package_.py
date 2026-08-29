"""merge password reset and package history migrations

Revision ID: b0f2c27b4532
Revises: 6bdf35d9c5ec, e193b5fb1da2
Create Date: 2026-08-28 19:38:35.277131

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b0f2c27b4532'
down_revision = ('6bdf35d9c5ec', 'e193b5fb1da2')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass