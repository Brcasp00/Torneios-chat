export const tournamentStatus: Record<string, string> = {
  draft: "Rascunho",
  registration: "Inscrições",
  running: "Em andamento",
  finished: "Encerrado",
  cancelled: "Cancelado",
};

export const matchStatus: Record<string, string> = {
  scheduled: "Agendado",
  reported: "Aguardando validação",
  validated: "Validado",
  void: "Anulado",
};

export const stageType: Record<string, string> = {
  league: "Pontos corridos",
  groups: "Fase de grupos",
  knockout: "Mata-mata",
  round: "Rodada única",
  playoff: "Playoff",
};

export const template: Record<string, string> = {
  league: "Pontos corridos",
  knockout: "Mata-mata",
  groups_knockout: "Grupos + mata-mata",
  custom: "Personalizado",
};

export const roleLabel: Record<string, string> = { admin: "Admin", organizer: "Organizador", player: "Jogador" };

export const playerStatus: Record<string, string> = { active: "Ativo", eliminated: "Eliminado", withdrawn: "Desistiu" };

export const actionLabel: Record<string, string> = {
  "match.report": "Reporte enviado",
  "match.validate": "Resultado validado",
  "match.reject": "Reporte rejeitado",
  "match.set_result": "Resultado lançado/corrigido",
  "match.walkover": "W.O. aplicado",
  "match.invalidate": "Resultado invalidado",
  "match.postpone": "Jogo adiado",
  "match.resume": "Adiamento removido",
  "match.settings": "Escolhas do mandante definidas",
  "report.validated": "Reporte aprovado",
  "report.rejected": "Reporte rejeitado",
  "match.auto_draw": "Empate automático por prazo vencido",
  "stage.set_deadlines": "Prazos das rodadas definidos",
  "round.postpone": "Rodada adiada",
  "round.resume": "Adiamento da rodada removido",
  "tournament.create": "Torneio criado",
  "tournament.create_sub": "Subtorneio criado",
  "tournament.update": "Torneio editado",
  "tournament.start": "Torneio iniciado (sorteio)",
  "tournament.set_status": "Status alterado",
  "tournament.delete": "Torneio apagado",
  "tournament.add_players": "Jogadores inscritos",
  "tournament.remove_player": "Jogador removido",
  "tournament.withdraw": "Desistência",
  "tournament.set_pots": "Potes definidos",
  "tournament.link_subtournament": "Subtorneio ligado à regra",
  "user.create": "Usuário criado",
  "user.reset_password": "Senha redefinida",
  "user.set_role": "Papel alterado",
  "user.set_active": "Conta ativada/desativada",
};

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function scoreText(m: { p1_wins: number | null; p2_wins: number | null; status: string }): string {
  if (m.status !== "validated" || m.p1_wins === null || m.p2_wins === null) return "×";
  return `${m.p1_wins} × ${m.p2_wins}`;
}

/** Valor para <input type="datetime-local"> (horário local) a partir de um ISO. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Data sem hora ("2019-03-01" -> "01/03/2019"), sem o fuso deslocar o dia. */
export function fmtDay(d: string | null | undefined): string {
  if (!d) return "—";
  const [y, m, day] = d.slice(0, 10).split("-");
  return y && m && day ? `${day}/${m}/${y}` : d;
}

/** Período de um torneio do acervo. */
export function fmtPeriod(start: string | null, end: string | null): string {
  if (start && end && start !== end) return `${fmtDay(start)} a ${fmtDay(end)}`;
  return start || end ? fmtDay(start || end) : "data não informada";
}

export const tiebreakLabel: Record<string, string> = {
  confronto_direto: "Confronto direto", saldo: "Saldo", vitorias: "Vitórias", sorteio: "Sorteio",
};

export const battleFormat: Record<string, string> = { singles: "1v1 tradicional", doubles: "2v2" };
export const chatLabel: Record<string, string> = { open: "Chat aberto", private: "Partida privada" };
