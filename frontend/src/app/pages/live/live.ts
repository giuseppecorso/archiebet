import { httpResource } from '@angular/common/http';
import { Component, DestroyRef, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CompetitionGroup, MatchCard } from '../../core/football';
import { odds, pct } from '../../core/format';
import { LIVE_REFRESH_MS } from '../../core/live';
import { PlanState } from '../../core/picks';
import { LeagueLogo } from '../../shared/crest';
import { MatchRow } from '../../shared/match-row';

/** Quote giuste di adesso per una partita in corso (D125) */
interface LiveNow extends Omit<PlanState, 'minute'> {
  status: string;
  minute: number | null;
}

const LABELS: Record<string, string> = {
  '1X2:1': '1', '1X2:X': 'X', '1X2:2': '2', 'OU2.5:over': 'Over 2.5', 'OU2.5:under': 'Under 2.5', 'GG:yes': 'Goal', 'GG:no': 'No goal',
};

/** Una partita in corso con le quote giuste e la quota minima da giocare adesso. */
@Component({
  selector: 'ab-live-card',
  imports: [MatchRow],
  template: `
    <article class="panel live-card">
      <ab-match-row [match]="match()" />
      @if (now.value(); as n) {
        <table class="lc-table">
          <thead><tr><th>Adesso</th><th>Probabilità</th><th>Quota giusta</th><th>Gioca da</th></tr></thead>
          <tbody>
            @for (l of n.lines; track l.market + l.selection) {
              <tr>
                <td>{{ labels[l.market + ':' + l.selection] }}</td>
                <td>{{ fmt.pct(l.probability) }}</td>
                <td>{{ fmt.odds(l.fair_odds) }}</td>
                <td>@if (l.min_odds) { <strong class="led">{{ fmt.odds(l.min_odds) }}</strong> } @else { <span class="muted small">no</span> }</td>
              </tr>
            }
          </tbody>
        </table>
      } @else if (!now.isLoading()) {
        <p class="muted small">Per questa partita mancano le probabilità prima del fischio: niente quote giuste live.</p>
      }
    </article>
  `,
  styles: `
    .live-card { padding: 8px 12px 12px; }
    .lc-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 6px; }
    .lc-table th, .lc-table td { padding: 4px 8px; text-align: left; border-bottom: 1px solid var(--line-row); }
    .lc-table th { color: var(--muted); font-weight: 500; }
  `,
})
export class LiveCard {
  readonly match = input.required<MatchCard>();
  readonly tick = input(0);
  protected readonly labels = LABELS;
  protected readonly fmt = { odds, pct };
  protected readonly now = httpResource<LiveNow | null>(() => `/api/picks/match/${this.match().id}/live-now?t=${this.tick()}`);
}

/** Live: partite in corso con le quote giuste del momento (D125, sperimentale). */
@Component({
  selector: 'ab-live',
  imports: [LiveCard, LeagueLogo, RouterLink],
  template: `
    <header class="hero">
      <h1>Live <span class="trial-tag" title="Stesso motore del termometro live, verificato all'intervallo sull'1X2 (D92); da provare in simulata">sperimentale</span></h1>
      <p>
        Le partite in corso, aggiornate ogni 30 secondi, con la <strong>quota minima da cui conviene giocare adesso</strong>:
        se sull'app del bookmaker la quota live è almeno quella, secondo Archie c'è valore. Le quote live hanno più margine:
        provalo prima in simulata.
      </p>
    </header>
    @for (group of live.value(); track group.competition.code) {
      <div class="group-head">
        <ab-league-logo [code]="group.competition.code" [size]="20" />
        <span class="title">{{ group.competition.name }}</span>
      </div>
      <div class="cards">
        @for (m of group.matches; track m.id) {
          <ab-live-card [match]="m" [tick]="tick()" />
        }
      </div>
    } @empty {
      <p class="panel empty">
        Nessuna partita in corso adesso. Minuto e punteggio arrivano da soli appena una partita comincia.
        Intanto guarda le <a routerLink="/partite">partite di oggi</a> o il piano partita live dentro ogni partita.
      </p>
    }
  `,
  styles: `
    .group-head { display: flex; align-items: center; gap: 8px; margin: 18px 0 8px; }
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }
    .empty { padding: 16px; color: var(--text-2); }
  `,
})
export class LivePage {
  /** Sale ogni 30 secondi: ricarica partite in corso e quote giuste */
  protected readonly tick = signal(0);
  protected readonly live = httpResource<CompetitionGroup[]>(() => `/api/matches?view=live&t=${this.tick()}`, { defaultValue: [] });

  constructor() {
    const timer = setInterval(() => this.tick.update((n) => n + 1), LIVE_REFRESH_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }
}
