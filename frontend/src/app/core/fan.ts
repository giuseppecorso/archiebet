/** Tipi dell'API /api/fan (Archie tifoso, D101-D102: vedi backend/app/api/fan.py). */

export interface FanFact {
  team_id: number;
  kind: string;
  label: string;
  player: string | null;
  detail: string;
  published_at: string;
  url: string;
  source: 'tuttoc' | 'gnews' | string;
  /** Altre notizie sulla stessa cosa, più vecchie: raggruppate sotto questa */
  similar?: { detail: string; published_at: string; url: string; source: string }[];
}

export interface FanInsight {
  created_at: string;
  side: 'home' | 'away' | 'none';
  strength: 'lieve' | 'netta' | '';
  reason: string;
}

export interface FanTest {
  /** "Serie C" (D101) o "Serie A e B" (D105): conteggi separati */
  group: string;
  signals: number;
  target: number;
  /** Spostamento medio delle quote verso il lato indicato da Archie (0,01 = un punto percentuale) */
  mean_move: number | null;
  std_error: number | null;
}

export interface MatchFan {
  facts: FanFact[];
  insight: FanInsight | null;
  test: FanTest;
}

/** Fatti che pesano contro la squadra (rossi) o a favore (verdi); gli altri sono neutri */
const BAD = new Set(['assente', 'squalifica', 'allenatore_in_bilico', 'societa_in_crisi', 'penalizzazione', 'cessione', 'clima_negativo']);
const GOOD = new Set(['rientro', 'acquisto', 'clima_positivo']);

export function factTone(kind: string): 'bad' | 'good' | 'neutral' {
  return BAD.has(kind) ? 'bad' : GOOD.has(kind) ? 'good' : 'neutral';
}

export const SOURCE_LABELS: Record<string, string> = { tuttoc: 'TuttoC', gnews: 'Google News' };
