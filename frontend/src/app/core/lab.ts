/** Tipi delle API del Laboratorio (vedi backend/app/api/lab.py). */
import { Competition, StandingRow, TeamRef } from './football';

export interface SeasonInfo {
  season: string;
  matches: number;
  finished: number;
  /** Ancora da giocare: se > 0 la stagione è in corso */
  pending: number;
  /** Annullate (es. squadre escluse) */
  cancelled: number;
}

export interface CompetitionSeasons {
  competition: Competition;
  seasons: SeasonInfo[];
}

export interface LeagueSummary {
  matches: number;
  home_win: number | null;
  draw: number | null;
  away_win: number | null;
  goals_per_match: number | null;
  home_goals: number | null;
  away_goals: number | null;
  over_2_5: number | null;
  both_scored: number | null;
  nil_nil: number | null;
  home_points_per_game: number | null;
  away_points_per_game: number | null;
}

export interface SeasonDetail {
  competition: Competition;
  season: string;
  matches: number;
  finished: number;
  pending: number;
  cancelled: number;
  summary: LeagueSummary;
  standings: StandingRow[];
}

export interface SeasonTrend {
  season: string;
  summary: LeagueSummary;
}

export interface TeamListItem {
  id: number;
  name: string;
  last_season: string | null;
  last_competition: string | null;
}

export interface TeamSeason {
  season: string;
  competition: Competition;
  rank: number;
  teams: number;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  points: number;
  complete: boolean;
}

export interface TeamHistory {
  team: TeamRef;
  seasons: TeamSeason[];
}

/** "2024/25" → "2024-25" per gli indirizzi */
export function seasonParam(season: string): string {
  return season.replace('/', '-');
}

// --- Cosa impara Archie (Fase 7, D117-D121) ---

export interface Est {
  mean: number;
  se: number | null;
  n: number;
}

export interface StrategyRow {
  strategy: { league: string; market: string; selection: string; band: [number, number]; moment: string; filter: string; name: string };
  tuning: Est | null;
  tuning_roi: Est | null;
  confirm: Est | null;
  confirm_roi: Est | null;
  candidate: boolean;
  passed: boolean;
}

export interface TimingGroup {
  group: string;
  matches: number;
  verdict: string;
  best: string | null;
  horizons: { label: string; clv: Est; vs_last: Est }[];
  occasions: { horizon: string; n: number; now: Est; gain: Est; still_value: number; play_now: boolean }[];
}

export interface CalibrationRow {
  group: string;
  market: string;
  matches: number;
  since: string | null;
  until: string | null;
  bins: { low: number; high: number; n: number; predicted: number; observed: number; se: number; off: boolean }[];
}

export interface Learning {
  computed_at: string;
  strategies: {
    tested: number;
    tuning_bets: number;
    confirm_bets: number;
    tuning_seasons: [string, string | null];
    confirm_seasons: [string, string | null];
    candidates: StrategyRow[];
    passed: StrategyRow[];
    closest: StrategyRow[];
  };
  timing: { matches: number; groups: TimingGroup[] };
  calibration: { matches_per_group: number; rows: CalibrationRow[] };
  value_map: { seasons: number; plays: number; clv: Est | null; rows: { league: string; month: number; count: number; per_season: number; clv: Est }[] };
}

export interface Twins {
  source: string;
  probabilities: Record<string, number>;
  p_over: number | null;
  n: number;
  observed: Record<string, number>;
  expected: Record<string, number>;
  over_observed: number | null;
  over_expected: number | null;
  avg_goals: number;
  top_scores: [string, number][];
  examples: { match_id: number; league: string; day: string; home: string | null; away: string | null; score: string }[];
}

export const LEAGUE_NAMES: Record<string, string> = {
  'ITA-A': 'Serie A', 'ITA-B': 'Serie B', 'ENG-1': 'Premier League', 'ENG-2': 'Championship', 'ESP-1': 'LaLiga',
  'ESP-2': 'Segunda', 'GER-1': 'Bundesliga', 'GER-2': '2. Bundesliga', 'FRA-1': 'Ligue 1', 'FRA-2': 'Ligue 2',
};
