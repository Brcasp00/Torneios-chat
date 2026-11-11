"""acervo de torneios: séries, entradas do acervo, classificação final e partidas de torneios antigos

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_TABLES = ["series", "archive_entries", "archive_placements", "archive_matches"]


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_series")),
    )
    op.create_index("uq_series_name_lower", "series", [sa.literal_column("lower(name)")], unique=True)

    op.create_table(
        "archive_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("format", sa.String(length=200), nullable=True),
        sa.Column("players_count", sa.Integer(), nullable=True),
        sa.Column("organizer", sa.String(length=80), nullable=True),
        sa.Column("tier", sa.String(length=60), nullable=True),
        sa.Column("rules_text", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("links", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("series_id", sa.BigInteger(), nullable=True),
        sa.Column("edition", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], name=op.f("fk_archive_entries_tournament_id_tournaments"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], name=op.f("fk_archive_entries_series_id_series"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_archive_entries_created_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_archive_entries")),
        sa.UniqueConstraint("tournament_id", name=op.f("uq_archive_entries_tournament_id")),
    )
    op.create_index(op.f("ix_archive_entries_series_id"), "archive_entries", ["series_id"])

    op.create_table(
        "archive_placements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("label", sa.String(length=40), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["archive_entries.id"], name=op.f("fk_archive_placements_entry_id_archive_entries"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_archive_placements_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_archive_placements")),
    )
    op.create_index(op.f("ix_archive_placements_entry_id"), "archive_placements", ["entry_id"])
    op.create_index(op.f("ix_archive_placements_user_id"), "archive_placements", ["user_id"])

    op.create_table(
        "archive_matches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("stage_label", sa.String(length=60), nullable=False),
        sa.Column("number", sa.SmallInteger(), nullable=True),
        sa.Column("player1_user_id", sa.BigInteger(), nullable=True),
        sa.Column("player1_name", sa.String(length=60), nullable=False),
        sa.Column("player2_user_id", sa.BigInteger(), nullable=True),
        sa.Column("player2_name", sa.String(length=60), nullable=False),
        sa.Column("winner", sa.SmallInteger(), nullable=True),
        sa.Column("replay_url", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["entry_id"], ["archive_entries.id"], name=op.f("fk_archive_matches_entry_id_archive_entries"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player1_user_id"], ["users.id"], name=op.f("fk_archive_matches_player1_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["player2_user_id"], ["users.id"], name=op.f("fk_archive_matches_player2_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_archive_matches")),
    )
    op.create_index(op.f("ix_archive_matches_entry_id"), "archive_matches", ["entry_id"])
    op.create_index(op.f("ix_archive_matches_player1_user_id"), "archive_matches", ["player1_user_id"])
    op.create_index(op.f("ix_archive_matches_player2_user_id"), "archive_matches", ["player2_user_id"])

    # Mesma regra das outras tabelas: só o FastAPI acessa o banco; a API pública do Supabase fica fechada.
    for table in _TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated')


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)
