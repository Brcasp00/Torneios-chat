"""histórico por rodada/final de fase e adiamento de confrontos

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # matches e standings_snapshots já têm RLS ativo e sem acesso para anon/authenticated (migration 0001).
    op.add_column("matches", sa.Column("postponed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("matches", sa.Column("postponed_reason", sa.Text(), nullable=True))
    op.add_column("matches", sa.Column("postponed_by", sa.BigInteger(), nullable=True))
    op.add_column("matches", sa.Column("postponed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_matches_postponed_by_users", "matches", "users", ["postponed_by"], ["id"], ondelete="SET NULL")

    op.add_column("standings_snapshots", sa.Column("kind", sa.String(12), nullable=False, server_default="change"))
    op.add_column("standings_snapshots", sa.Column("round", sa.SmallInteger(), nullable=True))
    op.create_check_constraint("ck_standings_snapshots_kind_valid", "standings_snapshots", "kind in ('change','round','final')")


def downgrade() -> None:
    op.drop_constraint("ck_standings_snapshots_kind_valid", "standings_snapshots", type_="check")
    op.drop_column("standings_snapshots", "round")
    op.drop_column("standings_snapshots", "kind")
    op.drop_constraint("fk_matches_postponed_by_users", "matches", type_="foreignkey")
    for col in ("postponed_at", "postponed_by", "postponed_reason", "postponed"):
        op.drop_column("matches", col)
