/** Formattazione per lo schermo. Le date arrivano in UTC e si mostrano sempre in ora italiana. */

const TZ = 'Europe/Rome';

const timeFmt = new Intl.DateTimeFormat('it-IT', { timeZone: TZ, hour: '2-digit', minute: '2-digit' });
const dayKeyFmt = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' });
const weekdayFmt = new Intl.DateTimeFormat('it-IT', { timeZone: TZ, weekday: 'short' });
const shortDateFmt = new Intl.DateTimeFormat('it-IT', { timeZone: TZ, day: '2-digit', month: '2-digit' });
const longDateFmt = new Intl.DateTimeFormat('it-IT', { timeZone: TZ, weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

/** "2026-10-11" del giorno in Italia: serve a confrontare i giorni senza sorprese di fuso. */
function dayKey(date: Date): string {
  return dayKeyFmt.format(date);
}

/** Ora del calcio d'inizio, es. "20:45" (vuota se la fonte non ha l'orario). */
export function kickoffTime(iso: string, hasTime = true): string {
  return hasTime ? timeFmt.format(new Date(iso)) : '--:--';
}

/** Etichetta corta del giorno: OGGI, DOMANI, IERI, oppure "SAB 10/10". */
export function dayLabel(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const day = dayKey(date);
  const offsets: Record<string, string> = { '0': 'OGGI', '1': 'DOMANI', '-1': 'IERI' };
  for (const [offset, label] of Object.entries(offsets)) {
    if (day === dayKey(new Date(now.getTime() + Number(offset) * 86_400_000))) {
      return label;
    }
  }
  return `${weekdayFmt.format(date).replace('.', '').toUpperCase()} ${shortDateFmt.format(date)}`;
}

export function longDate(iso: string): string {
  return longDateFmt.format(new Date(iso));
}

/** Quota con due decimali, es. 1.9 → "1.90". */
export function odds(value: number | null | undefined): string {
  return value == null ? '–' : value.toFixed(2);
}

/** Numero con al massimo due decimali, separatore italiano: 1.5 → "1,5". */
export function num(value: number | null | undefined, digits = 2): string {
  return value == null ? '–' : value.toLocaleString('it-IT', { maximumFractionDigits: digits });
}

/** Quota 0-1 → percentuale intera, es. 0.375 → "38%". */
export function pct(value: number | null | undefined): string {
  return value == null ? '–' : `${Math.round(value * 100)}%`;
}
