# Como a plataforma funciona

Guia completo, em linguagem simples, de tudo o que a plataforma de torneios faz e de como as peças se encaixam.
Serve para consultar antes de mudar algo, para explicar a alguém como usar, ou para entender por que algo aconteceu.

> Mantenha este documento atualizado junto com o código: mudou uma regra, atualize a seção correspondente.

## Sumário

1. [Visão geral: as três peças](#1-visão-geral-as-três-peças)
2. [Contas, login e senhas](#2-contas-login-e-senhas)
3. [Papéis: quem pode fazer o quê](#3-papéis-quem-pode-fazer-o-quê)
4. [Torneios: ciclo de vida](#4-torneios-ciclo-de-vida)
5. [Formatos de torneio](#5-formatos-de-torneio)
6. [Configurações do torneio e regras de batalha](#6-configurações-do-torneio-e-regras-de-batalha)
7. [Inscrição, potes, sorteio e início](#7-inscrição-potes-sorteio-e-início)
8. [Confrontos: reporte, validação e correção](#8-confrontos-reporte-validação-e-correção)
9. [Tabela de classificação e desempates](#9-tabela-de-classificação-e-desempates)
10. [Mata-mata](#10-mata-mata)
11. [Fases e regras de passagem (o "motor")](#11-fases-e-regras-de-passagem-o-motor)
12. [Repescagem (subtorneio)](#12-repescagem-subtorneio)
13. [Desistência e W.O.](#13-desistência-e-wo)
14. [Adiamento de jogos e rodadas](#14-adiamento-de-jogos-e-rodadas)
15. [Prazo das rodadas e empate automático](#15-prazo-das-rodadas-e-empate-automático)
16. [Histórico](#16-histórico)
17. [Auditoria e linha do tempo do confronto](#17-auditoria-e-linha-do-tempo-do-confronto)
18. [As telas do site](#18-as-telas-do-site)
19. [Segurança: o que protege a plataforma](#19-segurança-o-que-protege-a-plataforma)
20. [Hospedagem, banco e publicação (deploy)](#20-hospedagem-banco-e-publicação-deploy)
21. [Desenvolvimento local, branches e backup](#21-desenvolvimento-local-e-branches)
22. [O que ainda não existe na interface](#22-o-que-ainda-não-existe-na-interface)
23. [Glossário](#23-glossário)

---

## 1. Visão geral: as três peças

A plataforma é formada por três partes que conversam entre si:

| Peça | O que é | Onde roda | Pasta no repositório |
|---|---|---|---|
| **Site** (front-end) | As páginas que as pessoas veem e clicam (React) | Netlify | `frontend/` |
| **API** (back-end) | O "cérebro": confere permissões, aplica as regras, calcula tabelas | Render | `backend/` |
| **Banco de dados** | Onde tudo fica guardado (usuários, torneios, jogos...) | Supabase (Postgres) | — |

**O caminho de um clique:** a pessoa clica num botão no site → o site manda um pedido para a API → a API confere quem é a
pessoa e se ela pode fazer aquilo → aplica as regras e grava no banco → devolve a resposta → o site mostra o resultado
(ou a mensagem de erro explicando o motivo).

Pontos importantes:
- **O site nunca fala direto com o banco.** Só a API acessa o banco. A "porta pública" do Supabase está fechada (ver seção 19).
- **Qualquer pessoa pode ver** torneios, tabelas, chaveamentos, confrontos e histórico, sem login. **Ações exigem login.**
- **Toda regra vale na API**, não só no site. Mesmo que alguém tente "burlar" o site, a API recusa o que não é permitido.

---

## 2. Contas, login e senhas

### Como alguém ganha uma conta
- **O admin cria** a conta em Administração → Usuários → "Criar usuário" (escolhe nome, papel e, opcionalmente, a senha).
- **Cadastro público** (opcional): a tela "Entrar / Cadastrar" pode permitir que qualquer pessoa crie uma conta de
  jogador. Isso é controlado por variáveis de ambiente no **Render**, sem mexer no código:

  | Configuração no Render | Resultado |
  |---|---|
  | `ALLOW_REGISTRATION` ausente ou `false` (padrão) | Cadastro **fechado**: o botão "Criar conta" some e a tela diz para pedir a conta a um admin |
  | `ALLOW_REGISTRATION=true` | Cadastro **aberto**, sem verificação |
  | `ALLOW_REGISTRATION=true` + `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET` | Cadastro aberto, mas só passa quem resolver a **verificação anti-robô** da Cloudflare |

  Mudar uma variável no Render reinicia a API e vale em seguida; o site pergunta à API (`GET /auth/options`) como o
  cadastro está configurado.

### Verificação anti-robô (Cloudflare Turnstile)
- Na tela de cadastro aparece uma caixinha da Cloudflare. Para a maioria das pessoas ela se resolve sozinha em 1–2
  segundos; só quem parece suspeito precisa clicar.
- Ao passar, o site recebe um **comprovante de uso único** e o envia junto com o cadastro. A API pergunta à Cloudflare se
  o comprovante é válido; sem comprovante válido, a conta não é criada. Robôs que chamam a API direto ficam barrados.
- Barra robôs, não pessoas: alguém determinado ainda pode criar contas à mão, uma a uma.
- O login **não** usa a caixinha (ele já tem o bloqueio de 3 tentativas).
- **Configuração (uma vez):** conta gratuita na Cloudflare → Turnstile → Add widget → em *Hostname*, só o domínio do site
  (ex.: `nome-do-site.netlify.app`, sem `https://` e sem `/`). A Cloudflare gera a **chave do site** (pública →
  `TURNSTILE_SITE_KEY`) e a **chave secreta** (→ `TURNSTILE_SECRET`); as duas vão no Render.
- **Teste local:** no `backend/.env`, use as chaves de teste da Cloudflare, que aprovam sempre e funcionam em qualquer
  endereço: `TURNSTILE_SITE_KEY=1x00000000000000000000AA` e `TURNSTILE_SECRET=1x0000000000000000000000000000000AA`
  (mais `ALLOW_REGISTRATION=true`).
- Se a Cloudflare estiver fora do ar, o cadastro mostra "não foi possível fazer a verificação agora" e pede para tentar de novo.
- **Nome**: 3 a 32 caracteres (letras, números, espaço, ponto, hífen e `_`). Não pode repetir, sem diferenciar maiúsculas
  ("Ash" e "ash" são o mesmo nome).

### Login e o "crachá" (token)
Ao entrar com nome e senha, a API devolve um **crachá digital** (token JWT) que vale **12 horas**. O site guarda esse crachá
no navegador e o apresenta a cada ação. Depois de 12 horas é preciso entrar de novo.
- O crachá é assinado com uma chave secreta (`JWT_SECRET`) que só a API conhece. Sem ela, ninguém consegue fabricar um crachá.
- O papel (admin, organizador, jogador) e se a conta está ativa são **lidos do banco a cada ação**: desativar alguém ou
  mudar o papel vale na hora, mesmo que a pessoa ainda tenha um crachá válido.
- **Trocar ou redefinir a senha desconecta as outras sessões:** todo crachá emitido antes da troca deixa de valer. Quem
  trocou a própria senha continua logado no aparelho onde trocou (recebe um crachá novo); os outros aparelhos voltam a
  aparecer como visitante, com o aviso "Sua sessão terminou". Quando o admin redefine a senha de alguém, todos os
  aparelhos dessa pessoa saem — útil se a senha vazou.

### Bloqueio por tentativas erradas
- **3 senhas erradas seguidas** para o mesmo nome bloqueiam o login daquela conta por **10 minutos** (até a senha certa é
  recusada nesse período). A mensagem diz quantos minutos faltam.
- Quem **já estava logado continua usando** a plataforma normalmente: o bloqueio só impede entrar de novo.
- Um login certo zera a contagem; erros com mais de 10 minutos também deixam de contar.
- O **admin desbloqueia** na hora ao redefinir a senha da pessoa.
- Nomes que não existem são bloqueados do mesmo jeito (para não revelar quais contas existem).
- O bloqueio fica na memória do servidor: se o servidor reiniciar ou "dormir" (ver seção 20), os bloqueios são zerados.

### Regras de senha
- **Mínimo de 8 caracteres** (máximo 128) para qualquer senha nova: cadastro, criação pelo admin, troca e redefinição.
- **Senhas antigas mais curtas** (de antes dessa regra) continuam entrando, mas no login a conta é marcada para
  **troca obrigatória** (mesmo fluxo da senha temporária, abaixo).
- A senha nova precisa ser diferente da atual.

### Senha temporária e troca obrigatória
- Quando o admin cria uma conta **sem informar senha**, ou redefine a senha **sem informar uma nova**, o sistema gera uma
  **senha temporária**, mostrada **uma única vez** para o admin repassar à pessoa por um canal seguro.
- Senha **digitada pelo admin** vale como definitiva (não obriga troca).
- Quem entra com senha temporária (ou com senha antiga curta) é levado para **"Minha conta"** e não acessa mais nada até
  trocar a senha. A API também bloqueia: qualquer ação devolve a mensagem pedindo a troca.

### Como as senhas são guardadas
- A plataforma **nunca guarda a senha em si**, só uma "impressão digital" embaralhada (hash) feita com o **argon2**, o método
  recomendado hoje. Nem quem tem acesso ao banco consegue ver as senhas.
- O argon2 é **lento e pesado de propósito**: isso torna inviável testar milhões de senhas caso alguém roube o banco.
- Usamos os parâmetros mínimos recomendados pela OWASP (cerca de 19 MB de memória por cálculo), adequados ao servidor gratuito.
- O cálculo roda **em segundo plano** (numa linha de execução separada), com no máximo **2 cálculos ao mesmo tempo**: assim
  um login não deixa a API parada para os outros e uma rajada de logins não esgota a memória.
- Cada hash guarda os próprios parâmetros. Senhas guardadas com parâmetros antigos continuam funcionando e são
  **recalculadas automaticamente** no próximo login da pessoa, sem ela perceber.
- Ao entrar com um nome inexistente, a API gasta o mesmo tempo que gastaria com um nome real: não dá para descobrir
  quais nomes existem pelo tempo de resposta.

---

## 3. Papéis: quem pode fazer o quê

| Papel | Pode |
|---|---|
| **Admin** | Tudo: criar usuários, mudar papéis, redefinir senhas, desativar contas, ver a auditoria, gerenciar **qualquer** torneio, validar/corrigir/invalidar resultados, apagar torneios |
| **Organizador** | Criar torneios e gerenciar **apenas os que criou** (inscrever jogadores, potes, sorteio, prazos, adiamentos, validar resultados). Só apaga torneio em rascunho |
| **Jogador** | Reportar o resultado dos **próprios** confrontos, desistir de um torneio, trocar a própria senha. **Não se inscreve sozinho** |
| **Visitante (sem login)** | Ver torneios, tabelas, chaveamentos, confrontos, histórico e linha do tempo dos confrontos |

Limites de segurança do admin: não pode tirar o próprio acesso de admin nem desativar a própria conta (para nunca ficar
sem nenhum admin). O primeiro admin é criado por um script no servidor (`python -m app.scripts.create_admin "Nome"`).

---

## 4. Torneios: ciclo de vida

Todo torneio passa por estes estados:

```
rascunho ──► inscrições ──► em andamento ──► encerrado
   │  ▲          │
   │  └──────────┘ (volta para rascunho)
   └──────► cancelado ◄── (de rascunho, inscrições ou em andamento)
```

| Estado | O que significa |
|---|---|
| **Rascunho** | Recém-criado; dá para mexer em tudo |
| **Inscrições** | Aberto para o organizador inscrever jogadores (ainda editável) |
| **Em andamento** | Sorteio feito, confrontos gerados; jogos sendo disputados |
| **Encerrado** | Todas as fases terminaram (automático) ou o organizador encerrou manualmente |
| **Cancelado** | Interrompido; nada mais acontece |

- **Iniciar** só acontece pelo botão **"Sortear e iniciar"** (não por troca de estado) e exige **exatamente** o número
  máximo de jogadores inscritos.
- **Encerramento automático:** quando o último jogo da última fase é validado, o torneio passa a "encerrado" sozinho.
  Se depois um resultado for invalidado, ele **volta** a "em andamento".
- **Encerrar manualmente** é recusado se houver jogo **adiado** ainda pendente.
- **Apagar:** o organizador só apaga o próprio torneio em rascunho; o admin apaga qualquer um (leva junto subtorneios,
  jogos e histórico; a auditoria guarda o registro de que foi apagado).

---

## 5. Formatos de torneio

Um torneio é uma **sequência de fases**, ligadas por **regras de passagem** (quem sai de uma fase e vai para a outra).
Os modelos prontos montam isso sozinhos:

| Modelo | Como funciona |
|---|---|
| **Pontos corridos (liga)** | Todos contra todos (turno, ou turno e returno). Vence quem fizer mais pontos |
| **Mata-mata** | Eliminação simples: quem perde sai. Número de jogadores precisa ser potência de 2 (4, 8, 16, 32...) |
| **Grupos + mata-mata** | Jogadores sorteados em grupos (A, B, C...), todos contra todos dentro do grupo; os melhores de cada grupo vão para o mata-mata com cruzamento fixo |
| **Personalizado (custom)** | Qualquer combinação de fases e regras, montada no editor visual da tela de criação (seção 11) |

### Tipos de fase (usados no personalizado)
| Tipo | O que é |
|---|---|
| `league` | Pontos corridos |
| `groups` | Fase de grupos |
| `knockout` | Mata-mata |
| `round` | Rodada única: jogadores em pares, um jogo cada |
| `playoff` | Repescagem interna/disputa entre pares (como `round`, usada para decidir vagas) |

### Grupos + mata-mata em detalhe
- O número de grupos é sugerido pelo total de jogadores (~4 por grupo), mas pode ser escolhido.
- **Grupos de tamanhos diferentes** são permitidos (ex.: 14 jogadores em 4 grupos = 4, 4, 3 e 3). Os classificados e a
  posição que vai à repescagem precisam existir **no menor grupo** (com grupos de 3, no máximo 2 classificados), e a
  criação explica o problema se não existirem. A eliminação vale para quem existe: o grupo de 3 simplesmente não tem 4º.
- Define-se quantos se classificam por grupo (ex.: 2).
- **Cruzamento fixo:** grupos pareados (A com B, C com D...). O 1º de um grupo enfrenta o 2º do grupo parceiro
  (1ºA × 2ºB, 1ºB × 2ºA), e as chaves são intercaladas para que jogadores do mesmo grupo só se reencontrem tarde.
- O total de classificados precisa ser potência de 2. O número de grupos precisa ser par.
- Pode reservar vagas no mata-mata para quem volta da repescagem (seção 12).

---

## 6. Configurações do torneio e regras de batalha

| Configuração | Padrão | O que faz |
|---|---|---|
| Pontos por vitória / empate / derrota | 3 / 1 / 0 | Pontuação da tabela |
| Melhor de N | 1 | Série de 1, 3, 5 ou 7 jogos por confronto |
| Permitir empate | Liga/grupos: sim; mata-mata: não | Se o confronto pode terminar empatado |
| Turno e returno | Não | Cada par se enfrenta duas vezes |
| Disputa de 3º lugar | Não | No mata-mata, os perdedores das semifinais jogam pelo 3º |
| Placar do W.O. | 3 | W.O. conta como vitória por 3×0 (3 de saldo) |
| Critérios de desempate | saldo → vitórias → confronto direto | Ordem configurável |

**Regras de batalha** (informativas, mostradas na página do torneio e do confronto): formato (singles/doubles), jogo,
tier, tamanho do time, quantos levar para a batalha, nível máximo, timer, e se o **replay do Showdown é obrigatório**
(padrão: sim). Há também um campo de texto livre para regras adicionais.
- **Cláusulas não são informadas no site:** são definidas automaticamente pelo tier no Showdown.
- **Tamanho do time** = Pokémon registrados; **levar** = quantos entram em cada batalha (ex.: VGC leva 4 de 6).
  O máximo de "Pokémon vivos" aceito no reporte é o número que entra na batalha (ou o tamanho do time, ou 6).

---

## 7. Inscrição, potes, sorteio e início

### Inscrição
- Só o **admin ou o organizador do torneio** inscreve jogadores (aba Gerenciar → Jogadores, buscando pelo nome).
- Só antes do início (rascunho ou inscrições), e sem passar do máximo de jogadores.
- Contas desativadas não podem ser inscritas.
- Remover um jogador antes do início simplesmente o tira da lista.

### Potes (opcional)
- Cada jogador pode receber um **pote** (1 = mais forte). Se algum jogador tiver pote, **todos** precisam ter.
- **Em grupos:** cada grupo recebe um jogador de cada pote (os potes devem ter o tamanho do número de grupos).
- **No mata-mata:** os potes viram cabeças de chave (pote 1 = cabeças), na chave padrão 1º × último, 2º × penúltimo...

### Sorteio
- **"Prévia do sorteio"** mostra os confrontos que seriam gerados, **sem salvar nada**. Dá para repetir quantas vezes quiser.
- Cada sorteio tem um número de **semente (seed)**: a mesma semente gera sempre o mesmo resultado. Usar a semente da prévia
  no início garante que o resultado será exatamente o que foi visto.
- Modos: **aleatório**, **por potes** (se houver potes) ou **manual** (arranjo definido à mão; hoje só pela API, ver seção 22).
- **"Sortear e iniciar"** confirma o sorteio, gera os confrontos da 1ª fase e muda o torneio para "em andamento".
- O sorteio fica **registrado publicamente** (semente, modo, potes, quem sorteou e quando), para transparência.

---

## 8. Confrontos: reporte, validação e correção

### Estados de um confronto
| Estado | Significado |
|---|---|
| **Agendado** | Esperando o jogo/reporte |
| **Reportado** | Um jogador enviou o resultado; aguarda o organizador |
| **Validado** | Resultado oficial; conta na tabela/chaveamento |
| **Anulado** | Confronto cancelado (não conta) |

### Reporte pelo jogador
- **Só um dos dois jogadores** do confronto reporta, e só com o torneio em andamento e os dois jogadores definidos.
- Informa: vitórias de cada um na série, **Pokémon vivos** de cada um ao final, links de **replay** e observações.
- **Replay obrigatório** (se o torneio exigir): precisa ser um link `https://replay.pokemonshowdown.com/...`; no máximo
  um link por jogo da série.
- **Empate** só é aceito como **0×0** e só onde o torneio permite.
- Em melhor de 1, o vencedor tem pelo menos 1 Pokémon vivo e o perdedor 0.
- Um reporte novo **substitui** o pendente anterior.
- Quem desistiu do torneio não pode mais reportar.

### Ações do organizador (página do confronto → Painel do organizador)
| Ação | O que faz |
|---|---|
| **Validar** | Aceita o reporte pendente (pode marcar como empate, que vira 0×0) |
| **Rejeitar** | Recusa o reporte; o confronto volta a "agendado" |
| **Lançar resultado** | Registra o resultado direto, sem reporte (também serve para **corrigir** um já validado) |
| **W.O.** | Dá a vitória a um dos jogadores por W.O. (3×0 por padrão) |
| **Invalidar** | Desfaz um resultado validado; o confronto volta a "agendado" e tudo é recalculado |
| **Adiar / retomar** | Ver seção 14 |

Toda ação é registrada na auditoria e na linha do tempo do confronto (seção 17).

### Correção em cascata (por que às vezes aparece "409")
No mata-mata e entre fases, um resultado alimenta o jogo seguinte. Se você muda o **vencedor** de um confronto cujo jogo
seguinte **já tem reporte ou resultado**, a API **recusa** (erro 409) e não grava nada, para não bagunçar o que já foi
jogado. A solução é **invalidar de trás para frente**: primeiro o jogo mais adiante, depois o anterior.
Mudar só os Pokémon restantes (mesmo vencedor) é sempre permitido.

---

## 9. Tabela de classificação e desempates

- A tabela **nunca é guardada pronta**: é **recalculada** a partir dos confrontos validados toda vez que alguém a abre.
  Por isso uma correção reflete na hora.
- **Pontos:** vitória 3, empate 1, derrota 0 (configurável).
- **Saldo** = Pokémon vivos do jogador − Pokémon vivos do adversário, somado jogo a jogo. **Só conta em melhor de 1**.
- **Desempate** (ordem padrão): saldo → vitórias → **confronto direto** (pontos só nos jogos entre os empatados).
  Persistindo o empate, ordem alfabética.
- A coluna **J** (jogos disputados) mostra quem tem jogo a menos (útil com jogos adiados).
- Jogador que desistiu aparece marcado na tabela.

---

## 10. Mata-mata

- **Eliminação simples, sem "byes"** (ninguém passa de fase sem jogar): por isso o número de jogadores é potência de 2.
  Casos diferentes se resolvem no modelo personalizado com uma fase preliminar.
- **Nunca há empate** no mata-mata, mesmo que o torneio permita empate em outras fases.
- O vencedor validado **avança sozinho** para o próximo confronto. Só se pode reportar quando os dois jogadores estão definidos.
- **Disputa de 3º lugar** (opcional): alimentada automaticamente pelos perdedores das semifinais.
- A aba **Chaveamento** mostra as rodadas (oitavas, quartas, semifinal, final), o 3º lugar e o **campeão**.

---

## 11. Fases e regras de passagem (o "motor")

Nos torneios com mais de uma fase, o "motor" decide **quem vai para onde** quando uma fase termina.

**Uma regra de passagem diz:** "da fase X, as posições A a B vão para [destino], a partir da vaga N".

**De onde saem os jogadores (fonte):**
- **ranking** — a classificação final da fase (na liga, a tabela; nos grupos, posição no grupo; no mata-mata, campeão,
  vice, 3º...);
- **vencedores / perdedores** — de fases `round`/`playoff`, ordenados por saldo (empate de saldo é decidido por sorteio
  reproduzível);
- **posição no grupo** — ex.: "1º de cada grupo".

**Para onde vão (destino):** outra fase (em vagas específicas), **eliminados**, **repescagem** (seção 12) ou, num
subtorneio, **de volta ao torneio principal**.

**Quando acontece:** uma fase só é montada quando **todas** as fases que a alimentam terminaram. Os confrontos da nova
fase são gerados sozinhos (sorteados com semente derivada do sorteio inicial, ou nas vagas definidas pela regra).

**Se algo mudar depois:** se uma fase de origem for corrigida e a fase seguinte **ainda não teve nenhum reporte**, a
fase seguinte é **refeita** automaticamente (ou desfeita, se a origem foi reaberta; eliminados voltam a ativos). Se a fase
seguinte já teve jogo reportado, a API recusa (409): invalide de trás para frente.

**Exemplo (personalizado):** 20 jogadores fazem uma rodada única de 10 confrontos; os 6 melhores vencedores (por saldo)
vão direto ao mata-mata de 8; os 4 piores perdedores jogam um playoff; os 2 vencedores do playoff completam as 8 vagas.

### O editor do torneio personalizado
Na tela "Novo torneio", com o modelo **Personalizado**, aparece o bloco **Estrutura do torneio** (sem JSON na tela):
- **Fases:** cada fase tem nome, tipo e só as opções que fazem sentido para aquele tipo — "melhor de", turno e returno
  (liga/grupos), número de grupos (vazio = automático), disputa de 3º lugar e montagem da chave (mata-mata: automática,
  1º × último, ou na ordem das vagas), pares sorteados ou melhor × pior (rodada única/playoff a partir da 2ª fase) e
  **vagas reservadas para quem volta da repescagem**. Dá para reordenar (↑ ↓) e remover fases. Ao lado do número da fase
  aparece quantos jogadores ela vai receber.
- **Regras de passagem:** cada regra é uma linha "Da fase X · quem · da posição A até B · vão para (outra fase /
  eliminados / repescagem / torneio principal) · a partir da vaga N". As opções de "quem" mudam conforme o tipo da fase
  (ex.: "posição em cada grupo" só aparece em fase de grupos). Abaixo de cada regra aparece a frase do que ela faz, por
  exemplo: *"Da fase 1: do 1º ao 2º de cada grupo (8 jogadores) vão para a fase 2 ("Mata-mata"), vagas 1 a 8."*
  Grupos que alimentam um mata-mata podem usar o **cruzamento fixo** (1ºA × 2ºB...).
- **Verificação:** o editor confere a estrutura enquanto você monta (mesmas regras do servidor: tamanhos de cada fase,
  vagas sem buraco e sem sobreposição, mata-mata em potência de 2, número par em rodada única/playoff, etc.) e lista o
  que precisa ajustar. Com algum problema, o botão "Criar torneio" explica o motivo em vez de enviar.
- **Subtorneio (repescagem):** a regra "torneio principal" lista as fases do principal com as vagas que cada uma reservou.
- Ao criar, a API confere tudo de novo e explica o erro se algo não fizer sentido.

---

## 12. Repescagem (subtorneio)

A repescagem é um **torneio filho** (subtorneio) ligado ao torneio principal. Só existe **um nível**: subtorneio não tem
subtorneio.

**Como entra quem vai para a repescagem:**
- **Automático:** uma regra do principal (ex.: "o 3º de cada grupo vai para a repescagem"). Quando a fase de origem
  termina, esses jogadores são **inscritos sozinhos** no subtorneio. Se a fase for reaberta, eles saem.
- **Manual:** o organizador inscreve jogadores do principal no subtorneio.
- Só jogadores do torneio principal (que não desistiram) podem entrar.
- Com mais de um subtorneio, é preciso escolher qual recebe os candidatos (aba Gerenciar → Subtorneios).

**Como volta quem vence a repescagem:**
- O mata-mata do principal **reserva vagas** para quem volta da repescagem (ex.: 6 classificados diretos + 2 vagas de
  repescagem = 8). O mata-mata só é montado quando os grupos **e** a repescagem terminam.
- Os classificados diretos enfrentam os que voltaram da repescagem (chave padrão).

**Regras de início e desistência:**
- O subtorneio só começa com o principal **em andamento** e com o número exato de jogadores.
- Depois que o subtorneio começa, a lista dele não muda mais.
- Quem desiste do principal sai também da repescagem; desistir só da repescagem não afeta o principal.

---

## 13. Desistência e W.O.

- **Antes do início:** o jogador simplesmente sai da lista.
- **Com o torneio em andamento:** o jogador fica marcado como "desistiu" e **todos os jogos dele ainda sem reporte**
  viram **vitória por W.O.** para os adversários (3×0, +3 de saldo).
- Se já havia um **reporte pendente** antes da desistência, ele **permanece** e o organizador valida normalmente.
- Jogos já validados **não mudam**.
- **No mata-mata:** o adversário vence por W.O. e avança. Se o adversário ainda não estava definido, o W.O. é aplicado
  assim que ele chegar ao confronto. Se os dois desistirem, o organizador resolve manualmente.
- O organizador pode remover um jogador (mesmo efeito da desistência).

---

## 14. Adiamento de jogos e rodadas

Vale só para **pontos corridos e fase de grupos**, e só **admin/organizador do torneio** adia.

- Adia-se **um jogo** (página do confronto) ou **os jogos pendentes de uma rodada** (aba Gerenciar → Adiar rodada;
  opcionalmente só de um grupo), com um motivo.
- O jogo adiado **continua podendo ser reportado** a qualquer momento.
- **A fase e o torneio não encerram** enquanto houver jogo adiado pendente.
- **Retomar** desfaz o adiamento enquanto o jogo não foi disputado.
- No histórico, a tabela da rodada original fica registrada **sem** o jogo adiado (com a anotação de adiamento); quando
  o jogo for disputado, ele entra na tabela da rodada que fechar em seguida.

---

## 15. Prazo das rodadas e empate automático

O organizador define a **data e hora limite de cada rodada** (aba Gerenciar → Prazo das rodadas). Datas já passadas
não são aceitas. Remover o prazo é possível.

**Quando o prazo vence:**
| Situação | O que acontece |
|---|---|
| Liga ou grupos, torneio que **permite empate** | Jogos ainda **agendados** (sem reporte, não adiados) viram **empate 0×0 automático** |
| Mata-mata, rodada única, playoff, ou torneio **sem empate** | Nada é decidido; o confronto mostra o aviso **"prazo vencido"** para o organizador resolver (W.O., resultado, adiamento) |

- Jogo com **reporte pendente nunca** é empatado automaticamente (o organizador valida o reporte).
- Jogo **adiado** não é empatado.
- **Invalidar** um empate automático **libera** o jogo: os jogadores podem entregar atrasado e o prazo não age mais nele.
  Retomar um jogo adiado depois do prazo também o libera.
- O empate automático aparece como "empate por prazo" e fica na auditoria sem autor (foi o sistema).

**Como o sistema percebe que o prazo venceu:**
- Uma tarefa na API verifica os prazos **a cada 60 segundos**.
- Como o servidor gratuito "dorme" quando ninguém usa (seção 20), a verificação **também acontece quando alguém abre** o
  torneio, a tabela, os confrontos, o chaveamento ou um confronto. Assim o empate aparece mesmo que o servidor tenha dormido.
- Essa verificação é feita **sem travar** nada no caso comum: primeiro o sistema só olha se existe algum jogo para
  empatar; só se existir ele "reserva" esses jogos e aplica o empate. Assim as visitas às páginas não atrasam a
  validação de resultados.

---

## 16. Histórico

A aba **Histórico** tem três partes:

| Parte | O que mostra |
|---|---|
| **Fases encerradas** | O estado final de cada fase: tabela final da liga, tabelas finais dos grupos, chaveamento final e classificação do mata-mata, e as fases da repescagem. Se uma correção posterior mudar o resultado, vale a versão mais nova (e o número de versões aparece) |
| **Rodada a rodada** | A tabela **congelada ao fim de cada rodada** de pontos corridos/grupos, desde a primeira. Mostra jogos adiados pendentes e jogos adiados que foram disputados depois |
| **Registro de alterações** | Uma "foto" da tabela a cada mudança relevante (validação, correção, W.O., adiamento...), com o motivo |

- A tabela de uma rodada já fechada **não é alterada depois**. Se uma rodada fechada voltar a ter jogo em aberto (por
  invalidação), ela é marcada como **reaberta** e, ao fechar de novo, ganha um registro novo.

---

## 17. Auditoria e linha do tempo do confronto

- **Auditoria** (Administração → Auditoria, só admin): lista tudo o que foi feito na plataforma — quem fez, o quê,
  quando e em quê (criação de usuários, mudanças de papel, redefinições de senha, criação/alteração de torneios,
  validações, W.O., adiamentos, prazos, empates automáticos...). Tem filtros e paginação.
  **Senhas nunca aparecem** na auditoria.
- **Linha do tempo do confronto** (pública, na página do confronto): reportes, revisões do organizador e ações
  (validar, corrigir, invalidar, W.O., adiar) em ordem. Atenção: as **observações** escritas nos reportes e nas
  revisões ficam **visíveis para todos**.

---

## 18. As telas do site

| Tela | Endereço | Conteúdo |
|---|---|---|
| Início | `/` | Torneios em andamento, com inscrições abertas e encerrados recentemente; "Seus jogos pendentes" para quem está logado |
| Entrar / Cadastrar | `/entrar` | Login e cadastro |
| Torneios | `/torneios` | Lista de torneios; botão **"Novo torneio"** (admin/organizador) |
| Novo torneio | `/torneios/novo` | Criação com modelo pronto ou personalizado (editor visual de fases e regras). Com `?parent=ID`, cria um subtorneio |
| Torneio | `/torneios/:id` | Abas: **Visão geral**, **Tabela**, **Chaveamento**, **Confrontos**, **Histórico** e **Gerenciar** (só admin/organizador do torneio) |
| Confronto | `/matches/:id` | Placar, avisos (prazo, empate automático, adiado), formulário de reporte, painel do organizador, reportes e linha do tempo |
| Minha conta | `/conta` | Dados da conta e troca de senha |
| Administração | `/admin` | Só admin: abas **Usuários** (criar, papel, ativar/desativar, redefinir senha) e **Auditoria** |
| Criar usuário | `/admin/usuarios/novo` | Formulário de criação; ao concluir volta para a lista mostrando a senha temporária, se houver |

**A aba Gerenciar** reúne: situação do torneio (abrir inscrições, voltar a rascunho, cancelar, encerrar manualmente,
apagar), jogadores e potes, sorteio (prévia e "Sortear e iniciar"), adiar rodada, prazo das rodadas e subtorneios
(criar e ligar à regra de repescagem).

**Comportamentos gerais do site:**
- **Atualização automática:** as páginas se atualizam sozinhas a cada 15–30 segundos, **só enquanto a aba está visível**.
- **Botões explicam o motivo:** quando uma ação não é possível (ex.: sortear sem jogadores suficientes), o botão continua
  clicável e mostra **por que** não dá.
- **Sem acesso:** quem não é admin e tenta abrir a Administração é levado ao início; quem precisa trocar a senha só
  consegue abrir "Minha conta".
- **Falha de conexão:** aparece "Não foi possível conectar ao servidor" (também acontece no primeiro acesso depois de o
  servidor dormir: espere alguns segundos e tente de novo).

---

## 19. Segurança: o que protege a plataforma

| Proteção | O que impede |
|---|---|
| Senhas com argon2 (seção 2) | Mesmo com o banco roubado, as senhas não podem ser lidas e são muito caras de adivinhar |
| Bloqueio de 3 tentativas por 10 min | Adivinhar senhas testando várias seguidas |
| Senha mínima de 8 caracteres | Senhas fáceis demais |
| Senha temporária com troca obrigatória | Que a senha que o admin viu continue valendo |
| Troca/redefinição de senha invalida crachás antigos | Que alguém que descobriu a senha continue logado depois da troca |
| Crachá (token) assinado com `JWT_SECRET` | Que alguém finja ser outra pessoa ou se passe por admin |
| API recusa iniciar sem `JWT_SECRET` forte | Que um esquecimento na configuração deixe a chave padrão (pública) em uso |
| Permissões conferidas na API a cada ação | Que alguém faça pelo "lado de fora" o que o site não deixa |
| Papel e conta ativa lidos do banco a cada ação | Que uma conta desativada continue agindo |
| Consultas ao banco parametrizadas (SQLAlchemy) | "Injeção de SQL" (enviar comandos ao banco disfarçados de texto) |
| React trata texto como texto; replays só aceitam o site do Showdown | Que alguém injete código malicioso nas páginas (XSS) |
| Banco com RLS ativo e acesso público revogado | Que alguém leia ou altere o banco pela "porta pública" do Supabase |
| Conexão com o banco sempre criptografada (TLS) | Que alguém no meio do caminho leia os dados trocados entre a API e o banco |
| CORS: a API só aceita chamadas de navegador vindas do site oficial | Que outro site use o login de um visitante para agir na plataforma |
| Cadastro fechado por padrão, ou aberto com verificação anti-robô | Criação de contas em massa por robôs |
| Cabeçalhos de segurança do site (`frontend/netlify.toml`) | O navegador só roda código do próprio site e só conversa com ele e com a API (CSP); ninguém consegue embutir o site em outra página para enganar cliques; o site é sempre aberto por HTTPS |
| Segredos fora do Git (`.env` ignorado) | Vazamento de senha do banco e da chave do crachá |
| Auditoria de todas as ações | Ações sem rastro |

**Sobre a `JWT_SECRET` (chave do crachá):**
- Fica só nas variáveis do Render (produção) e no `backend/.env` (local). Deve ter **pelo menos 32 caracteres aleatórios**
  e ser **diferente** entre produção e local.
- Para gerar uma nova: `py -c "import secrets; print(secrets.token_urlsafe(48))"`.
- **Trocar a chave desconecta todo mundo** (todos precisam entrar de novo) — útil se suspeitar de vazamento.
- Nunca cole essa chave nem o conteúdo do `.env` em conversas, prints ou commits.

**Atenção:** se a API mudar para um endereço fora de `onrender.com`, o novo endereço precisa entrar no `connect-src` do
`frontend/netlify.toml`, senão o site não consegue falar com ela.

---

## 20. Hospedagem, banco e publicação (deploy)

### Onde cada peça roda
- **Site → Netlify.** Publica o conteúdo de `frontend/` da branch `main`. A variável `VITE_API_URL` diz ao site onde está
  a API; ela é "embutida" na hora de montar o site, então mudar a variável exige novo deploy.
- **API → Render** (plano gratuito). Publica `backend/` da branch `main`. Ao iniciar, aplica as migrations do banco e
  sobe a API. Variáveis: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS` (endereço do site) e, para o cadastro público,
  `ALLOW_REGISTRATION`, `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET` (seção 2).
  **Dorme** depois de ~15 minutos sem uso; o primeiro acesso depois disso leva cerca de 1 minuto.
- **Banco → Supabase** (Postgres, plano gratuito).

### As portas do banco: 6543 e 5432
O Supabase oferece duas formas de entrar no mesmo banco:
- **6543 — Transaction pooler:** cada comando pega uma conexão emprestada e devolve logo. Aguenta muitos acessos com
  poucas conexões. **É a usada pela API.** Por não manter "comandos preparados" entre usos, a API desliga esse recurso
  (sem isso aparecia o erro intermitente "prepared statement does not exist").
- **5432 — Session pooler:** a conexão fica presa ao programa enquanto ele estiver conectado. **É a usada pelas
  migrations**, que precisam de conexão contínua; a troca de 6543 para 5432 é automática.

### Como uma mudança chega ao ar
1. A mudança é feita na branch de trabalho (`Back-end` para a API, `front-end` para o site).
2. É testada localmente.
3. O dono do projeto abre o Pull Request e faz o **merge na `main`**.
4. O Render e o Netlify percebem a mudança na `main` e **publicam sozinhos** (1 a 3 minutos).
5. **Ordem quando há mudança nos dois:** primeiro a API (back-end), depois o site, para o site novo nunca chamar algo
   que a API ainda não tem.

**Se um deploy der errado:** no Render, um deploy que falha ao iniciar não substitui a versão que está no ar. Para
voltar uma versão: Netlify → Deploys → "Publish deploy" de um anterior; Render → redeploy de um commit anterior.

---

## 21. Desenvolvimento local e branches

- **`py main.py`** (na raiz do projeto) liga a API (http://localhost:8000) e o site (http://localhost:5173) juntos.
  Opções: `--status`, `--only back|front`, `--open`, `--install`, `--no-reload`. Ctrl+C desliga os dois.
- **Banco de testes:** o ambiente local usa um **projeto separado do Supabase** (o `DATABASE_URL` do `backend/.env`).
  O que você cria, altera ou apaga testando localmente **não** aparece no site real. A produção usa o banco configurado
  no Render. Usuários de teste do banco local: `teste1` a `teste16`, senha `12345678`.
- **Migrations:** rodar `alembic upgrade head` localmente altera só o banco de testes. Na produção, a migration é aplicada
  pelo Render ao publicar a versão nova. Assim dá para testar a migration antes de ela chegar ao site real.
- **Nunca** coloque a URL do banco de produção no `backend/.env` (guarde-a num gerenciador de senhas).
- **Testes automáticos da API:** `cd backend; .\.venv\Scripts\python -m pytest` (usam um banco temporário em memória,
  nunca o real).

### Branches
| Branch | Para quê |
|---|---|
| `main` | Produção: o que está no ar. Só recebe merge |
| `Back-end` | Trabalho na API (`backend/`) |
| `front-end` | Trabalho no site (`frontend/`), `main.py` e documentação |

Para funcionalidades grandes e novas (ex.: um "acervo"), o recomendado é criar **branches de funcionalidade a partir da
`main`** no mesmo repositório (ex.: `acervo-back`, `acervo-front`) e fazer o merge quando estiver pronto — não um fork.

### Backup, restauração e limpeza de contas (scripts)
O plano gratuito do Supabase não oferece um backup que você mesmo restaure, então a plataforma tem scripts próprios.
Todos rodam no terminal, em `D:\Projetos\backend`. **Sem `--prod`** usam o banco de testes (do `.env`); **com `--prod`**
pedem a URL do banco de produção, que é colada sem aparecer na tela, vale só naquela execução e não é gravada.
Todos mostram qual banco estão usando (pelo código do projeto no Supabase) antes de fazer qualquer coisa.

| Para quê | Comando |
|---|---|
| **Backup** (só lê; salva um arquivo `.json` em `C:\Users\<você>\Backups-torneios`) | `.\.venv\Scripts\python -m app.scripts.backup --prod` |
| **Conferir** se um backup é restaurável (faz tudo e desfaz no final) | `.\.venv\Scripts\python -m app.scripts.restore ARQUIVO.json --simular --substituir` |
| **Restaurar** um backup (pede para digitar RESTAURAR) | `.\.venv\Scripts\python -m app.scripts.restore ARQUIVO.json --prod` (banco vazio) ou `... --substituir` (apaga o que existe antes) |
| **Apagar contas de vez** (a interface só desativa; pede para digitar APAGAR) | `.\.venv\Scripts\python -m app.scripts.delete_users nome1 nome2 --prod` ou `--padrao "^teste"` |

- O arquivo de backup tem dados pessoais e as impressões (hashes) das senhas: guarde-o num lugar seguro (ex.: uma pasta
  de nuvem particular) e **nunca** dentro do projeto — o script recusa salvar na pasta do repositório.
- A restauração exige que o banco esteja com as **mesmas migrations** do backup e acontece numa única transação: se
  algo falhar, nada muda.
- `delete_users` mostra antes as contas e os torneios de que elas participam. Se houver torneios, só segue com
  `--com-torneios` (apagar só as contas deixaria confrontos sem jogador) e avisa quando há participantes de fora da
  lista. **Admins nunca são apagados.** Faça um backup antes.
- **Sugestão de rotina:** um backup da produção antes de cada merge com migration e, fora isso, uma vez por semana ou
  antes/depois de cada torneio. Guarde alguns dos mais recentes.
- Por que não automático pelo GitHub: o repositório é público, e um backup gerado lá ficaria acessível a outras pessoas.

---

## 22. O que ainda não existe na interface

Estas coisas a API já faz, mas o site ainda não tem botão:
- **Desistência pelo próprio jogador** (`POST /tournaments/{id}/withdraw`); hoje o organizador remove o jogador pela aba Gerenciar.
- **Sorteio manual** (montar grupos/chave à mão).
- **Editar um torneio em rascunho** (nome, regras, configuração).

Outras pendências: testes automáticos do site, paginação do registro de alterações e notificações (ex.: Discord).

---

## 23. Glossário

| Termo | Significado |
|---|---|
| **API** | O programa no servidor que recebe os pedidos do site e aplica as regras |
| **Admin / Organizador / Jogador** | Os papéis (seção 3) |
| **Branch** | Uma "linha" de desenvolvimento no Git; a `main` é a que está no ar |
| **Cascata** | Quando um resultado alimenta o jogo seguinte (e mudar um afeta o outro) |
| **CORS** | Regra do navegador que só deixa o site oficial chamar a API |
| **Crachá / token / JWT** | Comprovante digital de login, válido por 12 h |
| **Deploy** | Publicar uma versão nova no ar |
| **Hash** | "Impressão digital" embaralhada da senha; não dá para voltar à senha original |
| **Merge** | Juntar as mudanças de uma branch em outra |
| **Migration** | Script que altera a estrutura do banco (criar coluna, tabela...) |
| **Pote** | Grupo de força dos jogadores para o sorteio (1 = mais forte) |
| **RLS** | Trava do Supabase que bloqueia o acesso público às tabelas |
| **Saldo** | Pokémon vivos do jogador − do adversário (só em melhor de 1) |
| **Seed / semente** | Número que determina o resultado do sorteio (mesma semente, mesmo sorteio) |
| **Snapshot** | "Foto" da tabela guardada no histórico |
| **Subtorneio** | Torneio filho ligado ao principal (usado para a repescagem) |
| **W.O.** | Vitória sem jogo (adversário não jogou ou desistiu): 3×0 |
| **Erro 409** | "Conflito": a ação não pode ser feita no estado atual (a mensagem explica o motivo) |
| **Erro 422** | Dados inválidos no formulário (a mensagem diz qual campo) |
| **Erro 429** | Muitas tentativas: o login está bloqueado temporariamente |
