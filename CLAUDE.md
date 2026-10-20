# CLAUDE.md — Plataforma de Torneios Pokémon

> Documento vivo. **Ao concluir cada fase, atualize as seções "Estado atual", "Histórico de fases" e "Próxima fase" antes de seguir adiante.**

## Regras de trabalho (obrigatórias)

1. **Back-end → GitHub automaticamente.** Toda modificação feita no back-end (`backend/`) deve ser commitada e enviada (`git push`) para a branch **`Back-end`** de https://github.com/Brcasp00/Torneios-chat (atenção: o nome real da branch tem **B maiúsculo**: `Back-end`). Faça isso sem precisar pedir confirmação, ao final de cada conjunto coerente de mudanças (e sempre ao fechar uma fase), com os testes passando.
2. **`main` = produção.** A `main` só recebe código por **merge/Pull Request de `Back-end` (e `front-end`) feito quando o usuário pedir**. Nunca dê push direto na `main` por conta própria.
3. **Front-end → branch `front-end`.** Toda modificação no front-end vai para a branch **`front-end`** (https://github.com/Brcasp00/Torneios-chat/tree/front-end). Nunca misture código de front-end na branch `Back-end` nem o contrário. Para trabalhar nas duas sem trocar de branch, use um worktree: `git worktree add D:\Projetos\frontend front-end` (a pasta `frontend/` já está no `.gitignore` da branch `Back-end`).
4. **Segredos nunca vão para o Git.** `backend/.env` (DATABASE_URL, JWT_SECRET) é ignorado. Antes de cada commit, confira `git status`/`git diff --cached` e não deixe passar `.env`, `*.db`, `.venv/`. Nunca imprima a senha do banco nem cole a connection string em respostas/logs.
5. **Testes antes de commitar:** `cd backend; .\.venv\Scripts\python -m pytest` deve passar.
6. **Mensagens de commit** em português, no imperativo, com prefixo da fase quando fizer sentido (ex.: `Fase 4: gera chaveamento do mata-mata`), terminando com a linha `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
7. **Toda tabela nova** (migration) deve repetir `ENABLE ROW LEVEL SECURITY` + `REVOKE ALL ... FROM anon, authenticated` (ver `alembic/versions/0001_*.py`). O FastAPI é o único acesso ao banco; a API REST pública do Supabase deve permanecer fechada.
8. **Não escreva arquivos de código com `Set-Content`/`Add-Content` do PowerShell 5.1** (corrompe acentos). Use as ferramentas Write/Edit, ou Python com `encoding="utf-8"`.
9. **Idioma:** conversa, mensagens de erro da API e comentários em português.

## Contexto do projeto

O usuário organiza, com amigos, torneios de **Pokémon competitivo** (maioria das partidas no **Pokémon Showdown**) e quer uma plataforma própria. Escala pequena (dezenas de usuários). Visualização **pública**; ações exigem login. Interface em português.

- **Back-end:** FastAPI + SQLAlchemy 2 (async) + Alembic. **Banco:** Supabase (Postgres, plano gratuito). Não usamos Supabase Auth nem a API REST do Supabase: autenticação própria (nome + senha, argon2, JWT).
- **Front-end:** ainda não iniciado. Será básico (o design será discutido depois).
- **Repositório:** https://github.com/Brcasp00/Torneios-chat — branches `Back-end`, `front-end`, `main`. Raiz local: `D:\Projetos` (pasta `backend/` dentro).
- Possível futuro: notificações no Discord (a avaliar).

### Ambiente
- Windows 11, PowerShell. Python via `py` (3.14). Venv em `backend/.venv` (`cd D:\Projetos\backend; .\.venv\Scripts\Activate.ps1`).
- `backend/.env`: `DATABASE_URL` (Session/Transaction pooler do Supabase, **porta 6543**, sem colchetes na senha) e `JWT_SECRET`. As migrations trocam automaticamente para a porta **5432**.
- **Deploy (Render, Web Service):** Root Directory `backend`, Build `pip install -r requirements.txt`, Start `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`, Health Check `/health`. Variáveis no painel do Render: `DATABASE_URL`, `JWT_SECRET` (valor próprio de produção), `CORS_ORIGINS` (URL do front), `PYTHON_VERSION` se necessário. Hoje o Render acompanha a branch `Back-end` com auto-deploy; quando o usuário trocar para `main`, a produção só muda após merge na `main`. As migrations rodam no start e alteram o mesmo banco do Supabase usado localmente (cuidado com migrations destrutivas). Plano gratuito: o serviço dorme após ~15 min sem acesso.
- Skills Supabase instaladas (`supabase`, `supabase-postgres-best-practices`): consultar antes de mexer em schema/RLS.

## Papéis e permissões

| Papel | Pode |
|---|---|
| `admin` | Tudo: promover usuários, resetar senhas, desativar contas, gerenciar qualquer torneio, validar/corrigir/invalidar resultados |
| `organizer` | Criar torneios e gerenciar **apenas os que criou** (inscrever jogadores, sortear, validar resultados) |
| `player` | Reportar resultado dos **próprios** confrontos, desistir, alterar a própria senha. Não se inscreve sozinho (só o admin/organizador insere) |
| anônimo | Ver torneios, tabelas, chaveamentos, confrontos, histórico |

Admin não pode rebaixar nem desativar a si mesmo. Admin reseta a senha (não há e-mail). Cadastro aberto a qualquer pessoa (vira `player`). O primeiro admin é criado por `python -m app.scripts.create_admin "Nome"`.

**Senha temporária:** quando o admin cria um usuário sem informar senha, ou redefine a senha sem informar uma nova, o sistema gera uma senha temporária e marca `users.must_change_password` (migration 0005). Enquanto a marca existir, o login funciona, mas toda a API (exceto `GET /auth/me` e `POST /auth/change-password`) devolve 403 com a mensagem de troca obrigatória; ao trocar (a nova deve ser diferente da atual) a marca cai. Senha definida pelo próprio admin não é temporária.

## Regras de negócio decididas com o usuário

- **Torneio = sequência de fases** (`stages`) + **regras de passagem** (`advancement_rules`: "da fase X, posições A–B vão para a fase Y a partir da vaga N / eliminados / repescagem / torneio principal"). Modelos prontos (`league`, `knockout`, `groups_knockout`) só geram fases/regras; `custom` permite montar qualquer coisa (ex.: 20 jogadores → rodada única de 10 confrontos; 6 melhores vencedores por saldo direto ao mata-mata; 4 piores jogam playoff; 2 vencedores completam as 8 vagas).
- **Pontuação:** vitória 3, empate 1, derrota 0. **Desempate:** saldo → vitórias → confronto direto (ordem configurável). **Saldo** = Pokémon vivos do jogador − do adversário; **não conta em melhor de 3** (só em melhor de 1).
- **Melhor de N:** 1, 3, 5 ou 7, configurável por torneio/fase. Em melhor de 1 o vencedor tem ≥1 Pokémon vivo e o perdedor 0.
- **W.O.:** vale vitória por 3×0 (3 de saldo). Se um jogador desiste com o torneio em andamento, todos que ainda iam jogar contra ele (confrontos **sem reporte**) ganham W.O. (3 pontos, +3 de saldo). **Se já havia um reporte pendente antes da desistência, o resultado reportado permanece** (o admin valida normalmente). Jogos já validados não mudam.
- **Reporte:** só um dos dois jogadores do confronto reporta; **o admin/organizador valida** (ou rejeita, lança direto, corrige, invalida). Replay do Showdown obrigatório (`https://replay.pokemonshowdown.com/...`) quando `battle_rules.showdown_required` (padrão). Reporte novo substitui o pendente.
- **Empate:** só se o torneio permitir (`allow_draw`; padrão: liga/grupos sim, mata-mata não). O jogador reporta empate **apenas com placar 0×0**; o admin valida (ou marca `is_draw` num reporte, que vira 0×0).
- **Mata-mata:** eliminação simples, **sem byes** (nº de jogadores potência de 2 no template; casos diferentes via `custom` com fase preliminar), com disputa de 3º lugar opcional (`group_label="3rd"`, alimentada pelos perdedores das semifinais). **Nunca há empate no mata-mata**, mesmo com `allow_draw`. O vencedor validado avança sozinho para `next_match_id`/`next_slot`; só se pode reportar quando os dois jogadores já estão definidos. **Correção/invalidação em cascata:** mudar o vencedor (ou invalidar) de um confronto exige que o seguinte ainda esteja `scheduled`; se já tiver reporte/resultado a API devolve **409** e não grava nada (invalide de trás para frente). Mudar só Pokémon restantes (mesmo vencedor) é sempre permitido. **Desistência no mata-mata:** o adversário vence por W.O. e avança; se o adversário ainda não foi definido, o W.O. é aplicado automaticamente quando ele chegar ao confronto (`settle_withdrawn`). Se os dois desistirem, o confronto fica para o admin resolver (W.O. manual).
- **Grupos + mata-mata:** nº de grupos sugerido pelo total de jogadores (~4 por grupo, editável); classificados por grupo configurável; cruzamentos **fixos**; total de vagas no mata-mata potência de 2. Os jogadores são sorteados nos grupos (A, B, C...) e cada grupo joga todos contra todos (turno/returno opcional). Cruzamento padrão (`services/stages.crossing_order`): grupos pareados A-B, C-D...; posição *i* de um grupo enfrenta a posição inversa do outro (1ºA×2ºB, 1ºB×2ºA), com as chaves intercaladas para que companheiros de grupo só se reencontrem tarde (16 jogadores: A1×B2, C1×D2, A2×B1, C2×D1). Pode ser sobrescrito por `config.crossings` na regra (`[["A",1],["B",2],...]` na ordem das vagas).
- **Motor de regras de passagem (`services/engine.py`):** uma fase só é criada/sorteada quando **todas** as fases de origem das suas regras terminam; os confrontos são gerados sozinhos. Fontes: `ranking` (liga: tabela; grupos: posição no grupo e depois pontos/saldo; round/playoff: vencedores e depois perdedores; mata-mata: campeão, vice, 3º, 4º, demais por rodada de queda), `winners`/`losers` (só fases `round`/`playoff`; vencedores ordenados por **saldo** desc, perdedores pelo menor prejuízo; **empate de saldo → sorteio reproduzível** `engine._tiebreak_key`, que depende só de `draw_seed` + fase + jogador), `group_position`. Destinos: `stage` (vagas `to_slot_from`…), `eliminated`, `repechage` (jogadores ficam `eliminated` e a lista vai para `Tournament.config["repechage"][stage_id]` — a Fase 7 usa isso) e `parent_tournament` (Fase 7). Nas fases de destino: `knockout` → por padrão **`seeding="standard"`**: vaga = seed (1×N, 2×(N−1)…); com `config.seeding="sequential"` a vaga é a posição literal na chave (pares adjacentes se enfrentam — controle manual total; é o padrão implícito quando a entrada vem de `group_position`, pois o cruzamento já define as posições); `round`/`playoff` → pares sorteados ou, com `config.pairing="seeded"`, melhor×pior; `league`/`groups` → sorteio com seed derivada (`draw_seed + position*7919`). Jogadores que desistiram e chegam a uma fase nova já viram W.O. na hora.
- **Mudança em fase de origem depois do destino criado:** se nenhum confronto do destino foi reportado/validado, ele é apagado e refeito (ou desfeito, se a origem foi reaberta — eliminados voltam a `active`); caso contrário a API devolve **409** e não grava nada (invalide de trás para frente). Validação estática do `custom` no cadastro (`templates.validate_custom`): tamanhos de cada fase, vagas contínuas a partir de 1 sem sobreposição, mata-mata potência de 2, round/playoff par, posições existentes, fontes compatíveis com o tipo da fase.
- **Repescagem/subtorneio:** é um torneio filho (`parent_id`), cadastrado como qualquer torneio, **1 nível apenas** (subtorneio não tem subtorneio). Entrada: automática por regra (ex.: "3º de cada grupo", `repechage_position`) ou manual pelo admin. Pode ter **vários vencedores**, que **voltam ao torneio principal** em vagas configuradas de antemão (`parent_tournament` + `parent_stage` + `to_slot_from`). A página do torneio principal lista os subtorneios (botão de acesso; o detalhe traz `repechage`: regra, subtorneio ligado e candidatos).
  - **Ligação regra→subtorneio:** `rule.config.subtournament_id`, ou, se não marcado, o **único** subtorneio não cancelado. Com 2+ subtorneios é preciso ligar com `PUT /tournaments/{id}/rules/{rule_id}/subtournament` (`{"subtournament_id": N}`); trocar a ligação move os candidatos (409 se o antigo já começou).
  - **Entrada automática:** quando a fase de origem termina, os candidatos da regra `repechage` são inscritos no subtorneio (lista em `sub.config.auto_enrolled[rule_id]`); se a fase reabre, saem. Depois que o subtorneio **começa**, a lista não muda mais (409, invalide de trás para frente). Se exceder `max_players` do subtorneio, 409 com aviso. Quem desistiu do principal não é inscrito. Entrada manual: `POST /tournaments/{sub}/players` (só jogadores do principal, não desistentes). O subtorneio inicia pelo `/start` normal, **só com o principal em andamento** e `max_players` exatos.
  - **Retorno ao principal:** o subtorneio só pode devolver jogadores a vagas **reservadas** na fase de destino do principal: `stage.config.external_slots = [[de, até]]` (custom) ou `config.repechage_slots` (template `groups_knockout`: reserva as vagas depois dos classificados, exige `repechage_position`, `grupos*classificados + repechage_slots` = potência de 2, e a chave passa a `seeding="standard"` para que classificados diretos enfrentem repescados). O destino só é criado quando **todas** as fontes (grupos do principal **e** subtorneio) terminam; enquanto as vagas reservadas não são preenchidas ele espera. Mudou algo no subtorneio/grupo depois: destino refeito se ainda sem reporte, senão 409. Quem volta fica `active` no principal enquanto estiver na fase; ao desfazer volta a `eliminated`.
  - **Desistência:** quem desiste do principal sai também dos subtorneios não encerrados (remove da lista se não começou; W.O. se em andamento). Desistir só do subtorneio não afeta o principal.
  - **Limite conhecido:** o template `groups_knockout` exige nº par de grupos (cruzamento fixo); subtorneio cancelado nunca libera o destino (apague-o).
- **Sorteio da 1ª fase (`/draw` prévia, `/start` confirma):** (a) **aleatório** por seed; (b) **por potes** (`PUT /tournaments/{id}/pots`, `TournamentPlayer.pot`, 1 = mais forte; vale `use_pots`; todos precisam de pote se algum tiver): grupos recebem um jogador de cada pote por grupo (potes do tamanho do nº de grupos) e no mata-mata os potes viram seeds (pote 1 = cabeças de chave, chave padrão 1×N) — o `seed` do jogador passa a ser o ranking dos potes; (c) **manual**: `arrangement` com `slots` (mata-mata, ordem da chave), `groups` (`{"A":[ids]}`) ou `pairs` (round/playoff); não se aplica a pontos corridos. O `/draw` devolve o `arrangement` editável: o front ajusta e reenvia em `/start`. O sorteio fica registrado em `Tournament.config["draw"]` (seed, modo, potes, arranjo, quem/quando) e é público em `GET /tournaments/{id}/draw`.
- **Início do torneio** só via `POST /tournaments/{id}/start` e **com exatamente `max_players` inscritos**. Jogador que desiste antes do início é removido da lista.
- **Histórico:** cada mudança relevante salva um snapshot da tabela (`standings_snapshots`, `kind="change"`). Admin pode corrigir/invalidar resultados a qualquer momento (irregularidades); tudo é recalculado e registrado em `audit_log`. Além disso (`services/history.py`): **`kind="round"`** = tabela congelada quando uma rodada de pontos corridos/grupos fecha (uma por rodada, todas consultáveis; a tabela traz `played` por jogador para ver quem tem jogo a menos); **`kind="final"`** = estado final de cada fase (grupos, liga, mata-mata com `ranking`, rodada/playoff, e as fases dos subtorneios), regravado como nova versão se uma correção posterior o alterar (`versions`). Consultas públicas: `GET /tournaments/{id}/history/rounds[?stage_id=]`, `/history/stages` (inclui subtorneios), `/history?kind=`.
- **Adiamento (só pontos corridos/grupos, só admin/organizador do torneio):** adia um jogo (`POST /matches/{id}/postpone`) ou os jogos pendentes de uma rodada (`POST /tournaments/{id}/rounds/postpone` com `stage_id`, `round`, `group_label` opcional, `reason`); `resume` desfaz enquanto o jogo não foi disputado. O jogo adiado **continua podendo ser reportado**; a fase e o torneio **não encerram** enquanto houver jogo pendente (e `PATCH status=finished` retorna 409). Uma rodada "fecha" para o histórico quando seus jogos estão validados/anulados ou adiados; o snapshot dela registra `postponed` (pendentes) e **nunca é alterado depois**. O jogo adiado, quando disputado, entra na tabela do próximo snapshot que fechar (`played_postponed`, com `original_round`) ou no estado final. Se uma rodada fechada voltar a ter jogo em aberto (invalidação/retomada) o snapshot ganha `reopened=true` e, ao fechar de novo, é criado um novo.
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
    services/ templates.py schedule.py bracket.py stages.py tables.py engine.py standings.py results.py views.py
    scripts/ create_admin.py
  alembic/versions/  0001_esquema_inicial.py  0002_fechar_alembic_version.py  0003_pote_do_jogador.py  0004_historico_e_adiamento.py  0005_senha_temporaria.py
  tests/   conftest.py test_auth_users.py test_tournaments.py test_play.py test_knockout.py test_groups.py test_draw.py test_repechage.py test_history.py test_audit.py   # SQLite em memória
```

- Testes usam **SQLite** (`JsonType` → JSON; `BigIntPK` → INTEGER). Nunca apontam para o banco real.
- A tabela é **sempre recalculada** a partir dos confrontos `validated` (`services/standings.py`), não armazenada; os snapshots são só histórico.
- Concorrência: confrontos são carregados com `FOR UPDATE` nas ações de resultado.

### Endpoints atuais (docs interativa em `/docs`)
- **auth:** `POST /auth/register|login|change-password`, `GET /auth/me`
- **users:** `GET /users` (público: id+nome), `GET /users/admin`, `POST /users` (admin cria conta; sem senha devolve temporária e marca `must_change_password`), `POST /users/{id}/reset-password`, `PATCH /users/{id}/role|active`
- **tournaments:** `GET /tournaments`, `GET /tournaments/{id}` (detalhe completo: fases, regras, jogadores, subtorneios, `can_manage`), `POST /tournaments`, `POST /tournaments/{id}/subtournaments`, `PATCH /tournaments/{id}`, `PATCH /tournaments/{id}/status`, `DELETE /tournaments/{id}`, `GET|POST /tournaments/{id}/players`, `DELETE /tournaments/{id}/players/{user_id}`, `POST /tournaments/{id}/withdraw`, `PUT /tournaments/{id}/rules/{rule_id}/subtournament`, `POST /tournaments/{id}/rounds/postpone|resume`
- **play:** `PUT /tournaments/{id}/pots`, `POST /tournaments/{id}/draw` (prévia: `seed`, `use_pots`, `arrangement`), `POST /tournaments/{id}/start` (mesmos campos), `GET /tournaments/{id}/draw` (registro do sorteio), `GET /tournaments/{id}/matches|standings|bracket|history`, `GET /tournaments/{id}/history/rounds|stages`, `GET /tournaments/{id}/history/{snapshot_id}`
- **matches:** `GET /matches/{id}`, `POST /matches/{id}/report|validate|reject|result|walkover|invalidate|postpone|resume`

## Estado atual

**Concluído:** Fases 1 a 8 (autenticação, torneios/fases/regras/inscrição/subtorneios, pontos corridos, mata-mata, grupos + mata-mata com motor de regras, sorteador avançado, repescagem em subtorneio, histórico por rodada/final de fase, adiamento). 90 testes passando. Migrations 0001–0003 aplicadas no Supabase; a **0004** (colunas novas em `matches` e `standings_snapshots`) é aplicada pelo Render no próximo start. Back-end implantado no Render.
**Funciona de ponta a ponta:** `league`, `knockout`, `groups_knockout` e `custom`, com sorteio aleatório, por potes ou manual, e repescagem em subtorneio (entrada automática dos candidatos e retorno ao mata-mata principal).

## Histórico de fases

- **Fase 1 — Fundação:** projeto FastAPI/Alembic, conexão com o Supabase via pooler, modelo de dados completo (9 tabelas) com RLS ativo e sem acesso para `anon`/`authenticated`, cadastro/login (JWT), papéis, reset de senha pelo admin, auditoria, script `create_admin`.
- **Fase 2 — Torneios:** CRUD, modelos prontos (liga, mata-mata, grupos+mata-mata) e `custom`, regras de passagem, inscrição de jogadores (só staff), desistência, máquina de status, subtorneios (1 nível) com retorno ao principal, páginas de leitura públicas.
- **Fase 3 — Pontos corridos:** round-robin (turno/returno opcional) com sorteio por seed e prévia, `/start`, página do confronto, reporte do jogador com replay do Showdown, validação/rejeição/correção/invalidação/W.O. pelo admin, tabela com saldo/vitórias/confronto direto, W.O. automático na desistência (reportes pendentes permanecem), histórico de tabelas, encerramento/reabertura automática do torneio. Empate só como 0×0.

- **Fase 4 — Mata-mata:** `services/bracket.py` (chaveamento de eliminação simples sem byes, nomes de rodada, 3º lugar opcional), sorteio por seed com prévia, `seed` do jogador = posição no chaveamento, avanço automático do vencedor e dos perdedores das semifinais, bloqueio de empate, correção/invalidação em cascata com 409 seguro, W.O. por desistência encadeado, `GET /tournaments/{id}/bracket` (rodadas, 3º lugar, campeão), snapshots do chaveamento no histórico, encerramento/reabertura automática do torneio.

- **Fase 5 — Grupos + mata-mata e motor de regras:** `services/stages.py` (plano e criação de confrontos por tipo de fase: liga, grupos, mata-mata, round, playoff), `services/tables.py` (tabelas por fase/grupo), `services/engine.py` (saídas de cada fase, execução das regras de passagem, refazer/desfazer destinos com bloqueio 409), cruzamento fixo de grupos, standings por grupo (`StageStandings.groups`), `slot` exposto nos confrontos, desistência/W.O. em qualquer tipo de fase, snapshots de grupos e rodadas, validação estática de torneios `custom`, `/draw` e `/start` para todos os formatos.

- **Fase 6 — Sorteador avançado:** potes por jogador (`pot`, migration 0003) com sorteio por potes em grupos e mata-mata (cabeças de chave), sorteio manual (`arrangement`) para `slots`/`groups`/`pairs`, prévia devolvendo o arranjo editável, registro público do sorteio (`GET /tournaments/{id}/draw`), padrão `seeding=standard` para mata-mata alimentado por regras (e `sequential` para controle manual da chave) e desempate de saldo por sorteio reproduzível.

- **Fase 7 — Subtorneios na prática (repescagem):** `engine.rule_subtournament`/`set_enrolled`/`refresh_repechage` (ligação regra→subtorneio e inscrição automática dos candidatos), `_sync_dest` generalizado para destinos com fontes em torneios diferentes (principal + subtorneio, regras `parent_tournament`), `external_slots`/`repechage_slots` (vagas do mata-mata reservadas a quem volta), `PUT /tournaments/{id}/rules/{rule_id}/subtournament`, campo `repechage` no detalhe do torneio, restrição de jogadores do subtorneio ao principal, desistência do principal propagada ao subtorneio, subtorneio só inicia com o principal em andamento. Sem migration nova. 80 testes.

- **Fase 8 — Histórico e adiamento:** `services/history.py` (registros `round` e `final` em `standings_snapshots`, colunas `kind`/`round`), migration 0004 (também adiciona `matches.postponed*`), `GET /tournaments/{id}/history/rounds|stages` e filtro `kind` em `/history`, adiamento de jogo/rodada (`POST /matches/{id}/postpone|resume`, `POST /tournaments/{id}/rounds/postpone|resume`), filtro `postponed` em `/matches`, bloqueio de encerramento manual com jogo adiado pendente. 86 testes.

## Próxima fase — Fase 9: front-end básico (branch `front-end`)

Ver o roadmap abaixo; antes de começar, discutir o design com o usuário. Auditoria (concluída junto da Fase 8): `GET /audit` (admin; filtros actor_id, action exata ou prefixo "match.", entity, entity_id, since, until; limit/offset; devolve total+items) e `GET /matches/{id}/timeline` (público: reportes, revisões e ações do admin em ordem).

## Roadmap restante

- **Fase 9 — Front-end básico** (branch `front-end`; inclui a aba de histórico com rodadas e estados finais das fases): login/cadastro, lista de torneios, página do torneio (info + tabela/chaveamento + botão do subtorneio), página do confronto com reporte, painel do admin. Tempo real por polling (ou WebSocket).
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
