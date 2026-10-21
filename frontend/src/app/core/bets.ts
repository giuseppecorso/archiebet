/** Tipi delle API delle giocate (vedi backend/app/api/bets.py) ed etichette in italiano. */
import { MatchCard } from './football';

export type BetKind = 'real' | 'simulated';
export type BetStatus = 'open' | 'won' | 'lost' | 'void';
export type Market = '1X2' | 'DC' | 'OU2.5' | 'GG';

export interface Selection {
  id: number;
  match: MatchCard;
  market: Market;
  pick: string;
  odds: string;
  status: BetStatus;
  fair_closing_odds: string | null;
  clv: string | null;
  /** Probabilità che vinca adesso (termometro, D92); solo schedine aperte */
  probability?: number | null;
  /** Sfortuna o errore? (D113): solo a selezione chiusa */
  autopsy?: { verdict: string; probability: number | null; text: string } | null;
}

export interface Bet {
  id: number;
  kind: BetKind;
  stake: string;
  total_odds: string;
  potential_payout: string;
  bookmaker: string | null;
  note: string | null;
  status: BetStatus;
  payout: string | null;
  placed_at: string;
  settled_at: string | null;
  selections: Selection[];
  /** Termometro della speranza: probabilità di vincere adesso (solo aperte) */
  hope?: number | null;
  /** Almeno una partita della schedina è in corso */
  live?: boolean;
}

export interface BetCreated {
  bet: Bet;
  warnings: string[];
}

export interface BetSummary {
  bets: number;
  open: number;
  settled: number;
  won: number;
  staked: string;
  returned: string;
  profit: string;
  roi: number | null;
  win_rate: number | null;
  avg_clv: number | null;
  clv_count: number;
}

export interface SummaryOut {
  period: 'week' | '30d' | 'season' | 'all';
  real: BetSummary;
  simulated: BetSummary;
}

/** Rendimento di un gruppo di schedine chiuse (per numero di partite o bookmaker) */
export interface BetGroup {
  label: string;
  bets: number;
  won: number;
  staked: string;
  profit: string;
  roi: number | null;
}

/** Rendimento di un gruppo di selezioni chiuse (per mercato o campionato) */
export interface SelectionGroup {
  label: string;
  selections: number;
  won: number;
  hit_rate: number | null;
  avg_odds: number | null;
  flat_roi: number | null;
  avg_clv: number | null;
  clv_count: number;
}

export interface Habits {
  bets: number;
  avg_stake: string | null;
  avg_odds: number | null;
  multiple_share: number | null;
  avg_selections: number | null;
  top_market: string | null;
  top_bookmaker: string | null;
  top_teams: [string, number][];
}

export interface Breakdown {
  by_size: BetGroup[];
  by_bookmaker: BetGroup[];
  by_market: SelectionGroup[];
  by_competition: SelectionGroup[];
  habits: Habits;
}

export interface BudgetStatus {
  week_staked: string;
  week_budget: string | null;
  month_staked: string;
  month_budget: string | null;
  warnings: string[];
}

export interface UserSettings {
  weekly_budget: string | null;
  monthly_budget: string | null;
  favorite_team_id: number | null;
  bookmakers: string[];
  available_bookmakers: string[];
  favorite_team_name: string | null;
}

export interface Prefill {
  match: MatchCard;
  markets: Record<Market, string[]>;
  odds: Partial<Record<Market, Record<string, number>>>;
}

export const MARKET_LABEL: Record<Market, string> = {
  '1X2': 'Esito finale',
  DC: 'Doppia chance',
  'OU2.5': 'Under / Over 2.5',
  GG: 'Goal / NoGoal',
};

/** "1" → "1 · Inter", "over" → "Over 2.5", "yes" → "Goal"… */
export function pickLabel(market: Market, pick: string, match?: Pick<MatchCard, 'home' | 'away'>): string {
  const team = (side: 'home' | 'away') => (match ? ` · ${match[side].name}` : '');
  const labels: Record<string, string> = {
    '1X2:1': `1${team('home')}`,
    '1X2:X': 'X · Pareggio',
    '1X2:2': `2${team('away')}`,
    'DC:1X': '1X',
    'DC:X2': 'X2',
    'DC:12': '12',
    'OU2.5:over': 'Over 2.5',
    'OU2.5:under': 'Under 2.5',
    'GG:yes': 'Goal',
    'GG:no': 'NoGoal',
  };
  return labels[`${market}:${pick}`] ?? pick;
}

export const STATUS_LABEL: Record<BetStatus, string> = { open: 'In corso', won: 'Vinta', lost: 'Persa', void: 'Rimborsata' };
export const KIND_LABEL: Record<BetKind, string> = { real: 'Reale', simulated: 'Simulata' };

/**
 * Arrotondamento "per eccesso dal 5" come il backend (ROUND_HALF_UP).
 * Il piccolo correttivo evita l'errore della virgola mobile: 49,445 × 100 = 4944,4999… e non 4944,5.
 */
export function roundHalfUp(value: number, digits: number): number {
  const factor = 10 ** digits;
  return (Math.sign(value) * Math.round(Math.abs(value) * factor + 1e-7)) / factor;
}

/** Quota totale e vincita potenziale per l'anteprima, con le stesse regole del backend (che salva il valore ufficiale) */
export function preview(odds: number[], stake: number): { total: number; payout: number } {
  const total = roundHalfUp(odds.reduce((p, o) => p * o, 1), 4);
  return { total, payout: roundHalfUp(total * stake, 2) };
}

/** Euro con segno e virgola italiana: 12.5 → "+12,50 €" */
export function euro(value: string | number | null | undefined, signed = false): string {
  if (value == null) return '–';
  const n = Number(value);
  const text = Math.abs(n).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sign = signed ? (n > 0 ? '+' : n < 0 ? '−' : '') : n < 0 ? '−' : '';
  return `${sign}${text} €`;
}

/** Io contro Archie (vedi backend/app/betting/versus.py) */
export interface VersusGroup {
  n: number;
  won: number;
  expected_wins: number;
  roi: number;
  avg_value: number;
}

export interface Versus {
  judged: number;
  without_archie: number;
  /** Vinte − attese da Archie */
  skill: number | null;
  skill_std_error: number | null;
  agreed: VersusGroup | null;
  disagreed: VersusGroup | null;
}
