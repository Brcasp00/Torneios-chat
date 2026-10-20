# CLAUDE.md — Plataforma de Torneios Pokémon

> Documento vivo. **Ao concluir cada fase (ou qualquer mudança relevante), atualize as seções "Estado atual", "Histórico de fases" e "Próxima fase" antes de seguir adiante.**

## Resumo rápido (leia primeiro)

- **O que é:** plataforma web, em português, para organizar torneios de Pokémon competitivo (Showdown) entre amigos. Público vê tudo; ações exigem login. Dezenas de usuários.
- **Está no ar:** front **React/Vite no Netlify**, API **FastAPI no Render**, banco **Postgres no Supabase**. As três peças seguem a branch **`main`**. **Bancos separados:** a produção usa o projeto Supabase configurado no Render; o `backend/.env` local aponta para **outro projeto Supabase só de testes** (criado em 2026-10-20). Nunca coloque a URL de produção no `.env`.
- **Branches:** `main` = produção; `Back-end` = trabalho de `backend/`; `front-end` = trabalho de `frontend/`, `main.py` e docs. Fluxo e armadilhas na seção "Fluxo de trabalho e armadilhas".
- **Fases 1–9 concluídas**, mais melhorias posteriores (ver "Histórico de fases" e "Estado atual"). A Fase 10 (polimento) está em andamento.
- **Usuários de teste:** no **banco de testes** (local): `teste1`–`teste16`, senha `12345678` (jogadores; o admin local é criado pelo usuário com `create_admin`). No **banco de produção** ainda existem `teste1`–`teste14` e `testea` (`teste5`–`teste14` com senha `123456`): o usuário decidiu **apagá-los** (a interface só desativa; apagar exige script com a URL de produção, que não fica no `.env`). O admin é `Arlen`.

## Regras de trabalho (obrigatórias)

1. **Back-end → GitHub automaticamente.** Toda modificação feita no back-end (`backend/`) deve ser commitada e enviada (`git push`) para a branch **`Back-end`** de https://github.com/Brcasp00/Torneios-chat (atenção: o nome real da branch tem **B maiúsculo**: `Back-end`). Faça isso sem precisar pedir confirmação, ao final de cada conjunto coerente de mudanças (e sempre ao fechar uma fase), com os testes passando.
2. **`main` = produção.** A `main` só recebe código por **merge/Pull Request de `Back-end` (e `front-end`) feito quando o usuário pedir**. Nunca dê push direto na `main` por conta própria.
3. **Front-end → branch `front-end`.** Toda modificação no front-end (`frontend/`, `main.py`) vai para a branch **`front-end`** (https://github.com/Brcasp00/Torneios-chat/tree/front-end). Nunca misture código de front-end na branch `Back-end` nem o contrário. O checkout principal (`D:\Projetos`) fica na branch `front-end` (contém também `backend/` vindo da `main`); alterações em `backend/` vão só para `Back-end`, feitas no **worktree `D:\Projetos-back`** (já existe, aponta para `Back-end`; recriar com `git worktree add D:\Projetos-back Back-end`). Não deixe alterações de `backend/` commitadas na `front-end`.
4. **Segredos nunca vão para o Git.** `backend/.env` (DATABASE_URL, JWT_SECRET) é ignorado. Antes de cada commit, confira `git status`/`git diff --cached` e não deixe passar `.env`, `*.db`, `.venv/`. Nunca imprima a senha do banco nem cole a connection string em respostas/logs.
5. **Testes antes de commitar:** `cd backend; .\.venv\Scripts\python -m pytest` deve passar.
6. **Mensagens de commit** em português, no imperativo, com prefixo da fase quando fizer sentido (ex.: `Fase 4: gera chaveamento do mata-mata`), terminando com a linha `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
7. **Toda tabela nova** (migration) deve repetir `ENABLE ROW LEVEL SECURITY` + `REVOKE ALL ... FROM anon, authenticated` (ver `alembic/versions/0001_*.py`). O FastAPI é o único acesso ao banco; a API REST pública do Supabase deve permanecer fechada.
8. **Não escreva arquivos de código com `Set-Content`/`Add-Content` do PowerShell 5.1** (corrompe acentos). Use as ferramentas Write/Edit, ou Python com `encoding="utf-8"`.
9. **Idioma:** conversa, mensagens de erro da API e comentários em português.
10. **Botões nunca ficam só "desabilitados" sem explicação:** quando uma funcionalidade não pode ser feita (sorteio sem jogadores suficientes, rodada não escolhida, etc.), o botão fica clicável e, ao clicar, mostra o **motivo** (mensagem da API ou verificação prévia no front). Telas que escondem um formulário devem explicar por quê.
11. **Cláusulas das regras de batalha não são informadas no front:** são definidas automaticamente pelo tier (Smogon/Showdown). O campo foi removido do formulário (a API ainda aceita `battle_rules.clauses`, vazio por padrão).
12. **Migrations:** `alembic upgrade head` local altera só o **banco de testes**; a produção recebe a migration quando o Render publica a versão nova (o start roda `alembic upgrade head`). Teste a migration localmente antes do merge. Mesmo assim, prefira migrations aditivas (a produção tem dados reais). Antes de rodar algo que escreve no banco local, confira que não é a produção (ex.: banco recém-criado/sem dados reais).
13. **Ações que afetam a produção só quando o usuário pedir:** merge/PR na `main`, deploys, criação/remoção de dados reais. Não dê push na `main`. (O `gh` não está instalado: o PR é aberto pelo usuário em `https://github.com/Brcasp00/Torneios-chat/compare/main...<branch>`.)
14. **`docs/FUNCIONAMENTO.md`** é o guia, em linguagem simples, de como toda a plataforma funciona (feito a pedido do usuário). Ao mudar uma regra ou funcionalidade, atualize a seção correspondente dele também (fica na branch `front-end`, como os demais documentos).

## Contexto do projeto

O usuário organiza, com amigos, torneios de **Pokémon competitivo** (maioria das partidas no **Pokémon Showdown**) e quer uma plataforma própria. Escala pequena (dezenas de usuários). Visualização **pública**; ações exigem login. Interface em português.

- **Back-end:** FastAPI + SQLAlchemy 2 (async) + Alembic. **Banco:** Supabase (Postgres, plano gratuito). Não usamos Supabase Auth nem a API REST do Supabase: autenticação própria (nome + senha, argon2, JWT).
- **Front-end:** React + Vite + TypeScript em `frontend/` (branch `front-end`), tema escuro; ver a seção "Front-end".
- **Repositório:** https://github.com/Brcasp00/Torneios-chat — branches `Back-end`, `front-end`, `main`. Raiz local: `D:\Projetos` (pastas `backend/` e `frontend/` dentro, mais `main.py` e este arquivo).
- Possível futuro: notificações no Discord (a avaliar).

### Ambiente
- Windows 11, PowerShell. Python via `py` (3.14). Venv em `backend/.venv` (`cd D:\Projetos\backend; .\.venv\Scripts\Activate.ps1`).
- `backend/.env`: `DATABASE_URL` (Session/Transaction pooler do Supabase, **porta 6543**, sem colchetes na senha) e `JWT_SECRET`. As migrations trocam automaticamente para a porta **5432**.
- **Deploy (Render, Web Service):** Root Directory `backend`, Build `pip install -r requirements.txt`, Start `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`, Health Check `/health`. Variáveis no painel do Render: `DATABASE_URL`, `JWT_SECRET` (valor próprio de produção), `CORS_ORIGINS` (URL do front), `PYTHON_VERSION` se necessário. O Render acompanha a branch **`main`** com auto-deploy: a produção só muda após merge na `main`. As migrations rodam no start e alteram o banco de produção (cuidado com migrations destrutivas). Plano gratuito: o serviço dorme após ~15 min sem acesso (o primeiro acesso depois disso demora ~1 min; a tarefa de prazos não roda enquanto dorme, por isso a leitura do torneio também verifica prazos).
- **Deploy do front (Netlify):** projeto importado do mesmo repositório, branch de produção `main`, Base directory `frontend` (o `frontend/netlify.toml` define build `npm run build`, publish `dist`, Node 20 e o redirect de SPA; `frontend/public/_redirects` repete o redirect). Variável do Netlify: `VITE_API_URL` = URL da API no Render (sem barra final; só vale no build, então mudou → novo deploy). No Render, `CORS_ORIGINS` deve conter a URL do Netlify (sem barra final; várias separadas por vírgula, ex. incluindo `http://localhost:5173`). Trocar o nome do site no Netlify muda a URL → atualizar `CORS_ORIGINS`. Branch deploys/Deploy previews são opcionais (cada URL nova também precisa entrar em `CORS_ORIGINS`). Para voltar uma versão: Netlify → Deploys → "Publish deploy" do anterior; Render → redeploy do commit anterior.
- **Conexão com o banco (importante):** o pooler do Supabase (porta 6543, modo transaction) não aceita prepared statements; `app/db/session.py` desliga o cache do asyncpg **e** o do SQLAlchemy (`prepared_statement_cache_size=0` na URL) e usa nomes únicos. Sem isso aparece `prepared statement "__asyncpg_..." does not exist` de forma intermitente (e o navegador mostra "não foi possível conectar", pois um 500 sem cabeçalho CORS parece falha de rede).
- Skills Supabase instaladas (`supabase`, `supabase-postgres-best-practices`): consultar antes de mexer em schema/RLS.

## Papéis e permissões

| Papel | Pode |
|---|---|
| `admin` | Tudo: **criar usuários**, promover usuários, resetar senhas, desativar contas, ver a auditoria, gerenciar qualquer torneio, validar/corrigir/invalidar resultados |
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
- **Prazo das rodadas (`services/deadlines.py`):** admin/organizador define a data-limite de cada rodada, uma a uma (`PUT /tournaments/{id}/stages/{stage_id}/deadlines` com `{"deadlines": {"1": "<ISO com fuso>", "2": null}}`, null remove; data já passada é recusada com 422; fica em `stage.config.deadlines`). Vencido o prazo: em **liga/grupos** de torneio que **permite empate**, os jogos ainda `scheduled` (sem reporte, não adiados, não liberados) viram **empate 0x0 automático** (`matches.auto_result`, audit `match.auto_draw` com ator nulo, tabela recalculada). **Invalidar** esse empate marca `deadline_waived` e o jogo pode ser entregue atrasado (o prazo não age mais nele); retomar um jogo adiado depois do prazo também o libera. Em mata-mata/rodada única/playoff, ou em torneio sem empate, nada é decidido: o confronto só vem com `overdue=true` (aviso para o admin). Jogo com reporte pendente nunca é empatado. A verificação roda numa tarefa a cada 60 s (lifespan do FastAPI) **e** na leitura do torneio/confrontos/tabela/chaveamento/confronto, porque o plano gratuito do Render dorme. `MatchOut` ganhou `deadline`, `overdue`, `auto_result`, `deadline_waived`. Migration 0006.
- **Regras de batalha:** campos estruturados (`battle_rules`: formato, jogo, tier, team_size, bring, level_cap, timer, clauses, showdown_required) + texto livre (`rules_text`). `team_size` = Pokémon no time registrado; `bring` = quantos entram em cada batalha (ex.: VGC 6/4); o máximo de "Pokémon vivos" aceito no reporte é `bring` (ou `team_size`, ou 6). Cláusulas: ver regra 11 (definidas pelo tier, sem campo no front).

## Arquitetura (back-end)

```
backend/
  app/
    main.py                 # FastAPI, CORS, routers, lifespan (tarefa de prazos a cada 60 s)
    core/    config.py security.py deps.py   # settings, argon2/JWT, dependências (CurrentUser bloqueia senha temporária; CurrentUserAnyState só p/ /auth/me e change-password)
    db/      base.py session.py              # Base/naming/JsonType/BigIntPK, engine async (pooler-safe, ver "Conexão com o banco")
    models/  user.py tournament.py           # User(must_change_password), AuditLog | Tournament, Stage, AdvancementRule, TournamentPlayer, Match(postponed*, auto_result, deadline_waived), MatchReport, StandingsSnapshot(kind, round)
    schemas/ user.py tournament.py match.py audit.py  # Pydantic
    api/     auth.py users.py tournaments.py play.py matches.py audit.py
    services/ templates.py schedule.py bracket.py stages.py tables.py engine.py standings.py results.py views.py history.py deadlines.py
    scripts/ create_admin.py
  alembic/versions/  0001_esquema_inicial.py  0002_fechar_alembic_version.py  0003_pote_do_jogador.py  0004_historico_e_adiamento.py  0005_senha_temporaria.py  0006_prazo_das_rodadas.py
  tests/   conftest.py test_auth_users.py test_tournaments.py test_play.py test_knockout.py test_groups.py test_draw.py test_repechage.py test_history.py test_audit.py test_deadlines.py   # SQLite em memória
```

- Testes usam **SQLite** (`JsonType` → JSON; `BigIntPK` → INTEGER). Nunca apontam para o banco real.
- A tabela é **sempre recalculada** a partir dos confrontos `validated` (`services/standings.py`), não armazenada; os snapshots são só histórico.
- Concorrência: confrontos são carregados com `FOR UPDATE` nas ações de resultado.

### Endpoints atuais (docs interativa em `/docs`)
- **auth:** `POST /auth/register|login|change-password`, `GET /auth/me`
- **users:** `GET /users` (público: id+nome), `GET /users/admin`, `POST /users` (admin cria conta; sem senha devolve temporária e marca `must_change_password`), `POST /users/{id}/reset-password`, `PATCH /users/{id}/role|active`
- **tournaments:** `GET /tournaments`, `GET /tournaments/{id}` (detalhe completo: fases, regras, jogadores, subtorneios, `can_manage`), `POST /tournaments`, `POST /tournaments/{id}/subtournaments`, `PATCH /tournaments/{id}`, `PATCH /tournaments/{id}/status`, `DELETE /tournaments/{id}`, `GET|POST /tournaments/{id}/players`, `DELETE /tournaments/{id}/players/{user_id}`, `POST /tournaments/{id}/withdraw`, `PUT /tournaments/{id}/rules/{rule_id}/subtournament`, `POST /tournaments/{id}/rounds/postpone|resume`
- **play:** `PUT /tournaments/{id}/pots`, `POST /tournaments/{id}/draw` (prévia: `seed`, `use_pots`, `arrangement`), `POST /tournaments/{id}/start` (mesmos campos), `GET /tournaments/{id}/draw` (registro do sorteio), `GET /tournaments/{id}/matches` (filtros `stage_id`, `round`, `player_id`, `status_`, `postponed`), `GET /tournaments/{id}/standings|bracket|history` (`kind`), `GET /tournaments/{id}/history/rounds|stages`, `GET /tournaments/{id}/history/{snapshot_id}`, `PUT /tournaments/{id}/stages/{stage_id}/deadlines`
- **matches:** `GET /matches/{id}`, `POST /matches/{id}/report|validate|reject|result|walkover|invalidate|postpone|resume`, `GET /matches/{id}/timeline` (público)
- **audit:** `GET /audit` (admin; filtros `actor_id`, `action` exata ou prefixo terminado em ponto, `entity`, `entity_id`, `since`, `until`; `limit`/`offset`; devolve `total`+`items`)
- Leituras (`GET /tournaments/{id}`, `/matches`, `/standings`, `/bracket`, `GET /matches/{id}`) chamam `deadlines.safe_sweep` antes de responder (aplica prazos vencidos).

## Estado atual

**Concluído:** Fases 1 a 9 — back-end (autenticação, torneios/fases/regras/inscrição/subtorneios, pontos corridos, mata-mata, grupos + mata-mata com motor de regras, sorteador avançado, repescagem em subtorneio, histórico por rodada/final de fase, adiamento, auditoria, criação de usuário pelo admin, senha temporária com troca obrigatória, prazo das rodadas com empate automático) e front-end completo em `frontend/` + `main.py`. **103 testes do back-end passando** (o front ainda não tem testes automatizados; valida-se com `npm run build` e uso manual). Migrations **0001–0006** aplicadas no Supabase (o Render também as aplica sozinho no start).
**Em produção:** API no Render e site no Netlify, ambos seguindo a `main` (a `main` contém tudo até o commit "Front: mensagem de falha de conexão mais curta"). A `front-end` e a `Back-end` estão sincronizadas com a `main`, exceto por este documento quando editado.
**Funciona de ponta a ponta:** `league`, `knockout`, `groups_knockout` e `custom`, com sorteio aleatório, por potes ou manual, repescagem em subtorneio, histórico, adiamento e prazos. O usuário já testou a interface com os usuários de teste e relatou que funciona; ainda falta simular um torneio completo de ponta a ponta (sorteio → jogos → mata-mata → repescagem).

## Histórico de fases

- **Fase 1 — Fundação:** projeto FastAPI/Alembic, conexão com o Supabase via pooler, modelo de dados completo (9 tabelas) com RLS ativo e sem acesso para `anon`/`authenticated`, cadastro/login (JWT), papéis, reset de senha pelo admin, auditoria, script `create_admin`.
- **Fase 2 — Torneios:** CRUD, modelos prontos (liga, mata-mata, grupos+mata-mata) e `custom`, regras de passagem, inscrição de jogadores (só staff), desistência, máquina de status, subtorneios (1 nível) com retorno ao principal, páginas de leitura públicas.
- **Fase 3 — Pontos corridos:** round-robin (turno/returno opcional) com sorteio por seed e prévia, `/start`, página do confronto, reporte do jogador com replay do Showdown, validação/rejeição/correção/invalidação/W.O. pelo admin, tabela com saldo/vitórias/confronto direto, W.O. automático na desistência (reportes pendentes permanecem), histórico de tabelas, encerramento/reabertura automática do torneio. Empate só como 0×0.

- **Fase 4 — Mata-mata:** `services/bracket.py` (chaveamento de eliminação simples sem byes, nomes de rodada, 3º lugar opcional), sorteio por seed com prévia, `seed` do jogador = posição no chaveamento, avanço automático do vencedor e dos perdedores das semifinais, bloqueio de empate, correção/invalidação em cascata com 409 seguro, W.O. por desistência encadeado, `GET /tournaments/{id}/bracket` (rodadas, 3º lugar, campeão), snapshots do chaveamento no histórico, encerramento/reabertura automática do torneio.

- **Fase 5 — Grupos + mata-mata e motor de regras:** `services/stages.py` (plano e criação de confrontos por tipo de fase: liga, grupos, mata-mata, round, playoff), `services/tables.py` (tabelas por fase/grupo), `services/engine.py` (saídas de cada fase, execução das regras de passagem, refazer/desfazer destinos com bloqueio 409), cruzamento fixo de grupos, standings por grupo (`StageStandings.groups`), `slot` exposto nos confrontos, desistência/W.O. em qualquer tipo de fase, snapshots de grupos e rodadas, validação estática de torneios `custom`, `/draw` e `/start` para todos os formatos.

- **Fase 6 — Sorteador avançado:** potes por jogador (`pot`, migration 0003) com sorteio por potes em grupos e mata-mata (cabeças de chave), sorteio manual (`arrangement`) para `slots`/`groups`/`pairs`, prévia devolvendo o arranjo editável, registro público do sorteio (`GET /tournaments/{id}/draw`), padrão `seeding=standard` para mata-mata alimentado por regras (e `sequential` para controle manual da chave) e desempate de saldo por sorteio reproduzível.

- **Fase 7 — Subtorneios na prática (repescagem):** `engine.rule_subtournament`/`set_enrolled`/`refresh_repechage` (ligação regra→subtorneio e inscrição automática dos candidatos), `_sync_dest` generalizado para destinos com fontes em torneios diferentes (principal + subtorneio, regras `parent_tournament`), `external_slots`/`repechage_slots` (vagas do mata-mata reservadas a quem volta), `PUT /tournaments/{id}/rules/{rule_id}/subtournament`, campo `repechage` no detalhe do torneio, restrição de jogadores do subtorneio ao principal, desistência do principal propagada ao subtorneio, subtorneio só inicia com o principal em andamento. Sem migration nova. 80 testes.

- **Fase 8 — Histórico e adiamento:** `services/history.py` (registros `round` e `final` em `standings_snapshots`, colunas `kind`/`round`), migration 0004 (também adiciona `matches.postponed*`), `GET /tournaments/{id}/history/rounds|stages` e filtro `kind` em `/history`, adiamento de jogo/rodada (`POST /matches/{id}/postpone|resume`, `POST /tournaments/{id}/rounds/postpone|resume`), filtro `postponed` em `/matches`, bloqueio de encerramento manual com jogo adiado pendente. 86 testes.

  Auditoria (junto da Fase 8): `GET /audit` (admin; filtros actor_id, action exata ou prefixo "match.", entity, entity_id, since, until; limit/offset; devolve total+items) e `GET /matches/{id}/timeline` (público: reportes, revisões e ações do admin em ordem). 88 testes.

- **Fase 9 — Front-end (branch `front-end`):** app React 18 + Vite + TypeScript em `frontend/` (tema escuro estilo e-sports/Pokémon, responsivo, CSS puro, `react-router-dom`, sem biblioteca de UI), mais o orquestrador local `main.py` na raiz. Telas: início (torneios em andamento + "seus jogos pendentes"), lista de torneios, página do torneio com abas (visão geral, tabela/grupos, chaveamento, confrontos, **histórico** — fases encerradas, rodada a rodada, registro de alterações — e **gerenciar** para admin/organizador: status, inscrição, potes, prévia/início do sorteio, adiar rodada, subtorneios/ligação de repescagem), página do confronto (reporte com replay, validar/rejeitar/lançar/W.O./invalidar/adiar, linha do tempo), criação de torneio/subtorneio (botão "Novo torneio" na lista de torneios; modelos prontos + JSON para `custom`), conta (trocar senha) e administração, só para admins (criar usuários em página própria `/admin/usuarios/novo`, papéis, redefinir senha, auditoria). Atualização por polling (15–30 s, só com a aba visível). Prazo das rodadas: card "Prazo das rodadas" na aba Gerenciar (data/hora por rodada), prazo e avisos ("prazo vencido", "empate por prazo") nos confrontos. Senha temporária: quem entra com `must_change_password` é levado a "Minha conta" e não acessa mais nada até trocar a senha.

- **Melhorias pós-Fase 9 (pedidas pelo usuário durante os testes):**
  - **Correção do pooler** (`session.py`, `prepared_statement_cache_size=0`) — corrigia 500 intermitentes (ver "Conexão com o banco").
  - **Admin cria usuários:** `POST /users` + página `/admin/usuarios/novo` (botão "Criar usuário" na aba Usuários; ao concluir volta à administração mostrando o aviso e a senha temporária, se houver). Auditoria `user.create`.
  - **Senha temporária obrigatória:** migration 0005 (`users.must_change_password`), regra no servidor (`CurrentUser` → 403) e no front (redireciona para "Minha conta" até trocar). Senha gerada pelo sistema = temporária; senha digitada pelo admin = definitiva.
  - **Mostrar/ocultar senha** nos campos de senha (`PasswordInput`).
  - **Prazo das rodadas:** migration 0006 e `services/deadlines.py` (ver regras de negócio); card "Prazo das rodadas" na aba Gerenciar.
  - **Motivos nas ações** (regra 10), menu simplificado ("Novo torneio" só como botão em Torneios; "Administração" só para admin, outros são redirecionados), cláusulas removidas do formulário, mensagem de falha de conexão: "Não foi possível conectar ao servidor".
  - **Deploy:** Netlify (front) e Render na `main`; `netlify.toml` + `_redirects`.
- **Revisão de segurança (Fase 10, commits `3d5beb5` e `36cfef4` na `Back-end`; front na `front-end`):**
  - `core/login_guard.py`: 3 senhas erradas seguidas (janela de 10 min) bloqueiam o login daquele nome por 10 min (429 + `Retry-After`), inclusive nomes inexistentes; login certo zera; `reset-password` desbloqueia. Estado em memória (zera ao reiniciar). Testes zeram com `login_guard.reset()` no `conftest`.
  - `config.py`: a API não inicia com `JWT_SECRET` padrão ou com menos de 32 caracteres.
  - Senha mínima **8** (`security.MIN_PASSWORD_LENGTH`); login com senha antiga mais curta marca `must_change_password` (mensagem 403 genérica de troca de senha). Front com `minLength=8` e texto ajustado em "Minha conta".
  - argon2id com parâmetros mínimos da OWASP (19 MiB, t=2, p=1), calculado em thread (`hash_password_async`/`verify_password_async`, no máximo 2 simultâneos); hashes antigos são refeitos no login (`needs_rehash`).
  - `deadlines.sweep_tournament` só usa `FOR UPDATE` quando há jogo a empatar (consulta prévia sem trava, com os filtros no SQL).
  - Conexão com o banco com `ssl="require"` (verificado: TLS 1.3); `limit`/`offset` negativos → 422.
  - Cabeçalhos de segurança no `frontend/netlify.toml` (CSP com `connect-src` para `*.onrender.com` e `challenges.cloudflare.com` liberado para o Turnstile, anti-iframe, nosniff, HSTS).
  - **Cadastro público configurável** (commit `030dae5`): `ALLOW_REGISTRATION` (padrão **fechado**), `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET` (Cloudflare Turnstile, `services/captcha.py`); `GET /auth/options` informa o site; `RegisterIn.captcha_token`. Front: `components/Turnstile.tsx` e Login esconde "Criar conta" se fechado. Escolha do usuário: cadastro aberto + Turnstile (variáveis a criar no Render). Testes ligam o cadastro via env no `conftest`.
  - Avaliados e pendentes (decisão do usuário): revogar tokens ao trocar senha (precisa de migration), cabeçalhos de segurança no Netlify, atualizar Vite/React Router, banco separado para testes + backup.

## Próxima fase — Fase 10: polimento (em andamento)

O deploy já foi feito (Netlify + Render na `main`). Falta/ideias, em ordem sugerida:
1. **Simular um torneio completo** na produção/local com os usuários `teste*` (grupos + mata-mata + repescagem, adiamento, prazos) e corrigir o que aparecer; depois **desativar/apagar** os usuários e torneios de teste.
2. Revisar mensagens, estados vazios e o uso em **celular**.
3. Pendências do front: **testes automatizados** (nenhum ainda), **editar torneio em rascunho** pela interface (a API tem `PATCH /tournaments/{id}`), **sorteio manual** (`arrangement`) pela interface (a API já aceita), paginação do registro de alterações, trocar `window.confirm` por diálogos próprios.
4. Segurança/operação (continuação da revisão): cabeçalhos de segurança no Netlify, ~~banco separado para testes~~ (feito: projeto Supabase de testes no `.env` local, migrations 0001–0006 aplicadas, RLS conferido), rotina de backup da produção, apagar os `teste*` da produção, revogação de tokens ao trocar senha, atualização de dependências do front.
5. Avaliar notificações no Discord.

## Perguntas em aberto / ideias
- Notificações via Discord (webhook/bot): "interessante, verificar viabilidade depois".
- Personalizações adicionais de formato: o usuário prometeu pedir depois.
- Senha obrigatória a trocar também para senhas digitadas pelo admin? (hoje só as geradas; mudança pequena se quiser.)
- Instalar o GitHub CLI (`gh`) para eu abrir os PRs (o merge continuaria sendo do usuário).

## Front-end (`frontend/`)
```
frontend/
  src/ main.tsx App.tsx api.ts (cliente + tipos) auth.tsx hooks.ts (useLoad com polling) labels.ts styles.css
  src/components/ ui.tsx (Tabs, StandingsTable, MatchRow, BracketMatch, useAction...) SnapshotView.tsx TournamentCard.tsx
  src/pages/ Home Login Account Tournaments TournamentPage MatchPage CreateTournament CreateUser Admin
  src/pages/tournament/ Overview Standings Bracket Matches History Manage
  netlify.toml  public/_redirects  .env.example
```
- **Rotas:** `/` início · `/entrar` · `/torneios` · `/torneios/novo` (staff; aceita `?parent=ID` para subtorneio) · `/torneios/:id` · `/matches/:id` · `/conta` (RequireAuth) · `/admin` e `/admin/usuarios/novo` (só admin; outros são redirecionados ao início). Usuário com `must_change_password` só alcança `/conta`.
- **Padrões:** `api()` em `api.ts` (token no header, erros viram `ApiError` com a mensagem da API; falha de rede = "Não foi possível conectar ao servidor"); `useLoad(fn, deps, pollMs)` carrega e atualiza por polling sem piscar; `useAction()` executa ações e mostra a mensagem de sucesso/erro (`box`), com `setMsg` para recusas prévias (regra 10); tipos das respostas em `api.ts`; textos/rótulos em `labels.ts` (incluindo `actionLabel` da auditoria); estilos em `styles.css` (variáveis CSS, tema escuro).
- **Telas-chave:** página do torneio = abas Visão geral · Tabela · Chaveamento · Confrontos · Histórico (Fases encerradas / Rodada a rodada / Registro de alterações) · Gerenciar (status, jogadores/potes, sorteio com prévia, adiar rodada, **prazo das rodadas**, subtorneios). Página do confronto = placar, avisos (prazo, empate automático, adiado), formulário de reporte do jogador, painel do organizador, reportes e linha do tempo.
- Token JWT em `localStorage` (`torneios.token`); API em `VITE_API_URL` (padrão `http://localhost:8000`; ver `frontend/.env.example`). `frontend/` não é ignorado pelo `.gitignore` (o `frontend/.gitignore` ignora `node_modules`, `dist`, `.env`).
- Rodar tudo localmente: `py main.py` na raiz (sobe API em :8000 e site em :5173; `--status`, `--only back|front`, `--open`, `--install`, `--no-reload`). Só serve ao desenvolvimento local; Ctrl+C encerra os dois. Usa o `backend/.env` (banco de testes).
- Conferir tipos/build: `cd frontend; npm run build`.
- Deploy: ver a seção "Ambiente" (Netlify + Render).

## Fluxo de trabalho e armadilhas

**Sequência correta para mudanças:**
1. *Só front:* eu edito na `front-end` → o usuário testa com `py main.py` → o usuário faz o PR/merge `front-end` → `main` → o Netlify refaz o site sozinho (~1–2 min).
2. *Só back:* eu edito no worktree `D:\Projetos-back` (branch `Back-end`), rodo os testes, commito e dou push → o usuário testa localmente → merge `Back-end` → `main` → o Render refaz o deploy (migrations rodam no start).
3. *Back e front juntos:* **back-end primeiro** na `main`, front depois, para o site novo nunca chamar rota inexistente na produção. Enquanto o back-end não está na `main`, eu posso copiar os arquivos de `D:\Projetos-back\backend` para `D:\Projetos\backend` **sem commitar** na `front-end` só para o usuário testar (e aplicar a migration no banco de testes, se houver).
4. *Depois de qualquer merge na `main`:* atualizar a branch de trabalho com `git fetch; git merge origin/main` na `front-end` (e `git pull` no worktree da `Back-end`). Antes, descartar cópias locais de back-end (`git checkout -- backend` e apagar arquivos novos não rastreados que a `main` já tem), senão o merge recusa. O **`CLAUDE.md` costuma conflitar** (editado nas duas branches): resolver mantendo as duas versões.

**Armadilhas já encontradas:**
- Servidor local com `--reload` pode não recarregar todos os arquivos copiados à mão (sintoma: `405 method not allowed` em rota nova). Reinicie com `py main.py`. Para matar: encerrar quem escuta nas portas 8000/5173 (PowerShell `Get-NetTCPConnection` + `taskkill /T`).
- Um 500 da API não traz cabeçalhos CORS → no navegador parece "falha de conexão". Olhe o log do servidor.
- Heredocs grandes no `bash` do ambiente de trabalho falham com aspas/`EOF`: crie arquivos com a ferramenta Write/Edit. Python no bash é `py`; o venv é `backend/.venv/Scripts/python`.
- Avisos `LF will be replaced by CRLF` do git no Windows são normais.
- Testes que dependem de relógio usam `monkeypatch.setattr(app.services.deadlines, "now", ...)`; qualquer módulo que precise do "agora" do prazo deve chamar `deadlines.now()` pelo módulo (não `from ... import now`).
- Scripts que criam dados reais (ex.: usuários de teste) fazem-se por script Python com `backend/.env`, registram `audit_log` (`user.seed`) e nunca imprimem a connection string.

## Comandos úteis (PowerShell, em `D:\Projetos\backend`)
```
.\.venv\Scripts\python -m pytest                          # testes
.\.venv\Scripts\alembic upgrade head                      # aplicar migrations
.\.venv\Scripts\alembic revision --autogenerate -m "msg"  # nova migration (revisar! lembrar do RLS)
.\.venv\Scripts\python -m app.scripts.create_admin "Nome" # criar/promover admin
.\.venv\Scripts\uvicorn app.main:app --reload             # API em http://localhost:8000 (docs em /docs)
```
Na raiz (`D:\Projetos`): `py main.py` (liga API + site), `py main.py --status`; no front: `cd frontend; npm run build`.
Git: `git fetch; git merge origin/main` (atualizar a branch de trabalho), `git worktree list` (ver `D:\Projetos-back`).
