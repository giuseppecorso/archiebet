import { httpResource } from '@angular/common/http';
import { Component, computed, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatchCard, MatchEvent, scorerList } from '../../core/football';
import { kickoffTime } from '../../core/format';
import { liveShort } from '../../core/live';
import { Crest } from '../../shared/crest';
import { MatchEvents } from '../../shared/match-events';

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
    @if (scorers('home') || scorers('away')) {
      <div class="scorers" (click)="open.set(!open())">
        <span class="s-home">{{ scorers('home') }}</span><span></span><span class="s-away">{{ scorers('away') }}</span>
      </div>
    }
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
    .scorers { display: grid; grid-template-columns: 58px minmax(0, 1fr) 64px minmax(0, 1fr) 48px; gap: 8px; padding: 0 12px 5px; margin-top: -3px; font-size: 11px; color: var(--muted); cursor: pointer; }
    .scorers .s-home { grid-column: 2; text-align: right; }
    .scorers .s-away { grid-column: 4; }
    .detail { padding: 6px 12px 10px 78px; background: var(--bg-deep); border-top: 1px solid var(--line-row); }
    .open { display: inline-block; margin-top: 6px; }
    @media (max-width: 560px) {
      .row { grid-template-columns: 44px minmax(0, 1fr) 48px minmax(0, 1fr); padding: 6px 8px; font-size: 12px; }
      .ht { display: none; }
      .scorers { grid-template-columns: 44px minmax(0, 1fr) 48px minmax(0, 1fr); padding: 0 8px 5px; font-size: 10px; }
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

  protected scorers(side: 'home' | 'away'): string {
    return scorerList(this.match().highlights, side);
  }

  protected time(m: MatchCard): string {
    return kickoffTime(m.kickoff_at, m.kickoff_has_time);
  }
}
