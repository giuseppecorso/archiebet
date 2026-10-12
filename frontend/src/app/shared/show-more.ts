import { Component, input, model } from '@angular/core';

/**
 * Pulsante "Mostra tutte / Mostra meno" per tabelle ed elenchi lunghi.
 * Chi lo usa tiene un signal `expanded` (collegato con [(expanded)]) e mostra solo le prime righe finché è falso.
 */
@Component({
  selector: 'ab-show-more',
  template: `
    @if (total() > limit()) {
      <button type="button" class="more" [attr.aria-expanded]="expanded()" (click)="expanded.set(!expanded())">
        {{ expanded() ? 'Mostra meno' : 'Mostra tutte (' + total() + ')' }}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true" [class.up]="expanded()"><path d="M6 9l6 6 6-6"></path></svg>
      </button>
    }
  `,
  styles: `
    .more {
      display: inline-flex; align-items: center; gap: 6px; min-height: 36px; margin-top: 10px; padding: 4px 12px;
      font: inherit; font-size: 13px; font-weight: 600; color: var(--amber);
      background: transparent; border: 1px solid var(--line-strong); border-radius: 4px; cursor: pointer;
    }
    .more:hover { border-color: var(--amber); }
    svg { transition: transform 0.15s; }
    .up { transform: rotate(180deg); }
  `,
})
export class ShowMore {
  readonly total = input.required<number>();
  readonly limit = input.required<number>();
  readonly expanded = model(false);
}
