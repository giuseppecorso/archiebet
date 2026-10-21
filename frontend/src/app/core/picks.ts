import { MatchCard } from './football';

/** Tipi dell'API /api/picks (vedi backend/app/api/picks.py, D67). */
/** "sopra la media": la quota batte la media dei bookmaker italiani (Serie C, niente Pinnacle), un'indicazione (D96) */
export type Verdict = 'valore' | 'sopra la media' | 'nella norma' | 'paga poco';

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

/** I due pronostici della pagina partita (D107): il più sicuro (più probabile) e il più spinto (quota 2-4) */
export interface Suggestion {
  kind: 'sicuro' | 'spinto';
  market: MarketPick['market'];
  selection: string;
  probability: number;
  source: string;
  offer: Offer;
  /** La quota batte la probabilità giusta con la regola delle Occasioni (D72) */
  has_value: boolean;
}

export interface MatchPicks {
  suggestions: Suggestion[];
  markets: MarketPick[];
}

/** Analisi scritta da Archie (D107): spiega i numeri calcolati dal codice e le notizie */
export interface MatchAnalysis {
  created_at: string;
  model: string;
  summary: string;
  points: string[];
  verdict: string;
}

/** Classe CSS dell'etichetta di una quota */
export function verdictClass(v: Verdict): string {
  return v === 'valore' ? 'valore' : v === 'sopra la media' ? 'archie' : v === 'paga poco' ? 'poco' : 'norma';
}

/** Numeri attesi di una partita (D109): tiri, angoli, cartellini con le quote giuste di Archie */
export interface CountLine {
  side: 'totale' | 'casa' | 'ospite';
  line: number;
  p_over: number;
  fair_over: number;
  fair_under: number;
  /** bookmaker → { over, under }, dove quotato */
  offers: Record<string, { over?: number; under?: number }>;
}

export interface MatchNumbers {
  stat: 'shots' | 'corners' | 'cards';
  label: string;
  home: number;
  away: number;
  lines: CountLine[];
}
