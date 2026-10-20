"""fecha alembic_version para anon/authenticated

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE public.alembic_version FROM anon, authenticated")


def downgrade() -> None:
    pass
