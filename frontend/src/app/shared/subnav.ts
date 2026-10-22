import { Component, input } from '@angular/core';
import { IsActiveMatchOptions, RouterLink, RouterLinkActive } from '@angular/router';
import { SubItem } from '../core/sections';

const EXACT: IsActiveMatchOptions = { paths: 'exact', queryParams: 'exact', matrixParams: 'ignored', fragment: 'ignored' };
const SUBTREE: IsActiveMatchOptions = { paths: 'subset', queryParams: 'ignored', matrixParams: 'ignored', fragment: 'ignored' };

/** Schede interne di una voce del menu (es. Pronostici: Pronostici, Occasioni, Multipla, Statistiche, Simulatore). */
@Component({
  selector: 'ab-subnav',
  imports: [RouterLink, RouterLinkActive],
  template: `
    <nav class="subnav" [attr.aria-label]="label()">
      @for (item of items(); track item.label) {
        <a
          class="sub title"
          [routerLink]="item.link"
          [queryParams]="item.query ?? null"
          routerLinkActive="on"
          [routerLinkActiveOptions]="item.subtree ? subtree : exact"
          ariaCurrentWhenActive="page"
          >{{ item.label }}</a
        >
      }
    </nav>
  `,
  styles: `
    .subnav { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 16px; padding-bottom: 10px; border-bottom: 1px solid var(--line); }
    .sub {
      padding: 6px 14px; font-size: 17px; color: var(--text-2); text-decoration: none;
      border: 1px solid var(--line-strong); border-radius: 999px;
    }
    .sub:hover { color: var(--text); border-color: var(--amber); }
    .sub.on { color: var(--bg); background: var(--amber); border-color: var(--amber); }
    /* Telefono: una riga sola che scorre di lato */
    @media (max-width: 600px) {
      .subnav { flex-wrap: nowrap; overflow-x: auto; gap: 4px; margin: 0 -16px 10px 0; padding: 0 16px 8px 0; scrollbar-width: none; }
      .sub { flex: 0 0 auto; padding: 4px 11px; font-size: 14px; white-space: nowrap; }
    }
  `,
})
export class Subnav {
  readonly items = input.required<SubItem[]>();
  readonly label = input('Schede');
  protected readonly exact = EXACT;
  protected readonly subtree = SUBTREE;
}
