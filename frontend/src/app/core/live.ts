import { LiveState } from './football';

/** "67'", "Intervallo", "Supplementari", "Rigori": cosa scrivere al posto dell'orario mentre si gioca */
export function liveLabel(l: LiveState): string {
  if (l.status === 'HT') return 'Intervallo';
  if (l.status === 'ET' || l.status === 'BT') return 'Supplementari';
  if (l.status === 'P') return 'Rigori';
  if (l.status === 'SUSP' || l.status === 'INT') return 'Sospesa';
  return l.minute != null ? `${l.minute}'` : 'In corso';
}

/** Ogni quanto ricaricare i dati mentre si segue una partita (il backend li aggiorna ogni minuto) */
export const LIVE_REFRESH_MS = 30_000;

/** Versione corta per la colonna dell'orario: "67'", "INT", "SUPPL", "RIG" */
export function liveShort(l: LiveState): string {
  const short: Record<string, string> = { HT: 'INT', ET: 'SUPPL', BT: 'SUPPL', P: 'RIG', SUSP: 'SOSP', INT: 'SOSP' };
  return short[l.status] ?? (l.minute != null ? `${l.minute}'` : 'LIVE');
}
