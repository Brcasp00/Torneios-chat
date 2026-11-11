"""mando de campo: mandante do confronto e escolhas dele (formato, md3, teto de empate, chat)

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # matches já tem RLS ativo e sem acesso para anon/authenticated (migration 0001).
    op.add_column("matches", sa.Column("home", sa.SmallInteger(), nullable=True))
    op.add_column("matches", sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "settings")
    op.drop_column("matches", "home")
