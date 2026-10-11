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
}

export const OUTCOME_LABEL: Record<Outcome, string> = { V: 'vinta', N: 'pareggio', P: 'persa' };
