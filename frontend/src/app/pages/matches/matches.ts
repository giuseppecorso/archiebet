import { httpResource } from '@angular/common/http';
import { Component, computed, effect, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Competition, CompetitionGroup } from '../../core/football';
import { LeagueLogo } from '../../shared/crest';
import { MatchRow } from '../../shared/match-row';

const STORAGE_KEY = 'archiebet.matches.competition';
const DAYS_BACK = 3;
const DAYS_AHEAD = 7;

/** Giorno locale AAAA-MM-GG spostato di `offset` giorni da oggi */
export function isoDay(offset = 0, now: Date = new Date()): string {
  const d = new Date(now);
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** "Oggi", "Domani", "Ieri" oppure "sab 25/10" */
export function dayName(offset: number, now: Date = new Date()): string {
  if (offset === 0) return 'Oggi';
  if (offset === 1) return 'Domani';
  if (offset === -1) return 'Ieri';
  const d = new Date(now);
  d.setDate(d.getDate() + offset);
  return `${d.toLocaleDateString('it-IT', { weekday: 'short' })} ${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** Partite di un giorno, per campionato: si sceglie il giorno, il campionato e si cerca una squadra. */
@Component({
  selector: 'ab-matches',
  imports: [MatchRow, LeagueLogo, FormsModule],
  templateUrl: './matches.html',
  styleUrl: './matches.scss',
})
export class Matches {
  protected readonly days = Array.from({ length: DAYS_BACK + DAYS_AHEAD + 1 }, (_, i) => i - DAYS_BACK).map((o) => ({ value: isoDay(o), label: dayName(o) }));
  protected readonly day = signal(isoDay());
  protected readonly competition = signal<string>(readSaved());
  protected readonly team = signal('');

  protected readonly competitions = httpResource<Competition[]>(() => '/api/competitions', { defaultValue: [] });
  protected readonly data = httpResource<CompetitionGroup[]>(
    () => `/api/matches?view=day&day=${this.day()}&limit=200${this.competition() ? `&competitions=${this.competition()}` : ''}`,
  );

  protected readonly groups = computed(() => {
    const q = this.team().trim().toLowerCase();
    return (this.data.value() ?? [])
      .map((g) => ({ ...g, matches: g.matches.filter((m) => !q || `${m.home.name} ${m.away.name}`.toLowerCase().includes(q)) }))
      .filter((g) => g.matches.length);
  });

  constructor() {
    effect(() => {
      try {
        localStorage.setItem(STORAGE_KEY, this.competition());
      } catch {
        // memoria del browser non disponibile: il filtro vale solo per questa visita
      }
    });
  }
}

function readSaved(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
}
