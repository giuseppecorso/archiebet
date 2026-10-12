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
