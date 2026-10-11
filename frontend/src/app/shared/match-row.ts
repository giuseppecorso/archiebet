import { Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatchCard } from '../core/football';
import { dayLabel, kickoffTime, odds } from '../core/format';

/** Una riga dell'elenco partite, come nel mockup della dashboard. */
@Component({
  selector: 'ab-match-row',
  imports: [RouterLink],
  template: `
    @let m = match();
    <a class="row" [routerLink]="['/partite', m.id]" [attr.aria-label]="ariaLabel()">
      <div class="when">
        <span class="label">{{ day() }}</span>
        <span class="led time">{{ time() }}</span>
      </div>

      <div class="teams">
        <div class="team">
          <span class="name" [class.winner]="winner() === 'home'">{{ m.home.name }}</span>
          @if (m.status === 'finished') {
            <span class="led score">{{ m.home_goals }}</span>
          }
        </div>
        <div class="team">
          <span class="name" [class.winner]="winner() === 'away'">{{ m.away.name }}</span>
          @if (m.status === 'finished') {
            <span class="led score">{{ m.away_goals }}</span>
          }
        </div>
      </div>

      <div class="odds" [attr.aria-label]="oddsLabel()">
        @for (sel of selections; track sel) {
          <div class="odd" aria-hidden="true">
            <div class="sel">{{ sel }}</div>
            <div class="led price">{{ format(m.odds_1x2?.[sel]) }}</div>
          </div>
        }
      </div>

      <div class="tag">
        @if (m.status === 'awaiting_result') {
          <span class="badge awaiting">Risultato in arrivo</span>
        } @else if (m.status === 'finished') {
          <span class="badge final">Finale</span>
        }
      </div>
    </a>
  `,
  styleUrl: './match-row.scss',
})
export class MatchRow {
  readonly match = input.required<MatchCard>();
  protected readonly selections = ['1', 'X', '2'] as const;
  protected readonly format = odds;

  protected readonly day = computed(() => dayLabel(this.match().kickoff_at));
  protected readonly time = computed(() => kickoffTime(this.match().kickoff_at, this.match().kickoff_has_time));
  protected readonly winner = computed(() => {
    const m = this.match();
    if (m.status !== 'finished' || m.home_goals === m.away_goals) return null;
    return m.home_goals! > m.away_goals! ? 'home' : 'away';
  });
  protected readonly ariaLabel = computed(() => {
    const m = this.match();
    const score = m.status === 'finished' ? `, finita ${m.home_goals} a ${m.away_goals}` : '';
    return `${m.home.name} contro ${m.away.name}, ${this.day()} ${this.time()}${score}. Apri la partita`;
  });
  protected readonly oddsLabel = computed(() => {
    const o = this.match().odds_1x2;
    return o ? `Quote medie: 1 ${odds(o['1'])}, X ${odds(o.X)}, 2 ${odds(o['2'])}` : 'Quote non disponibili';
  });
}
