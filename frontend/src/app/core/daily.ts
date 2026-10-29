/** Bacheca Daily (D153): vedi backend/app/api/daily.py */

export interface DailyLeg {
  match_id: number;
  kickoff_at: string;
  competition: string;
  home: string;
  away: string;
  market: string;
  selection: string;
  /** Il pronostico detto a parole */
  event: string;
  /** Probabilità di Archie (per il CLV: quella giusta di Pinnacle) */
  p: number;
  /** Quota al momento della pubblicazione */
  price: number;
  status: 'open' | 'won' | 'lost' | 'void';
  /** Risultato finale, quando la partita è finita */
  score?: string | null;
}

export interface DailySlip {
  id: number;
  kind: string;
  title: string;
  period: string;
  published_at: string;
  /** true = pronostici da giocare uno per uno (la schedina del CLV) */
  singles: boolean;
  /** Sistema "k su n" (D157): il sistemone */
  system?: number | null;
  legs: DailyLeg[];
  total_odds: number;
  win_probability: number;
  status: 'open' | 'won' | 'lost' | 'void' | 'done';
}

export interface DailyKindStats {
  kind: string;
  title: string;
  published: number;
  closed: number;
  won: number;
  /** Quante dovevano uscire secondo le probabilità di Archie */
  expected: number;
  legs_won: number;
  legs_closed: number;
  /** Guadagno con 1 € a schedina */
  profit: number;
}

export interface DailyOut {
  board: DailySlip[];
  today: { legs_won: number; legs_closed: number; legs_total: number };
  stats: DailyKindStats[];
  history: DailySlip[];
}
