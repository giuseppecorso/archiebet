import { httpResource } from '@angular/common/http';
import { Component, DestroyRef, computed, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Competition, CompetitionGroup, MatchCard } from '../../core/football';
import { LIVE_REFRESH_MS } from '../../core/live';
import { LeagueLogo } from '../../shared/crest';
import { DirettaRow } from '../live/live';

type Filter = 'tutte' | 'live' | 'finite' | 'programma';

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
  imports: [DirettaRow, LeagueLogo, FormsModule],
  templateUrl: './matches.html',
  styleUrl: './matches.scss',
})
export class Matches {
  protected readonly days = Array.from({ length: DAYS_BACK + DAYS_AHEAD + 1 }, (_, i) => i - DAYS_BACK).map((o) => ({ value: isoDay(o), label: dayName(o) }));
  protected readonly day = signal(isoDay());
  protected readonly competition = signal<string>(readSaved());
  protected readonly team = signal('');
  /** 'ora' = per campionato e orario; 'notizie' = prima le partite su cui il tifoso sa di più */
  protected readonly order = signal<'ora' | 'notizie'>('ora');
  /** Dall'indirizzo: ?stato=live (la vecchia Diretta) */
  readonly stato = input<string | undefined>(undefined);
  protected readonly filters: [Filter, string][] = [['tutte', 'Tutte'], ['live', 'In diretta'], ['finite', 'Finite'], ['programma', 'Da giocare']];
  protected readonly filter = signal<Filter>('tutte');
  /** Sale ogni 30 secondi: oggi ricarica punteggi e cronache aperte */
  protected readonly tick = signal(0);

  protected readonly competitions = httpResource<Competition[]>(() => '/api/competitions', { defaultValue: [] });
  protected readonly data = httpResource<CompetitionGroup[]>(
    () =>
      `/api/matches?view=day&day=${this.day()}&limit=200${this.competition() ? `&competitions=${this.competition()}` : ''}${this.day() === isoDay() ? `&t=${this.tick()}` : ''}`,
  );

  protected readonly liveCount = computed(() => (this.data.value() ?? []).reduce((n, g) => n + g.matches.filter((m) => !!m.live).length, 0));

  protected readonly groups = computed(() => {
    const q = this.team().trim().toLowerCase();
    return (this.data.value() ?? [])
      .map((g) => ({ ...g, matches: g.matches.filter((m) => this.keep(m) && (!q || `${m.home.name} ${m.away.name}`.toLowerCase().includes(q))) }))
      .filter((g) => g.matches.length);
  });

  /** Ordine "più notizie": tutte le partite con almeno una notizia, dalla più ricca */
  protected readonly byNews = computed(() =>
    this.groups()
      .flatMap((g) => g.matches)
      .filter((m) => (m.news ?? 0) > 0)
      .sort((a, b) => (b.news ?? 0) - (a.news ?? 0)),
  );

  private keep(m: MatchCard): boolean {
    switch (this.filter()) {
      case 'live':
        return !!m.live;
      case 'finite':
        return m.status === 'finished';
      case 'programma':
        return m.status === 'scheduled' && !m.live;
      default:
        return true;
    }
  }

  constructor() {
    const timer = setInterval(() => this.tick.update((n) => n + 1), LIVE_REFRESH_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
    effect(() => {
      if (this.stato() === 'live') this.filter.set('live');
    });
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
