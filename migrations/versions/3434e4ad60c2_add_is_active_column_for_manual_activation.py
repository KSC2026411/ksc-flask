from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3434e4ad60c2'
down_revision = '9cd1a823f595'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        'user',
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false()
        )
    )
    op.alter_column('user', 'is_active', server_default=None)

def downgrade():
    op.drop_column('user', 'is_active')