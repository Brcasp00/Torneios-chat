"""prazo das rodadas: empate automático e liberação do prazo em matches

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # matches já tem RLS ativo e sem acesso para anon/authenticated (migration 0001).
    op.add_column("matches", sa.Column("auto_result", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("matches", sa.Column("deadline_waived", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("matches", "deadline_waived")
    op.drop_column("matches", "auto_result")
