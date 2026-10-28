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
  /** Quota migliore dei bookmaker ("Altri bookmakers"), se quotano il mercato */
  prices: Record<string, number>;
  /** Quota media dei bookmaker che quotano il pronostico */
  avg_price?: number | null;
}

export interface StudyMultiple {
  level: string;
  legs: StudyLeg[];
  win_probability: number;
  totals: Record<string, number>;
  more: boolean;
  /** Quota totale: la migliore di ogni gamba, o quella giusta dello studio dove il bookmaker non quota */
  total_odds: number;
  /** Con la quota obiettivo: Archie ci è arrivato? */
  target_reached: boolean;
}
