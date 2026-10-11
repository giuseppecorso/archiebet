import { Component, computed, input } from '@angular/core';
import { OUTCOME_LABEL, Outcome } from '../core/football';

/** Ultimi risultati come quadratini: V verde, N ambra, P rosso. La lettera c'è sempre (il colore non è l'unico segnale). */
@Component({
  selector: 'ab-form-badges',
  template: `
    <div class="badges" role="img" [attr.aria-label]="label()">
      @for (o of outcomes(); track $index) {
        <span [class]="'b ' + o" aria-hidden="true">{{ o }}</span>
      } @empty {
        <span class="none">nessuna partita</span>
      }
    </div>
  `,
  styles: `
    .badges { display: flex; gap: 4px; }
    .b {
      width: var(--size, 26px); height: var(--size, 26px);
      display: flex; align-items: center; justify-content: center;
      font-weight: 700; font-size: 13px; color: var(--bg); border-radius: 3px;
    }
    .V { background: var(--value); box-shadow: 0 0 6px rgb(61 255 110 / 45%); }
    .N { background: var(--amber); }
    .P { background: var(--loss); }
    .none { font-size: 12px; color: var(--muted); }
  `,
})
export class FormBadges {
  readonly outcomes = input.required<Outcome[]>();
  readonly team = input('');
  protected readonly label = computed(() => {
    const words = this.outcomes().map((o) => OUTCOME_LABEL[o]).join(', ');
    return `Ultimi risultati ${this.team()}, dal più recente: ${words || 'nessuno'}`;
  });
}
