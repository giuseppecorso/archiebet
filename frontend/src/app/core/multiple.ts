import { MatchCard } from './football';

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
  horizon: 'today' | 'week';
  multiples: Multiple[];
  missing: string[];
}
