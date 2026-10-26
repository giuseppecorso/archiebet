import { Component, computed, input } from '@angular/core';
import { MatchEvent, eventMinute } from '../core/football';

const ICON: Record<string, string> = {
  goal: '⚽', penalty: '⚽', own_goal: '⚽', goal_cancelled: '⚽', missed_penalty: '✕', yellow: '▮', second_yellow: '▮▮', red: '▮', subst: '⇄', var: 'VAR',
};
const NOTE: Record<string, string> = { goal_cancelled: 'gol annullato dal VAR', penalty: 'rigore', own_goal: 'autogol', missed_penalty: 'rigore sbagliato', second_yellow: 'secondo giallo' };

/** Cronaca di una partita (D133), come su un sito di risultati: casa a sinistra, ospite a destra. */
@Component({
  selector: 'ab-match-events',
  template: `
    <ol class="events">
      @for (e of shown(); track $index) {
        <li [class]="'ev ' + e.side + ' k-' + e.kind">
          <span class="min">{{ minute(e) }}</span>
          <span class="icon" [attr.aria-label]="label(e)">{{ icon(e) }}</span>
          <span class="who">
            <strong>{{ e.player ?? '?' }}</strong>
            @if (e.kind === 'subst' && e.other) { <span class="muted"> ⇄ {{ e.other }}</span> }
            @else if (e.other && (e.kind === 'goal')) { <span class="muted"> (assist {{ e.other }})</span> }
            @if (note(e); as n) { <span class="muted"> · {{ n }}</span> }
            @if (e.kind === 'var' && e.detail) { <span class="muted"> · {{ e.detail }}</span> }
          </span>
        </li>
      } @empty {
        <li class="muted small none">Nessun evento ancora.</li>
      }
    </ol>
  `,
  styles: `
    .events { margin: 0; padding: 0; list-style: none; font-size: 12.5px; }
    .ev { display: grid; grid-template-columns: 44px 28px minmax(0, 1fr); align-items: baseline; gap: 6px; padding: 3px 0; border-bottom: 1px solid var(--line-row); }
    .ev.away { grid-template-columns: minmax(0, 1fr) 28px 44px; text-align: right; }
    .ev.away .min { order: 3; }
    .ev.away .icon { order: 2; }
    .ev.away .who { order: 1; }
    .min { font-variant-numeric: tabular-nums; color: var(--muted); }
    .icon { text-align: center; font-size: 12px; }
    .k-yellow .icon, .k-second_yellow .icon { color: #ffd400; }
    .k-red .icon { color: var(--loss); }
    .k-missed_penalty .icon { color: var(--loss); }
    .k-subst .icon { color: var(--sky); }
    .k-var .icon { font-size: 9px; font-weight: 700; color: var(--text-2); }
    .k-goal strong, .k-penalty strong, .k-own_goal strong { color: var(--text); }
    .k-goal_cancelled .icon { opacity: 0.4; }
    .k-goal_cancelled strong { text-decoration: line-through; color: var(--muted); }
    .who { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
    .none { padding: 4px 0; }
  `,
})
export class MatchEvents {
  readonly events = input.required<MatchEvent[]>();
  /** false = senza i cambi (cronaca corta) */
  readonly withSubs = input(true);
  protected readonly shown = computed(() => this.events().filter((e) => this.withSubs() || e.kind !== 'subst'));
  protected readonly minute = eventMinute;

  protected icon(e: MatchEvent): string {
    return ICON[e.kind] ?? '•';
  }

  protected note(e: MatchEvent): string | null {
    return NOTE[e.kind] ?? null;
  }

  protected label(e: MatchEvent): string {
    const names: Record<string, string> = { goal: 'Gol', goal_cancelled: 'Gol annullato', penalty: 'Gol su rigore', own_goal: 'Autogol', missed_penalty: 'Rigore sbagliato', yellow: 'Ammonizione', second_yellow: 'Espulsione per doppio giallo', red: 'Espulsione', subst: 'Cambio', var: 'VAR' };
    return names[e.kind] ?? e.kind;
  }
}
