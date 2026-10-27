/** Tipi delle API delle giocate (vedi backend/app/api/bets.py) ed etichette in italiano. */
import { MatchCard } from './football';

export type BetKind = 'real' | 'simulated';
export type BetStatus = 'open' | 'won' | 'lost' | 'void';
/** 1X2, DC, GG, Under/Over dei gol ('OU2.5') e, dal D131, angoli e cartellini ('COR9.5', 'CORH4.5', 'CRDA1.5'…) */
export type Market = string;

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

const SECONDARY = /^(COR|CRD)([HA]?)(\d+\.5)$/;
const FAMILY: Record<string, string> = { COR: 'angoli', CRD: 'cartellini' };

/** Angoli e cartellini: famiglia, lato ('' = totale, H = casa, A = ospite) e linea; null per gli altri mercati */
export function parseSecondary(market: string): { family: string; side: '' | 'H' | 'A'; line: string } | null {
  const m = SECONDARY.exec(market);
  return m ? { family: FAMILY[m[1]], side: m[2] as '' | 'H' | 'A', line: m[3] } : null;
}

const TEAM_GOALS = /^TG([HA])(\d\.5)$/;

/** Gol di una sola squadra (D135): "TGH1.5" → { side: 'H', line: '1.5' } */
export function parseTeamGoals(market: string): { side: 'H' | 'A'; line: string } | null {
  const m = TEAM_GOALS.exec(market);
  return m ? { side: m[1] as 'H' | 'A', line: m[2] } : null;
}

/** Famiglia di mercati per i filtri: esito, gol, gol squadra, angoli, cartellini */
export function marketFamily(market: string): 'esito' | 'gol' | 'gol squadra' | 'angoli' | 'cartellini' {
  const sec = parseSecondary(market);
  if (sec) return sec.family as 'angoli' | 'cartellini';
  if (parseTeamGoals(market)) return 'gol squadra';
  return market === '1X2' || market === 'DC' || market === 'DNB' ? 'esito' : 'gol';
}

const BASE_LABEL: Record<string, string> = { '1X2': 'Esito finale', DC: 'Doppia chance', DNB: 'Draw No Bet (pareggio rimborsato)', GG: 'Goal / NoGoal' };

/** "OU2.5" → "Under / Over 2.5", "CORH4.5" → "Angoli Inter U/O 4.5" (con la partita) o "Angoli casa U/O 4.5" */
export function marketLabel(market: Market, match?: Pick<MatchCard, 'home' | 'away'>): string {
  if (market.startsWith('1T_') || market.startsWith('2T_')) return `${marketLabel(market.slice(3), match)} · ${market[0]}° tempo`;
  if (market.startsWith('MG')) return `Multigol ${market.slice(2)}`;
  if (market.startsWith('CB_')) {
    const [, res, goals] = market.split('_');
    return `Combo ${res} + ${goals[0] === 'O' ? 'Over' : 'Under'} ${goals.slice(1)}`;
  }
  if (market.startsWith('OU')) return `Under / Over ${market.slice(2)}`;
  const team = parseTeamGoals(market);
  if (team) {
    const who = match ? (team.side === 'H' ? match.home.name : match.away.name) : team.side === 'H' ? 'casa' : 'ospite';
    return `Gol ${who} U/O ${team.line}`;
  }
  const sec = parseSecondary(market);
  if (sec) {
    const who = sec.side === '' ? 'totali' : match ? (sec.side === 'H' ? match.home.name : match.away.name) : sec.side === 'H' ? 'casa' : 'ospite';
    return `${sec.family === 'angoli' ? 'Angoli' : 'Cartellini'} ${who} U/O ${sec.line}`;
  }
  return BASE_LABEL[market] ?? market;
}

/** Esiti di un mercato, nell'ordine in cui si mostrano */
export function marketSelections(market: Market): string[] {
  if (market === '1X2') return ['1', 'X', '2'];
  if (market === 'DC') return ['1X', 'X2', '12'];
  if (market === 'GG') return ['yes', 'no'];
  if (market === 'DNB') return ['1', '2'];
  if (market.startsWith('MG') || market.startsWith('CB_')) return ['yes'];
  return ['over', 'under'];
}

/** "1" → "1 · Inter", "over" → "Over 2.5", "yes" → "Goal", angoli → "Over 9.5 angoli"… */
export function pickLabel(market: Market, pick: string, match?: Pick<MatchCard, 'home' | 'away'>): string {
  const team = (side: 'home' | 'away') => (match ? ` · ${match[side].name}` : '');
  const ou = pick === 'over' ? 'Over' : 'Under';
  if (market.startsWith('1T_') || market.startsWith('2T_')) return `${pickLabel(market.slice(3), pick, match)} ${market[0]}° tempo`;
  if (market.startsWith('MG') || market.startsWith('CB_')) return marketLabel(market);
  if (market.startsWith('OU')) return `${ou} ${market.slice(2)}`;
  const tg = parseTeamGoals(market);
  if (tg) return `${ou} ${tg.line} gol${tg.side === 'H' ? team('home') : team('away')}`;
  const sec = parseSecondary(market);
  if (sec) {
    const who = sec.side === '' ? '' : sec.side === 'H' ? team('home') : team('away');
    return `${ou} ${sec.line} ${sec.family}${who}`;
  }
  const labels: Record<string, string> = {
    '1X2:1': `1${team('home')}`,
    '1X2:X': 'X · Pareggio',
    '1X2:2': `2${team('away')}`,
    'DC:1X': '1X',
    'DC:X2': 'X2',
    'DC:12': '12',
    'DNB:1': `1 DNB${team('home')}`,
    'DNB:2': `2 DNB${team('away')}`,
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

/** Una giocata aperta dell'utente su una partita, con come sta andando adesso (D155) */
export interface MyPick {
  match_id: number;
  bet_id: number;
  legs: number;
  market: string;
  pick: string;
  state: 'waiting' | 'winning' | 'losing' | 'won' | 'lost' | 'void' | 'unknown';
  probability: number | null;
}
