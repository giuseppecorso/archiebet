/** Multipla studiata da Archie (D137): vedi backend/app/api/study.py */
import { MatchCard } from './football';

export interface StudyLeg {
  match: MatchCard;
  market: string;
  selection: string;
  market_label: string;
  /** Il pronostico detto a parole, es. "Brescia segna nel primo tempo" */
  event: string;
  level: string;
  /** Probabilità dello studio (modello dei gol e fatti del campo) */
  p_archie: number;
  p_model: number;
  /** [volte in casa, partite in casa, volte in trasferta, partite in trasferta] */
  evidence: number[];
  reasons: string[];
  /** Quote di Sisal ed Eurobet, se il bookmaker quota il mercato */
  prices: Record<string, number>;
}

export interface StudyMultiple {
  level: string;
  legs: StudyLeg[];
  win_probability: number;
  totals: Record<string, number>;
  more: boolean;
}
