"""pote (cabeça de chave) do jogador no torneio

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tournament_players já tem RLS ativo e sem acesso para anon/authenticated (migration 0001).
    op.add_column("tournament_players", sa.Column("pot", sa.SmallInteger(), nullable=True))
    op.create_check_constraint("ck_tournament_players_pot_valid", "tournament_players", "pot is null or (pot >= 1 and pot <= 8)")


def downgrade() -> None:
    op.drop_constraint("ck_tournament_players_pot_valid", "tournament_players", type_="check")
    op.drop_column("tournament_players", "pot")
