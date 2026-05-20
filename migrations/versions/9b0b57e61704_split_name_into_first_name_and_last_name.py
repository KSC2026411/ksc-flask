"""split name into first_name and last_name

Revision ID: 9b0b57e61704
Revises: 3434e4ad60c2
Create Date: 2026-05-20 17:34:59.468545

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String


# revision identifiers, used by Alembic.
revision = '9b0b57e61704'
down_revision = '3434e4ad60c2'
branch_labels = None
depends_on = None


def upgrade():
    # 1️⃣ Add new columns as nullable first
    op.add_column('user', sa.Column('first_name', sa.String(length=100), nullable=True))
    op.add_column('user', sa.Column('last_name', sa.String(length=100), nullable=True))

    # 2️⃣ Populate new columns from old `name` column
    conn = op.get_bind()
    users = conn.execute(sa.text('SELECT "id", "name" FROM "user"')).fetchall()

    for u in users:
        if u.name and ' ' in u.name:
            first, last = u.name.split(' ', 1)
        else:
            first = u.name or ''
            last = ''
        conn.execute(
            sa.text('UPDATE "user" SET "first_name"=:first, "last_name"=:last WHERE "id"=:id'),
            {"first": first, "last": last, "id": u.id}
        )

    # 3️⃣ Now that all rows have values, make the columns NOT NULL
    op.alter_column('user', 'first_name', nullable=False)
    op.alter_column('user', 'last_name', nullable=False)

    # 4️⃣ Drop the old `name` column if you want
    op.drop_column('user', 'name')


def downgrade():
    # Reverse everything if needed
    op.add_column('user', sa.Column('name', sa.String(length=100), nullable=True))
    conn = op.get_bind()
    users = conn.execute(sa.text('SELECT "id", "first_name", "last_name" FROM "user"')).fetchall()
    for u in users:
        full_name = f"{u.first_name} {u.last_name}".strip()
        conn.execute(
            sa.text('UPDATE "user" SET "name"=:name WHERE "id"=:id'),
            {"name": full_name, "id": u.id}
        )
    op.drop_column('user', 'first_name')
    op.drop_column('user', 'last_name')

    # ### end Alembic commands ###
