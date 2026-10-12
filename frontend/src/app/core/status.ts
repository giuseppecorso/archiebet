import { Competition } from './football';

/** Stato dei dati (GET /api/status): quanto sono freschi e se un aggiornamento è in corso */
export interface SourceStatus {
  source: string;
  label: string;
  configured: boolean;
  last_ok_at: string | null;
  last_run_at: string | null;
  last_run_ok: boolean | null;
  message: string | null;
}

export interface CompetitionFreshness {
  competition: Competition;
  last_result_at: string | null;
  /** Partite già giocate di cui non abbiamo ancora il risultato */
  awaiting_results: number;
  next_match_at: string | null;
}

export interface DataStatus {
  now: string;
  syncing: boolean;
  sources: SourceStatus[];
  competitions: CompetitionFreshness[];
  upcoming: number;
  upcoming_with_prediction: number;
}
