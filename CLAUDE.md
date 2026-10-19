# CLAUDE.md — Plataforma de Torneios Pokémon

> Documento vivo. **Ao concluir cada fase, atualize as seções "Estado atual", "Histórico de fases" e "Próxima fase" antes de seguir adiante.**

## Regras de trabalho (obrigatórias)

1. **Back-end → GitHub automaticamente.** Toda modificação feita no back-end (`backend/`) deve ser commitada e enviada (`git push`) para a branch **`Back-end`** de https://github.com/Brcasp00/Torneios-chat (atenção: o nome real da branch tem **B maiúsculo**: `Back-end`). Faça isso sem precisar pedir confirmação, ao final de cada conjunto coerente de mudanças (e sempre ao fechar uma fase), com os testes passando.
2. **Front-end → branch `front-end`.** Toda modificação no front-end vai para a branch **`front-end`** (https://github.com/Brcasp00/Torneios-chat/tree/front-end). Nunca misture código de front-end na branch `Back-end` nem o contrário. Para trabalhar nas duas sem trocar de branch, use um worktree: `git worktree add D:\Projetos\frontend front-end` (a pasta `frontend/` já está no `.gitignore` da branch `Back-end`).
3. **Segredos nunca vão para o Git.** `backend/.env` (DATABASE_URL, JWT_SECRET) é ignorado. Antes de cada commit, confira `git status`/`git diff --cached` e não deixe passar `.env`, `*.db`, `.venv/`. Nunca imprima a senha do banco nem cole a connection string em respostas/logs.
4. **Testes antes de commitar:** `cd backend; .\.venv\Scripts\python -m pytest` deve passar.
5. **Mensagens de commit** em português, no imperativo, com prefixo da fase quando fizer sentido (ex.: `Fase 4: gera chaveamento do mata-mata`), terminando com a linha `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
6. **Toda tabela nova** (migration) deve repetir `ENABLE ROW LEVEL SECURITY` + `REVOKE ALL ... FROM anon, authenticated` (ver `alembic/versions/0001_*.py`). O FastAPI é o único acesso ao banco; a API REST pública do Supabase deve permanecer fechada.
7. **Não escreva arquivos de código com `Set-Content`/`Add-Content` do PowerShell 5.1** (corrompe acentos). Use as ferramentas Write/Edit, ou Python com `encoding="utf-8"`.
8. **Idioma:** conversa, mensagens de erro da API e comentários em português.

## Contexto do projeto

O usuário organiza, com amigos, torneios de **Pokémon competitivo** (maioria das partidas no **Pokémon Showdown**) e quer uma plataforma própria. Escala pequena (dezenas de usuários). Visualização **pública**; ações exigem login. Interface em português.

- **Back-end:** FastAPI + SQLAlchemy 2 (async) + Alembic. **Banco:** Supabase (Postgres, plano gratuito). Não usamos Supabase Auth nem a API REST do Supabase: autenticação própria (nome + senha, argon2, JWT).
- **Front-end:** ainda não iniciado. Será básico (o design será discutido depois).
- **Repositório:** https://github.com/Brcasp00/Torneios-chat — branches `Back-end`, `front-end`, `main`. Raiz local: `D:\Projetos` (pasta `backend/` dentro).
- Possível futuro: notificações no Discord (a avaliar).

### Ambiente
- Windows 11, PowerShell. Python via `py` (3.14). Venv em `backend/.venv` (`cd D:\Projetos\backend; .\.venv\Scripts\Activate.ps1`).
- `backend/.env`: `DATABASE_URL` (Session/Transaction pooler do Supabase, **porta 6543**, sem colchetes na senha) e `JWT_SECRET`. As migrations trocam automaticamente para a porta **5432**.
- Skills Supabase instaladas (`supabase`, `supabase-postgres-best-practices`): consultar antes de mexer em schema/RLS.

## Papéis e permissões

| Papel | Pode |
|---|---|
| `admin` | Tudo: promover usuários, resetar senhas, desativar contas, gerenciar qualquer torneio, validar/corrigir/invalidar resultados |
| `organizer` | Criar torneios e gerenciar **apenas os que criou** (inscrever jogadores, sortear, validar resultados) |
| `player` | Reportar resultado dos **próprios** confrontos, desistir, alterar a própria senha. Não se inscreve sozinho (só o admin/organizador insere) |
| anônimo | Ver torneios, tabelas, chaveamentos, confrontos, histórico |

Admin não pode rebaixar nem desativar a si mesmo. Admin reseta a senha (não há e-mail). Cadastro aberto a qualquer pessoa (vira `player`). O primeiro admin é criado por `python -m app.scripts.create_admin "Nome"`.

## Regras de negócio decididas com o usuário

- **Torneio = sequência de fases** (`stages`) + **regras de passagem** (`advancement_rules`: "da fase X, posições A–B vão para a fase Y a partir da vaga N / eliminados / repescagem / torneio principal"). Modelos prontos (`league`, `knockout`, `groups_knockout`) só geram fases/regras; `custom` permite montar qualquer coisa (ex.: 20 jogadores → rodada única de 10 confrontos; 6 melhores vencedores por saldo direto ao mata-mata; 4 piores jogam playoff; 2 vencedores completam as 8 vagas).
- **Pontuação:** vitória 3, empate 1, derrota 0. **Desempate:** saldo → vitórias → confronto direto (ordem configurável). **Saldo** = Pokémon vivos do jogador − do adversário; **não conta em melhor de 3** (só em melhor de 1).
- **Melhor de N:** 1, 3, 5 ou 7, configurável por torneio/fase. Em melhor de 1 o vencedor tem ≥1 Pokémon vivo e o perdedor 0.
- **W.O.:** vale vitória por 3×0 (3 de saldo). Se um jogador desiste com o torneio em andamento, todos que ainda iam jogar contra ele (confrontos **sem reporte**) ganham W.O. (3 pontos, +3 de saldo). **Se já havia um reporte pendente antes da desistência, o resultado reportado permanece** (o admin valida normalmente). Jogos já validados não mudam.
- **Reporte:** só um dos dois jogadores do confronto reporta; **o admin/organizador valida** (ou rejeita, lança direto, corrige, invalida). Replay do Showdown obrigatório (`https://replay.pokemonshowdown.com/...`) quando `battle_rules.showdown_required` (padrão). Reporte novo substitui o pendente.
- **Empate:** só se o torneio permitir (`allow_draw`; padrão: liga/grupos sim, mata-mata não). O jogador reporta empate **apenas com placar 0×0**; o admin valida (ou marca `is_draw` num reporte, que vira 0×0).
- **Mata-mata:** eliminação simples, **sem byes** (nº de jogadores potência de 2 no template; casos diferentes via `custom` com fase preliminar), com disputa de 3º lugar opcional.
- **Grupos + mata-mata:** nº de grupos sugerido pelo total de jogadores (~4 por grupo, editável); classificados por grupo configurável; cruzamentos **fixos**; total de vagas no mata-mata potência de 2.
- **Repescagem/subtorneio:** é um torneio filho (`parent_id`), cadastrado como qualquer torneio, **1 nível apenas** (subtorneio não tem subtorneio). Entrada: automática por regra (ex.: "3º de cada grupo", `repechage_position`) ou manual pelo admin. Pode ter **vários vencedores**, que **voltam ao torneio principal** em vagas configuradas de antemão (`parent_tournament` + `parent_stage` + `to_slot_from`). A página do torneio principal lista os subtorneios (botão de acesso).
- **Início do torneio** só via `POST /tournaments/{id}/start` e **com exatamente `max_players` inscritos**. Jogador que desiste antes do início é removido da lista.
- **Histórico:** cada mudança relevante salva um snapshot da tabela (`standings_snapshots`). Admin pode corrigir/invalidar resultados a qualquer momento (irregularidades); tudo é recalculado e registrado em `audit_log`.
- **Regras de batalha:** campos estruturados (`battle_rules`: formato, jogo, tier, team_size, bring, level_cap, timer, clauses, showdown_required) + texto livre (`rules_text`).

## Arquitetura (back-end)

```
backend/
  app/
    main.py                 # FastAPI, CORS, routers
    core/    config.py security.py deps.py   # settings, argon2/JWT, dependências de permissão
    db/      base.py session.py              # Base/naming/JsonType/BigIntPK, engine async (pooler-safe)
    models/  user.py tournament.py           # User, AuditLog | Tournament, Stage, AdvancementRule, TournamentPlayer, Match, MatchReport, StandingsSnapshot
    schemas/ user.py tournament.py match.py  # Pydantic
    api/     auth.py users.py tournaments.py play.py matches.py
    services/ templates.py schedule.py standings.py results.py views.py
    scripts/ create_admin.py
  alembic/versions/  0001_esquema_inicial.py  0002_fechar_alembic_version.py
  tests/   conftest.py test_auth_users.py test_tournaments.py test_play.py   # SQLite em memória
```

- Testes usam **SQLite** (`JsonType` → JSON; `BigIntPK` → INTEGER). Nunca apontam para o banco real.
- A tabela é **sempre recalculada** a partir dos confrontos `validated` (`services/standings.py`), não armazenada; os snapshots são só histórico.
- Concorrência: confrontos são carregados com `FOR UPDATE` nas ações de resultado.

### Endpoints atuais (docs interativa em `/docs`)
- **auth:** `POST /auth/register|login|change-password`, `GET /auth/me`
- **users:** `GET /users` (público: id+nome), `GET /users/admin`, `POST /users/{id}/reset-password`, `PATCH /users/{id}/role|active`
- **tournaments:** `GET /tournaments`, `GET /tournaments/{id}` (detalhe completo: fases, regras, jogadores, subtorneios, `can_manage`), `POST /tournaments`, `POST /tournaments/{id}/subtournaments`, `PATCH /tournaments/{id}`, `PATCH /tournaments/{id}/status`, `DELETE /tournaments/{id}`, `GET|POST /tournaments/{id}/players`, `DELETE /tournaments/{id}/players/{user_id}`, `POST /tournaments/{id}/withdraw`
- **play:** `POST /tournaments/{id}/draw` (prévia do sorteio, com `seed`), `POST /tournaments/{id}/start`, `GET /tournaments/{id}/matches|standings|history`, `GET /tournaments/{id}/history/{snapshot_id}`
- **matches:** `GET /matches/{id}`, `POST /matches/{id}/report|validate|reject|result|walkover|invalidate`

## Estado atual

**Concluído:** Fases 1, 2 e 3 (autenticação, torneios/fases/regras/inscrição/subtorneios, pontos corridos completo). 43 testes passando. Migrations 0001–0002 aplicadas no Supabase.
**Só funciona de ponta a ponta:** formato `league`. `knockout`, `groups_knockout` e `custom` já podem ser **cadastrados**, mas `/draw` e `/start` retornam 409 ("ainda não implementado") — `SUPPORTED_TEMPLATES` em `app/api/play.py`.

## Histórico de fases

- **Fase 1 — Fundação:** projeto FastAPI/Alembic, conexão com o Supabase via pooler, modelo de dados completo (9 tabelas) com RLS ativo e sem acesso para `anon`/`authenticated`, cadastro/login (JWT), papéis, reset de senha pelo admin, auditoria, script `create_admin`.
- **Fase 2 — Torneios:** CRUD, modelos prontos (liga, mata-mata, grupos+mata-mata) e `custom`, regras de passagem, inscrição de jogadores (só staff), desistência, máquina de status, subtorneios (1 nível) com retorno ao principal, páginas de leitura públicas.
- **Fase 3 — Pontos corridos:** round-robin (turno/returno opcional) com sorteio por seed e prévia, `/start`, página do confronto, reporte do jogador com replay do Showdown, validação/rejeição/correção/invalidação/W.O. pelo admin, tabela com saldo/vitórias/confronto direto, W.O. automático na desistência (reportes pendentes permanecem), histórico de tabelas, encerramento/reabertura automática do torneio. Empate só como 0×0.

## Próxima fase — Fase 4: mata-mata

1. Gerar o chaveamento de eliminação simples a partir do sorteio (potência de 2, sem byes): `Match.round`, `slot`, `next_match_id`/`next_slot`.
2. Ao validar um confronto, o vencedor avança automaticamente para a próxima partida; semifinal → final (+ disputa de 3º lugar opcional).
3. Resultado de mata-mata não admite empate. Melhor de N por fase.
4. Desistência/W.O. dentro do chaveamento (o adversário avança). Correção/invalidação de resultado já validado deve desfazer em cascata o avanço (só se a partida seguinte ainda não foi jogada; senão exigir invalidar a seguinte antes).
5. Endpoint de leitura do chaveamento (`GET /tournaments/{id}/bracket`) para o front desenhar a árvore; snapshots no histórico.
6. Habilitar `knockout` em `SUPPORTED_TEMPLATES` e cobrir com testes (inclui desistência e invalidação em cascata).

## Roadmap restante

- **Fase 5 — Grupos + mata-mata:** sorteio dos grupos (por seed), tabela por grupo, classificados alimentam o mata-mata com cruzamentos fixos; executar regras de passagem genéricas (inclui o cenário `custom` dos 20 jogadores: rodada única, ranking dos vencedores por saldo, playoff, mata-mata de 8).
- **Fase 6 — Sorteador avançado:** sorteio por potes/seeds, registro do sorteio, redistribuição manual pelo admin antes de confirmar.
- **Fase 7 — Subtorneios na prática:** entrada automática por regra (ex.: 3º de cada grupo vai à repescagem) ou manual; retorno dos vencedores às vagas configuradas do torneio principal.
- **Fase 8 — Histórico e auditoria:** consulta do histórico de tabelas/resultados por torneio, filtros do `audit_log`.
- **Fase 9 — Front-end básico** (branch `front-end`): login/cadastro, lista de torneios, página do torneio (info + tabela/chaveamento + botão do subtorneio), página do confronto com reporte, painel do admin. Tempo real por polling (ou WebSocket).
- **Fase 10 — Polimento e deploy:** hospedagem da API e do front, CORS, variáveis de ambiente, documentação; avaliar notificações no Discord.

## Perguntas em aberto / ideias
- Notificações via Discord (webhook/bot): "interessante, verificar viabilidade depois".
- Personalizações adicionais de formato: o usuário prometeu pedir depois.
- Design do front-end: a discutir.

## Comandos úteis (PowerShell, em `D:\Projetos\backend`)
```
.\.venv\Scripts\python -m pytest                          # testes
.\.venv\Scripts\alembic upgrade head                      # aplicar migrations
.\.venv\Scripts\alembic revision --autogenerate -m "msg"  # nova migration (revisar! lembrar do RLS)
.\.venv\Scripts\python -m app.scripts.create_admin "Nome" # criar/promover admin
.\.venv\Scripts\uvicorn app.main:app --reload             # API em http://localhost:8000 (docs em /docs)
```
