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
  /** Da dove viene la probabilità: "consenso" = media dei bookmaker italiani (Serie C, D130) */
  source?: string;
}

export interface Multiple {
  bookmaker: string;
  legs: MultipleLeg[];
  /** true = ogni gamba con valore ≥ 0; false = quote "nella norma" */
  with_value: boolean;
  /** "valore" | "nella norma" | "paga poco" (D130) */
  quality?: string;
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
