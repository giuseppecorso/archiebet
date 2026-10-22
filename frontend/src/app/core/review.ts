/** Pagella settimanale di Archie (D132): vedi backend/app/forecast/review.py */

export interface FamilyScore {
  family: 'esito' | 'gol' | 'angoli' | 'cartellini';
  markets: number;
  favorite_expected: number;
  favorite_actual: number;
  log_loss: number | null;
  log_loss_closing: number | null;
}

export interface Tally {
  played: number;
  won: number;
  expected: number;
  profit: number;
  clv: number | null;
}

export type Variant = 'base' | 'impara';

export interface ReviewWeek {
  week: string;
  matches: number;
  families: FamilyScore[];
  multiples: Record<Variant, Record<string, Tally>>;
  corrections: string[];
  bench: string[];
}

export interface GroupTest {
  group: string;
  markets_tested: number;
  eval_weeks: number;
  gain: number | null;
  t: number | null;
  corrected: boolean;
}

export interface BenchTest {
  group: string;
  legs: number;
  gap: number | null;
  t: number | null;
  benched: boolean;
}

export interface Review {
  computed_at: string;
  weeks: ReviewWeek[];
  totals: Record<Variant, Record<string, Tally>>;
  state: {
    corrections: Record<string, { a: number; b: number }>;
    bench: string[];
    groups: GroupTest[];
    bench_tests: BenchTest[];
  };
}

export const REVIEW_PROFILES = ['molto tranquilla', 'tranquilla', 'equilibrata', 'coraggiosa', 'spericolata', 'caccia al clv'];

/** "2026-10-12" → "12–18 ott" */
export function weekLabel(monday: string): string {
  const start = new Date(`${monday}T12:00:00`);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  const month = (d: Date) => d.toLocaleDateString('it-IT', { month: 'short' }).replace('.', '');
  return start.getMonth() === end.getMonth()
    ? `${start.getDate()}–${end.getDate()} ${month(end)}`
    : `${start.getDate()} ${month(start)} – ${end.getDate()} ${month(end)}`;
}

/** Il gruppo "angoli · pinnacle" detto bene */
export function groupLabel(group: string): string {
  const [family, source] = group.split(' · ');
  const names: Record<string, string> = { esito: '1X2 e doppia chance', gol: 'Gol (Under/Over, Goal)', angoli: 'Angoli', cartellini: 'Cartellini' };
  const sources: Record<string, string> = { pinnacle: 'da Pinnacle', consenso: 'dal consenso italiano', betfair_ex: 'da Betfair', market_avg: 'dalla media' };
  return `${names[family] ?? family} ${sources[source] ?? source}`;
}
