import { Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatchCard, eventMinute, shortName } from '../core/football';
import { dayLabel, kickoffTime, odds } from '../core/format';
import { Crest } from './crest';
import { liveShort } from '../core/live';

/** Una riga dell'elenco partite, come nel mockup della dashboard. */
@Component({
  selector: 'ab-match-row',
  imports: [RouterLink, Crest],
  template: `
    @let m = match();
    <a class="row" [routerLink]="['/partite', m.id]" [attr.aria-label]="ariaLabel()">
      <div class="when">
        @if (m.live; as l) {
          <span class="label live-tag"><span class="pulse" aria-hidden="true"></span>LIVE</span>
          <span class="led time">{{ minute(l) }}</span>
        } @else {
          <span class="label">{{ day() }}</span>
          <span class="led time">{{ time() }}</span>
        }
      </div>

      <div class="teams">
        <div class="team">
          <ab-crest [team]="m.home" [size]="20" />
          <span class="name" [class.winner]="winner() === 'home'">{{ m.home.name }}@for (r of reds('home'); track $index) { <span class="red-card" title="Espulsione" aria-label="espulsione"></span> }</span>
          @if (m.live; as l) {
            <span class="led score live">{{ l.home_goals }}</span>
          } @else if (m.status === 'finished') {
            <span class="led score">{{ m.home_goals }}</span>
          }
        </div>
        <div class="team">
          <ab-crest [team]="m.away" [size]="20" />
          <span class="name" [class.winner]="winner() === 'away'">{{ m.away.name }}@for (r of reds('away'); track $index) { <span class="red-card" title="Espulsione" aria-label="espulsione"></span> }</span>
          @if (m.live; as l) {
            <span class="led score live">{{ l.away_goals }}</span>
          } @else if (m.status === 'finished') {
            <span class="led score">{{ m.away_goals }}</span>
          }
        </div>
      </div>

      @if (started()) {
        <div class="scorers" aria-label="Marcatori">
          <div class="line">{{ scorers('home') }}</div>
          <div class="line">{{ scorers('away') }}</div>
        </div>
      } @else {
        <div class="odds" [attr.aria-label]="oddsLabel()">
          @for (sel of selections; track sel) {
            <div class="odd" aria-hidden="true">
              <div class="sel">{{ sel }}</div>
              <div class="led price">{{ format(m.odds_1x2?.[sel]) }}</div>
            </div>
          }
        </div>
      }

      <div class="tag">
        @if (m.status === 'awaiting_result') {
          <span class="badge awaiting">Risultato in arrivo</span>
        } @else if (m.status === 'finished') {
          <span class="badge final">Finale</span>
          @if (m.ht_home_goals != null) { <span class="ht muted small">pt {{ m.ht_home_goals }}-{{ m.ht_away_goals }}</span> }
        }
      </div>
    </a>
  `,
  styleUrl: './match-row.scss',
})
export class MatchRow {
  protected readonly minute = liveShort;
  readonly match = input.required<MatchCard>();
  protected readonly selections = ['1', 'X', '2'] as const;
  protected readonly format = odds;

  /** In corso o finita: al posto delle quote, i marcatori (D133) */
  protected readonly started = computed(() => this.match().status === 'finished' || !!this.match().live);

  protected scorers(side: 'home' | 'away'): string {
    const notes: Record<string, string> = { penalty: ' (rig.)', own_goal: ' (aut.)' };
    return (this.match().highlights ?? [])
      .filter((e) => e.side === side && (e.kind === 'goal' || e.kind === 'penalty' || e.kind === 'own_goal'))
      .map((e) => `${shortName(e.player)} ${eventMinute(e)}${notes[e.kind] ?? ''}`)
      .join(', ');
  }

  protected reds(side: 'home' | 'away'): unknown[] {
    return (this.match().highlights ?? []).filter((e) => e.side === side && (e.kind === 'red' || e.kind === 'second_yellow'));
  }

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
