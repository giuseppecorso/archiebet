import { MatchCard } from './football';

/** Periodo della multipla (D83): giorni italiani, al massimo 7 giorni avanti */
export type Horizon = 'today' | 'tomorrow' | '2days' | '3days' | 'week' | 'range';

/** Tipi dell'API /api/picks/multiple (vedi backend/app/api/picks.py, D68). */
export interface MultipleLeg {
  match: MatchCard;
  market: string;
  selection: string;
  probability: number;
  price: number;
  value: number;
}

export interface Multiple {
  bookmaker: string;
  legs: MultipleLeg[];
  /** true = ogni gamba con valore ≥ 0; false = quote "nella norma" */
  with_value: boolean;
  price: number;
  win_probability: number;
  one_in: number;
  alive_before_last: number;
  expected_value: number;
}

export interface MultiplesOut {
  horizon: Horizon;
  multiples: Multiple[];
  missing: string[];
}
