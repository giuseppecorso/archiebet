import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { PRONOSTICI_TABS } from '../../core/sections';
import { Subnav } from '../../shared/subnav';

/** Intestazione comune del Laboratorio con le schede. */
@Component({
  selector: 'ab-lab-tabs',
  imports: [RouterLink, RouterLinkActive, Subnav],
  template: `
    <ab-subnav [items]="pronosticiTabs" label="Pronostici" />
    <div class="head">
      <h1 class="title">Statistiche</h1>
      <p class="muted">Il passato di campionati e squadre, e quello che Archie impara da solo. Solo numeri calcolati dal codice.</p>
    </div>
    <nav class="tabs" aria-label="Schede del Laboratorio">
      <a class="tab title" routerLink="/laboratorio/campionati" routerLinkActive="on" ariaCurrentWhenActive="page">Campionati</a>
      <a class="tab title" routerLink="/laboratorio/squadre" routerLinkActive="on" ariaCurrentWhenActive="page">Squadre</a>
      <a class="tab title" routerLink="/laboratorio/impara" routerLinkActive="on" ariaCurrentWhenActive="page">Cosa impara Archie</a>
    </nav>
  `,
  styles: `
    .head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; margin-bottom: 12px; }
    h1 { margin: 0; font-size: 28px; color: var(--amber); }
    p { margin: 0; font-size: 13px; }
    .tabs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 20px; }
    .tab {
      display: inline-flex; align-items: center; min-height: 40px; padding: 6px 14px;
      font-size: 16px; color: var(--text); text-decoration: none;
      border: 1px solid var(--line-strong); border-radius: 4px;
    }
    .tab.on { color: var(--bg); background: var(--amber); border-color: var(--amber); }
  `,
})
export class LabTabs {
  protected readonly pronosticiTabs = PRONOSTICI_TABS;
}
