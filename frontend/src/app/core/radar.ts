import { Competition, TeamRef } from './football';

/** Segnale del radar: quota italiana sopra la quota giusta di Pinnacle (D57, D63) */
export interface RadarSignal {
  match_id: number;
  competition: Competition;
  kickoff_at: string;
  home: TeamRef;
  away: TeamRef;
  /** Principali: '1X2', 'OU2.5', 'GG'; angoli e cartellini (D94): 'COR9.5', 'CORH4.5', 'CRDA1.5', ... */
  market: string;
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
  secondary?: boolean;
}

/** Occasione di adesso su un bookmaker dell'utente (D74) */
export interface Occasion {
  match_id: number;
  competition: Competition;
  kickoff_at: string;
  home: TeamRef;
  away: TeamRef;
  market: string;
  selection: string;
  bookmaker: string;
  price: number;
  fair_probability: number;
  fair_source: string;
  value: number;
  /** Soglia per quella quota (D72) */
  required_value: number;
  suspicious: boolean;
  /** Angoli o cartellini: "in prova", simulazione separata (D94) */
  secondary?: boolean;
  /** Strategia trovata da Archie e confermata sul passato che gioca questo esito (D118) */
  strategy?: string | null;
  /** Probabilità dello studio di Archie per l'esito, se la partita è studiata (D152) */
  p_study?: number | null;
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
  /** Simulazione di angoli e cartellini (D94) */
  live_secondary?: RadarLive;
}

/** "COR9.5" → "Angoli Over 9.5"; "CRDH1.5" → "Cartellini Torino Under 1.5" */
export function secondaryLabel(market: string, selection: string, home: string, away: string): string | null {
  const m = /^(COR|CRD)([HA]?)(\d+\.5)$/.exec(market);
  if (!m) return null;
  const family = m[1] === 'COR' ? 'Angoli' : 'Cartellini';
  const side = m[2] === 'H' ? ` ${home}` : m[2] === 'A' ? ` ${away}` : '';
  return `${family}${side} ${selection === 'over' ? 'Over' : 'Under'} ${m[3]}`;
}
