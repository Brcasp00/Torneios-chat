// Cliente da API + tipos das respostas do back-end.
export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "http://localhost:8000";

const TOKEN_KEY = "torneios.token";

export const tokenStore = {
  get: () => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set: (t: string | null) => {
    try {
      if (t) localStorage.setItem(TOKEN_KEY, t);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* armazenamento indisponível: a sessão vale só até recarregar */
    }
  },
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string; loc?: unknown[] }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg ?? ""}`).join("; ");
  }
  return `Erro ${status}`;
}

export async function api<T = unknown>(path: string, opts: { method?: string; body?: unknown; params?: Record<string, unknown> } = {}): Promise<T> {
  const url = new URL(API_URL + path);
  for (const [k, v] of Object.entries(opts.params ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(url, { method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"), headers, body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined });
  } catch {
    throw new ApiError(0, "Não foi possível falar com o servidor. Se ele estava dormindo (plano gratuito), tente de novo em alguns segundos.");
  }
  if (res.status === 204) return undefined as T;
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* sem corpo JSON */
  }
  if (!res.ok) throw new ApiError(res.status, errorMessage(body, res.status));
  return body as T;
}

// ---------- tipos ----------
export type Role = "admin" | "organizer" | "player";
export interface User { id: number; name: string; role: Role; is_active: boolean; created_at: string; must_change_password?: boolean }
export interface Token { access_token: string; user: User }
export interface PlayerRef { id: number; name: string }

export interface Stage { id: number; position: number; name: string; type: "round" | "league" | "groups" | "knockout" | "playoff"; config: Record<string, unknown> | null; status: "pending" | "running" | "finished" }
export interface Rule { id: number; from_stage_id: number; source: string; pos_from: number; pos_to: number; target: string; to_stage_id: number | null; to_slot_from: number | null; config: Record<string, unknown> | null }
export interface TPlayer { user_id: number; name: string; seed: number | null; group_label: string | null; pot: number | null; status: "active" | "eliminated" | "withdrawn" }
export interface TournamentSummary { id: number; name: string; template: string; max_players: number; status: string; parent_id: number | null; created_at: string; players_count: number }
export interface RepechageInfo { rule_id: number; stage_id: number; subtournament_id: number | null; user_ids: number[] }
export interface TournamentDetail extends TournamentSummary {
  battle_rules: Record<string, unknown> | null;
  rules_text: string | null;
  config: Record<string, unknown> | null;
  created_by: number | null;
  stages: Stage[];
  rules: Rule[];
  players: TPlayer[];
  subtournaments: TournamentSummary[];
  repechage: RepechageInfo[];
  parent: TournamentSummary | null;
  can_manage: boolean;
}

export interface Match {
  id: number; tournament_id: number; stage_id: number; round: number; slot: number | null; group_label: string | null; leg: number; best_of: number;
  status: "scheduled" | "reported" | "validated" | "void";
  player1: PlayerRef | null; player2: PlayerRef | null;
  p1_wins: number | null; p2_wins: number | null; p1_remaining: number | null; p2_remaining: number | null;
  winner_id: number | null; is_draw: boolean; is_walkover: boolean; validated_at: string | null; has_pending_report: boolean;
  postponed: boolean; postponed_reason: string | null;
  deadline: string | null; overdue: boolean; auto_result: boolean; deadline_waived: boolean;
}
export interface Report { id: number; reported_by: number | null; p1_wins: number; p2_wins: number; p1_remaining: number; p2_remaining: number; replay_urls: string[] | null; notes: string | null; status: string; created_at: string; reviewed_by: number | null; reviewed_at: string | null; review_note: string | null }
export interface MatchDetail extends Match { tournament_name: string; tournament_status: string; stage_name: string; battle_rules: Record<string, unknown> | null; reports: Report[]; can_report: boolean; can_manage: boolean }
export interface TimelineEvent { at: string; kind: string; actor_id: number | null; actor_name: string | null; action: string; data: Record<string, unknown> | null }

export interface StandingRow { position: number; user_id: number; name: string; withdrawn: boolean; played: number; wins: number; draws: number; losses: number; points: number; saldo: number }
export interface StageStandings { stage_id: number; stage_name: string; stage_type: string; rows: StandingRow[]; groups: { label: string; rows: StandingRow[] }[] }
export interface BracketStage { stage_id: number; stage_name: string; status: string; rounds: { round: number; name: string; matches: Match[] }[]; third_place: Match | null; champion: PlayerRef | null }

export interface RoundHistory { snapshot_id: number; tournament_id: number; stage_id: number; stage_name: string; round: number; created_at: string; reopened: boolean; postponed: PostponedEntry[]; played_postponed: PostponedEntry[]; data: SnapshotData }
export interface PostponedEntry { match_id: number; round: number; group_label: string | null; player1: PlayerRef | null; player2: PlayerRef | null; reason: string | null; original_round?: number }
export interface StageHistory { snapshot_id: number; tournament_id: number; tournament_name: string; stage_id: number; stage_name: string; stage_type: string; created_at: string; versions: number; data: SnapshotData }
export interface SnapshotData {
  rows?: StandingRow[];
  groups?: Record<string, StandingRow[]>;
  matches?: { id: number; round: number; slot: number | null; group_label: string | null; player1_id: number | null; player2_id: number | null; winner_id: number | null; status: string; p1_wins: number | null; p2_wins: number | null }[];
  players?: Record<string, string>;
  ranking?: { position: number; user_id: number; name: string }[];
  [k: string]: unknown;
}

export interface DrawRound { round: number; matches: { player1: PlayerRef; player2: PlayerRef; leg: number; group_label: string | null }[] }
export interface DrawOut { seed: number; mode: string; rounds: DrawRound[]; arrangement: unknown }
export interface DrawRecord { seed: number; mode: string; drawn_at: string | null; pots: Record<string, number>; players: PlayerRef[] }

export interface AuditItem { id: number; created_at: string; actor_id: number | null; actor_name: string | null; action: string; entity: string; entity_id: number | null; data: Record<string, unknown> | null }
