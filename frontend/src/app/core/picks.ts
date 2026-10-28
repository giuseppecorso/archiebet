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
  market: string;
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

/** Tiri attesi di un giocatore (D110-D111): probabilità e quote giuste di Over 0,5 / 1,5 tiri e Over 0,5 in porta */
export interface PlayerShots {
  side: 'casa' | 'ospite';
  name: string;
  position: string;
  exp_shots: number;
  exp_on: number;
  p_shot: number;
  p_two: number;
  p_on: number;
  /** Assente o squalificato secondo le notizie (Archie tifoso) */
  absent: string | null;
}

/** Formazioni previste (D123) o ufficiali */
export interface LineupPlayer {
  name: string;
  position: string;
  p_start: number | null;
  absent: string | null;
}

export interface TeamLineup {
  side: 'casa' | 'ospite';
  official: boolean;
  eleven: LineupPlayer[];
  doubtful: LineupPlayer[];
  out: LineupPlayer[];
  based_on: number;
}

/** Un consiglio da giocare tra le linee di tiri, angoli o cartellini: l'esito con probabilità più vicina al 70%,
 * tra il 60% e l'85% (sotto è un azzardo, sopra la quota non vale la pena). Null se nessuna linea è in quella fascia. */
export function countTip(lines: CountLine[]): { pick: 'Over' | 'Under'; line: number; p: number; fair: number } | null {
  const options = lines
    .filter((l) => l.side === 'totale')
    .flatMap((l) => [
      { pick: 'Over' as const, line: l.line, p: l.p_over, fair: l.fair_over },
      { pick: 'Under' as const, line: l.line, p: 1 - l.p_over, fair: l.fair_under },
    ])
    .filter((o) => o.p >= 0.6 && o.p <= 0.85);
  if (!options.length) return null;
  return options.reduce((a, b) => (Math.abs(b.p - 0.7) < Math.abs(a.p - 0.7) ? b : a));
}

/** I due giocatori (non assenti) più probabili a fare almeno un tiro in porta */
export function playerTips(players: PlayerShots[]): PlayerShots[] {
  return players.filter((p) => !p.absent).sort((a, b) => b.p_on - a.p_on).slice(0, 2);
}
