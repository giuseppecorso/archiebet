import { httpResource } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CompetitionGroup, MatchCard, MatchEvent } from '../../core/football';
import { kickoffTime } from '../../core/format';
import { LIVE_REFRESH_MS, liveShort } from '../../core/live';
import { Crest, LeagueLogo } from '../../shared/crest';
import { MatchEvents } from '../../shared/match-events';

type Filter = 'tutte' | 'live' | 'finite' | 'programma';

/** Giorno locale AAAA-MM-GG spostato di `offset` giorni da oggi */
function isoDay(offset = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Una partita della Diretta: una riga; al clic la cronaca (D133). */
@Component({
  selector: 'ab-diretta-row',
  imports: [Crest, MatchEvents, RouterLink],
  template: `
    @let m = match();
    <button type="button" class="row" [class.is-live]="!!m.live" [attr.aria-expanded]="open()" (click)="open.set(!open())">
      <span class="when">
        @if (m.live; as l) { <span class="live">{{ minute(l) }}</span> }
        @else if (m.status === 'finished') { <span class="muted">Finale</span> }
        @else if (m.status === 'awaiting_result') { <span class="muted">Fine?</span> }
        @else { {{ time(m) }} }
      </span>
      <span class="team home" [class.win]="winner() === 'home'">{{ m.home.name }} <ab-crest [team]="m.home" [size]="16" /></span>
      <span class="score" [class.live]="!!m.live">
        @if (m.live; as l) { {{ l.home_goals }} - {{ l.away_goals }} }
        @else if (m.status === 'finished') { {{ m.home_goals }} - {{ m.away_goals }} }
        @else { <span class="muted">-</span> }
      </span>
      <span class="team away" [class.win]="winner() === 'away'"><ab-crest [team]="m.away" [size]="16" /> {{ m.away.name }}</span>
      <span class="ht muted">
        @if (m.status === 'finished' && m.ht_home_goals != null) { ({{ m.ht_home_goals }}-{{ m.ht_away_goals }}) }
      </span>
    </button>
    @if (open()) {
      <div class="detail">
        @if (started()) {
          @if (events.value(); as list) { <ab-match-events [events]="list" /> }
          @else { <p class="muted small">Carico la cronaca…</p> }
        } @else {
          <p class="muted small">Non è ancora cominciata: la cronaca arriva in diretta, minuto per minuto.</p>
        }
        <a class="open small" [routerLink]="['/partite', m.id]">Apri la partita →</a>
      </div>
    }
  `,
  styles: `
    .row {
      width: 100%; display: grid; grid-template-columns: 58px minmax(0, 1fr) 64px minmax(0, 1fr) 48px; align-items: center; gap: 8px;
      padding: 6px 12px; font: inherit; font-size: 13px; color: var(--text-2); text-align: left;
      background: transparent; border: 0; border-top: 1px solid var(--line-row); cursor: pointer;
    }
    .row:hover { background: var(--panel-head); }
    .when { font-size: 12px; font-variant-numeric: tabular-nums; }
    .live { font-weight: 700; color: var(--loss); }
    .team { display: flex; align-items: center; gap: 6px; min-width: 0; overflow: hidden; white-space: nowrap; }
    .team.home { justify-content: flex-end; text-align: right; }
    .team.win { font-weight: 700; color: var(--text); }
    .score { text-align: center; font-weight: 700; font-size: 14px; color: var(--text); font-variant-numeric: tabular-nums; }
    .score.live { color: var(--loss); }
    .ht { font-size: 11px; text-align: right; }
    .detail { padding: 6px 12px 10px 78px; background: var(--bg-deep); border-top: 1px solid var(--line-row); }
    .open { display: inline-block; margin-top: 6px; }
    @media (max-width: 560px) {
      .row { grid-template-columns: 44px minmax(0, 1fr) 48px minmax(0, 1fr); padding: 6px 8px; font-size: 12px; }
      .ht { display: none; }
      .detail { padding-left: 8px; }
    }
  `,
})
export class DirettaRow {
  readonly match = input.required<MatchCard>();
  readonly tick = input(0);
  protected readonly open = signal(false);
  protected readonly minute = liveShort;
  protected readonly started = computed(() => this.match().status === 'finished' || !!this.match().live);
  protected readonly events = httpResource<MatchEvent[]>(() =>
    this.open() && this.started() ? `/api/matches/${this.match().id}/events?t=${this.match().live ? this.tick() : 0}` : undefined,
  );
  protected readonly winner = computed(() => {
    const m = this.match();
    if (m.status !== 'finished' || m.home_goals === m.away_goals) return null;
    return m.home_goals! > m.away_goals! ? 'home' : 'away';
  });

  protected time(m: MatchCard): string {
    return kickoffTime(m.kickoff_at, m.kickoff_has_time);
  }
}

/** Diretta (D133): risultati del giorno come su un sito di risultati, con cronaca. Niente giocate live. */
@Component({
  selector: 'ab-diretta',
  imports: [DirettaRow, LeagueLogo],
  template: `
    <header class="hero">
      <h1>Diretta</h1>
      <p>Risultati in tempo reale, marcatori e cronaca di tutti i campionati seguiti. Clicca una partita per vedere com'è andata.</p>
    </header>

    <div class="toolbar">
      <div class="chips" role="group" aria-label="Giorno">
        @for (d of days; track d[0]) {
          <button type="button" class="chip" [class.on]="day() === d[1]" [attr.aria-pressed]="day() === d[1]" (click)="day.set(d[1])">{{ d[0] }}</button>
        }
      </div>
      <div class="chips" role="group" aria-label="Filtro">
        @for (f of filters; track f[0]) {
          <button type="button" class="chip" [class.on]="filter() === f[0]" [attr.aria-pressed]="filter() === f[0]" (click)="filter.set(f[0])">
            {{ f[1] }}@if (f[0] === 'live' && liveCount()) { <span class="count">{{ liveCount() }}</span> }
          </button>
        }
      </div>
    </div>

    @for (g of groups(); track g.competition.code) {
      <section class="panel group" [attr.aria-label]="g.competition.name">
        <h2 class="group-head">
          <ab-league-logo [code]="g.competition.code" [size]="16" />
          <span class="country muted">{{ g.competition.country }}:</span> {{ g.competition.name }}
        </h2>
        @for (m of g.matches; track m.id) {
          <ab-diretta-row [match]="m" [tick]="tick()" />
        }
      </section>
    } @empty {
      @if (data.isLoading()) {
        <p class="muted small">Carico le partite…</p>
      } @else {
        <p class="panel empty">{{ emptyText() }}</p>
      }
    }
  `,
  styles: `
    .toolbar { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
    .chips { display: flex; flex-wrap: wrap; gap: 4px; }
    .chip { min-height: 28px; padding: 0 12px; font: inherit; font-size: 12px; font-weight: 600; color: var(--text-2); background: transparent; border: 1px solid var(--line-strong); border-radius: 14px; cursor: pointer; }
    .chip.on { color: var(--amber); background: var(--chip); border-color: var(--amber); }
    .count { margin-left: 6px; padding: 0 5px; font-size: 10px; color: #fff; background: var(--loss); border-radius: 8px; }
    .group { margin-bottom: 10px; overflow: hidden; }
    .group-head { display: flex; align-items: center; gap: 6px; margin: 0; padding: 6px 12px; font-size: 12px; font-weight: 700; background: var(--panel-head); }
    .country { font-weight: 600; text-transform: uppercase; font-size: 11px; }
    .empty { padding: 12px 14px; color: var(--text-2); }
  `,
})
export class DirettaPage {
  protected readonly days: [string, string][] = [['Ieri', isoDay(-1)], ['Oggi', isoDay()], ['Domani', isoDay(1)]];
  protected readonly filters: [Filter, string][] = [['tutte', 'Tutte'], ['live', 'In corso'], ['finite', 'Finite'], ['programma', 'Da giocare']];
  protected readonly day = signal(isoDay());
  protected readonly filter = signal<Filter>('tutte');
  /** Sale ogni 30 secondi: ricarica punteggi e cronache aperte */
  protected readonly tick = signal(0);
  protected readonly data = httpResource<CompetitionGroup[]>(
    () => `/api/matches?view=day&day=${this.day()}&limit=200${this.day() === isoDay() ? `&t=${this.tick()}` : ''}`,
    { defaultValue: [] },
  );

  protected readonly liveCount = computed(() => this.data.value().reduce((n, g) => n + g.matches.filter((m) => !!m.live).length, 0));
  protected readonly groups = computed(() => {
    const keep = (m: MatchCard): boolean => {
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
    };
    return this.data
      .value()
      .map((g) => ({ ...g, matches: g.matches.filter(keep) }))
      .filter((g) => g.matches.length > 0);
  });
  protected readonly emptyText = computed(() =>
    this.filter() === 'live' ? 'Nessuna partita in corso adesso: appena ne comincia una la vedi qui, minuto per minuto.' : 'Nessuna partita in questo giorno.',
  );

  constructor() {
    const timer = setInterval(() => this.tick.update((n) => n + 1), LIVE_REFRESH_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }
}
