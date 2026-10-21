import { MatchCard } from './football';

/** Tipi dell'API /api/picks (vedi backend/app/api/picks.py, D67). */
/** "sopra Archie": la quota batte solo il modello di Archie (es. Serie C, niente Pinnacle), non un valore dimostrato (D88) */
export type Verdict = 'valore' | 'sopra Archie' | 'sopra la media' | 'nella norma' | 'paga poco';

export interface Offer {
  bookmaker: string;
  price: number;
  value: number;
  verdict: Verdict;
}

export interface MarketPick {
  market: '1X2' | 'DC' | 'OU2.5' | 'GG';
  /** Da dove viene la probabilità: Pinnacle, Betfair Exchange, Media mercato o Modello di Archie */
  source: string;
  from_model: boolean;
  probabilities: Record<string, number>;
  offers: Record<string, Offer[]>;
}

export interface Pick {
  match: MatchCard;
  favorite: string | null;
  favorite_probability: number | null;
  markets: MarketPick[];
  signals: number;
}

export interface PicksOut {
  bookmakers: string[];
  picks: Pick[];
}
