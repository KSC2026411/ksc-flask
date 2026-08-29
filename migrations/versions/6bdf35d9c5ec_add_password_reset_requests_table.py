"""add password reset requests table

Revision ID: 6bdf35d9c5ec

Revises: 4e35950359eb

Create Date: 2026-08-28 18:32:01.974499

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6bdf35d9c5ec'

down_revision = '4e35950359eb'

branch_labels = None

depends_on = None


def upgrade():

    op.create_table(
        'password_reset_request',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            sa.String(length=20),
            server_default='pending',
            nullable=False
        ),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('handled_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['user.id']
        ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():

    op.drop_table('password_reset_request')