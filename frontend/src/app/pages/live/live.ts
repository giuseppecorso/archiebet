import { Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Market, MyPick, pickLabel } from '../../core/bets';
import { MatchCard, scorerList } from '../../core/football';
import { pct } from '../../core/format';
import { kickoffTime } from '../../core/format';
import { liveShort } from '../../core/live';
import { Crest } from '../../shared/crest';

/** Una partita nella lista di Partite: una riga con i marcatori; al clic la pagina della partita. */
@Component({
  selector: 'ab-diretta-row',
  imports: [Crest, RouterLink],
  template: `
    @let m = match();
    <a class="row" [class.is-live]="!!m.live" [routerLink]="['/partite', m.id]">
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
    </a>
    @if (scorers('home') || scorers('away')) {
      <a class="scorers" [routerLink]="['/partite', m.id]" tabindex="-1">
        <span class="s-home">{{ scorers('home') }}</span><span></span><span class="s-away">{{ scorers('away') }}</span>
      </a>
    }
    @for (p of mine(); track p.bet_id + p.market + p.pick) {
      <a class="mine" [attr.data-state]="p.state" [routerLink]="['/schedine', p.bet_id]">
        <span class="tag">{{ p.legs > 1 ? 'Multipla' : 'Singola' }}</span>
        <span>{{ label(p) }}</span>
        <strong>{{ stateText(p) }}</strong>
      </a>
    }
  `,
  styles: `
    .row {
      width: 100%; display: grid; grid-template-columns: 58px minmax(0, 1fr) 64px minmax(0, 1fr) 48px; align-items: center; gap: 8px;
      padding: 6px 12px; font: inherit; font-size: 13px; color: var(--text-2); text-align: left;
      background: transparent; border: 0; border-top: 1px solid var(--line-row); cursor: pointer; text-decoration: none;
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
    .scorers { text-decoration: none; display: grid; grid-template-columns: 58px minmax(0, 1fr) 64px minmax(0, 1fr) 48px; gap: 8px; padding: 0 12px 5px; margin-top: -3px; font-size: 11px; color: var(--muted); cursor: pointer; }
    .scorers .s-home { grid-column: 2; text-align: right; }
    .mine { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; margin: 0 12px 6px 78px; padding: 3px 8px; font-size: 12px; color: var(--text-2); text-decoration: none; border-left: 3px solid var(--line-strong); background: var(--bg-deep); border-radius: 3px; }
    .mine .tag { font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--amber); }
    .mine[data-state='winning'], .mine[data-state='won'] { border-left-color: var(--win); }
    .mine[data-state='winning'] strong, .mine[data-state='won'] strong { color: var(--win); }
    .mine[data-state='losing'], .mine[data-state='lost'] { border-left-color: var(--loss); }
    .mine[data-state='losing'] strong, .mine[data-state='lost'] strong { color: var(--loss); }
    .scorers .s-away { grid-column: 4; }
    @media (max-width: 560px) {
      .row { grid-template-columns: 44px minmax(0, 1fr) 48px minmax(0, 1fr); padding: 6px 8px; font-size: 12px; }
      .ht { display: none; }
      .mine { margin-left: 8px; margin-right: 8px; }
      .scorers { grid-template-columns: 44px minmax(0, 1fr) 48px minmax(0, 1fr); padding: 0 8px 5px; font-size: 10px; }
    }
  `,
})
export class DirettaRow {
  readonly match = input.required<MatchCard>();
  readonly tick = input(0);
  /** Le giocate aperte dell'utente su questa partita (D155) */
  readonly mine = input<MyPick[]>([]);
  protected readonly minute = liveShort;
  protected readonly winner = computed(() => {
    const m = this.match();
    if (m.status !== 'finished' || m.home_goals === m.away_goals) return null;
    return m.home_goals! > m.away_goals! ? 'home' : 'away';
  });

  protected label(p: MyPick): string {
    return pickLabel(p.market as Market, p.pick, this.match());
  }

  protected stateText(p: MyPick): string {
    const prob = p.probability != null && (p.state === 'winning' || p.state === 'losing') ? ` (${pct(p.probability)})` : '';
    return { waiting: 'da giocare', winning: 'sta vincendo', losing: 'sta perdendo', won: 'vinta', lost: 'persa', void: 'annullata', unknown: 'in corso' }[p.state] + prob;
  }

  protected scorers(side: 'home' | 'away'): string {
    return scorerList(this.match().highlights, side);
  }

  protected time(m: MatchCard): string {
    return kickoffTime(m.kickoff_at, m.kickoff_has_time);
  }
}
