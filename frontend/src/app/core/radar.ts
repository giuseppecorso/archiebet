import { Competition, TeamRef } from './football';

/** Segnale del radar: quota italiana sopra la quota giusta di Pinnacle (D57, D63) */
export interface RadarSignal {
  match_id: number;
  competition: Competition;
  kickoff_at: string;
  home: TeamRef;
  away: TeamRef;
  market: '1X2' | 'OU2.5' | 'GG';
  selection: string;
  /** Prima rilevazione = giocata simulata: quota e valore restano questi */
  detected_at: string;
  bookmaker: string;
  price: number;
  fair_probability: number;
  fair_source: string;
  value: number;
  suspicious: boolean;
  /** Quote di adesso (null = quota sparita) */
  latest_bookmaker: string | null;
  latest_price: number | null;
  latest_value: number | null;
  latest_is_occasion: boolean;
  clv: number | null;
  won: boolean | null;
}

/** Occasione di adesso su un bookmaker di Giuse (D74) */
export interface Occasion {
  match_id: number;
  competition: Competition;
  kickoff_at: string;
  home: TeamRef;
  away: TeamRef;
  market: '1X2' | 'OU2.5' | 'GG';
  selection: string;
  bookmaker: string;
  price: number;
  fair_probability: number;
  fair_source: string;
  value: number;
  /** Soglia per quella quota (D72) */
  required_value: number;
  suspicious: boolean;
}

export interface RadarLive {
  n: number;
  target: number;
  mean_clv: number | null;
  clv_std_error: number | null;
  share_positive: number | null;
  roi: number | null;
  verdict: 'in prova' | 'superato' | 'non superato';
}

export interface RadarOut {
  /** Valore minimo a quota 2: la soglia cresce con la quota (D72) */
  threshold: number;
  max_price: number;
  playable: string[];
  simulation_bookmakers: string[];
  upcoming: Occasion[];
  recent: RadarSignal[];
  live: RadarLive;
}
