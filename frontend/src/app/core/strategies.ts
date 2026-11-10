/** Scheda Strategie (D189, D194): sistemi costruiti sui pronostici di Archie e strategie famose provate sul passato. */
import { roundHalfUp, systemPreview } from './bets';

export interface StrategyEstimate {
  mean: number;
  se: number | null;
  t: number;
}

export interface StrategyPart {
  n: number;
  won: number;
  hit_rate: number | null;
  avg_price: number | null;
  roi: StrategyEstimate | null;
  clv: StrategyEstimate | null;
}

export interface MarketStrategy {
  key: string;
  name: string;
  how: string;
  price: string;
  passed: boolean;
  beats_close: boolean;
  tuning: StrategyPart;
  confirm: StrategyPart;
}

export interface StrategiesOut {
  generated_at: string | null;
  tuning?: { from: string; to: string; matches: number };
  confirm?: { from: string; to: string; matches: number };
  strategies: MarketStrategy[];
}

/** Probabilità di indovinarne almeno k su n, con partite indipendenti (programmazione dinamica). */
export function atLeast(probabilities: number[], k: number): number {
  let dist = [1]; // dist[j] = probabilità di averne indovinate esattamente j
  for (const p of probabilities) {
    const next = new Array(dist.length + 1).fill(0);
    dist.forEach((q, j) => {
      next[j] += q * (1 - p);
      next[j + 1] += q * p;
    });
    dist = next;
  }
  return dist.slice(k).reduce((a, b) => a + b, 0);
}

export interface SystemRow {
  /** multiple da k partite; k = n è la multipla secca */
  k: number;
  combos: number;
  /** puntata per ogni multipla */
  perBet: number;
  min: number;
  max: number;
  /** probabilità di vincere qualcosa (almeno k giuste) */
  pWin: number;
}

/** Tutti i sistemi da "2 su n" alla multipla secca, con la stessa puntata totale. */
export function systemRows(legs: { p: number; odds: number }[], stake: number): SystemRow[] {
  const odds = legs.map((l) => l.odds);
  const ps = legs.map((l) => l.p);
  const rows: SystemRow[] = [];
  for (let k = Math.min(2, legs.length); k <= legs.length; k++) {
    const { combos, min, max } = systemPreview(odds, k, stake);
    rows.push({ k, combos, perBet: roundHalfUp(stake / combos, 2), min, max, pWin: atLeast(ps, k) });
  }
  return rows;
}
