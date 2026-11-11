"""draft: lote de Pokémon do torneio, clubes e movimentações de dinheiro

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_TABLES = ["draft_pokemon", "draft_clubs", "draft_transactions"]
JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "draft_pokemon",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("species_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("draft_tier", sa.String(length=10), nullable=True),
        sa.Column("price", sa.BigInteger(), nullable=True),
        sa.Column("positions", JSON, nullable=True),
        sa.Column("costs", JSON, nullable=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=True),
        sa.Column("contract_price", sa.BigInteger(), nullable=True),
        sa.Column("acquired_via", sa.String(length=16), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], name=op.f("fk_draft_pokemon_tournament_id_tournaments"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_draft_pokemon_owner_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_draft_pokemon")),
        sa.UniqueConstraint("tournament_id", "species_id", name="uq_draft_pokemon_tournament_species"),
    )
    op.create_index(op.f("ix_draft_pokemon_tournament_id"), "draft_pokemon", ["tournament_id"])
    op.create_index(op.f("ix_draft_pokemon_owner_id"), "draft_pokemon", ["owner_id"])

    op.create_table(
        "draft_clubs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("sponsors", JSON, nullable=True),
        sa.Column("ct_level", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], name=op.f("fk_draft_clubs_tournament_id_tournaments"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_draft_clubs_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_draft_clubs")),
        sa.UniqueConstraint("tournament_id", "user_id", name="uq_draft_clubs_tournament_user"),
    )
    op.create_index(op.f("ix_draft_clubs_tournament_id"), "draft_clubs", ["tournament_id"])
    op.create_index(op.f("ix_draft_clubs_user_id"), "draft_clubs", ["user_id"])

    op.create_table(
        "draft_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("pokemon_id", sa.BigInteger(), nullable=True),
        sa.Column("round", sa.SmallInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], name=op.f("fk_draft_transactions_tournament_id_tournaments"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_draft_transactions_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pokemon_id"], ["draft_pokemon.id"], name=op.f("fk_draft_transactions_pokemon_id_draft_pokemon"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_draft_transactions_created_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_draft_transactions")),
    )
    op.create_index("ix_draft_transactions_tournament_user", "draft_transactions", ["tournament_id", "user_id"])
    op.create_index(op.f("ix_draft_transactions_pokemon_id"), "draft_transactions", ["pokemon_id"])

    # Regra do projeto: o FastAPI é o único acesso; a API REST pública do Supabase fica fechada.
    for table in _TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE public."{table}" FROM anon, authenticated')


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)
