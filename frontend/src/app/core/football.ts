/** Tipi delle API /api/matches e /api/competitions (vedi backend/app/api/football.py). */

export interface TeamRef {
  id: number;
  name: string;
}

export interface Competition {
  code: string;
  name: string;
  country: string;
  tier: number;
}

export type MatchStatus = 'scheduled' | 'finished' | 'awaiting_result';
export type Odds1x2 = Record<'1' | 'X' | '2', number>;

/** Partita in corso (D92): codice API-Football ("1H", "HT", "2H", "ET", "P"), minuto, punteggio di adesso */
export interface LiveState {
  status: string;
  minute: number | null;
  home_goals: number;
  away_goals: number;
}

export interface MatchCard {
  id: number;
  competition: Competition;
  season: string;
  kickoff_at: string;
  kickoff_has_time: boolean;
  status: MatchStatus;
  home: TeamRef;
  away: TeamRef;
  home_goals: number | null;
  away_goals: number | null;
  odds_1x2: Odds1x2 | null;
  live?: LiveState | null;
}

export interface CompetitionGroup {
  competition: Competition;
  matches: MatchCard[];
}

export type Outcome = 'V' | 'N' | 'P';

export interface FormEntry {
  outcome: Outcome;
  match_id: number;
  kickoff_at: string;
  opponent: string;
  venue: 'C' | 'T';
  score: string;
}

export interface TeamSummary {
  played: number;
  points_per_game: number | null;
  goals_for: number | null;
  goals_against: number | null;
  shots_for: number | null;
  shots_on_target_for: number | null;
  corners_for: number | null;
  xg_for: number | null;
  xg_against: number | null;
  clean_sheets: number | null;
  over_2_5: number | null;
  both_scored: number | null;
}

export interface SideStats {
  team: TeamRef;
  form: FormEntry[];
  season: TeamSummary;
  venue: TeamSummary;
}

export interface StandingRow {
  rank: number;
  team: TeamRef;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  points: number;
  form: Outcome[];
}

export interface OddsRow {
  bookmaker: string;
  label: string;
  market: '1X2' | 'OU2.5';
  opening: Record<string, number>;
  closing: Record<string, number>;
}

export interface MarketReference {
  /** Es. "Pinnacle · chiusura" */
  source: string;
  /** Probabilità senza margine */
  probabilities: Record<string, number>;
}

/** Previsione di Archie fatta prima del calcio d'inizio */
export interface Prediction {
  model_version: string;
  computed_at: string;
  /** Calcio d'inizio dell'ultimo risultato usato dal modello */
  data_until: string;
  /** Elo [casa, trasferta] */
  ratings: [number, number];
  expected_goals: [number, number];
  /** Mercato → esito → probabilità */
  markets: Record<string, Record<string, number>>;
  market: Record<string, MarketReference>;
}

export interface MatchDetail {
  match: MatchCard;
  stats_as_of: string;
  /** Partite già giocate del campionato senza risultato nei dati: statistiche incomplete */
  missing_results: number;
  home: SideStats;
  away: SideStats;
  head_to_head: MatchCard[];
  standings: StandingRow[];
  odds: OddsRow[];
  match_stats: Record<string, [number | null, number | null]> | null;
  prediction: Prediction | null;
}

export const OUTCOME_LABEL: Record<Outcome, string> = { V: 'vinta', N: 'pareggio', P: 'persa' };
