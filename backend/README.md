# Backend – Plataforma de Torneios Pokémon

FastAPI + SQLAlchemy 2 (async) + Supabase (Postgres) + Alembic.

## Configuração
Crie `.env` nesta pasta (já está no `.gitignore`):

```
DATABASE_URL=postgresql://postgres.<ref>:<SENHA>@aws-1-<regiao>.pooler.supabase.com:6543/postgres
JWT_SECRET=<string longa aleatória>
```
Sem colchetes na senha. As migrations usam automaticamente a porta 5432 do mesmo host.

## Comandos (PowerShell, na pasta backend)
```
.\.venv\Scripts\alembic upgrade head                      # aplicar migrations
.\.venv\Scripts\python -m app.scripts.create_admin "Nome" # criar/promover o primeiro admin
.\.venv\Scripts\uvicorn app.main:app --reload             # subir a API (docs em /docs)
.\.venv\Scripts\python -m pytest                          # testes (SQLite em memória)
```

## Segurança
Todas as tabelas têm RLS ativo e nenhum acesso para `anon`/`authenticated`: só o FastAPI acessa o banco.
Novas migrations que criam tabelas devem repetir `ENABLE ROW LEVEL SECURITY` + `REVOKE ALL ... FROM anon, authenticated`.
