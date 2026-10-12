import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

/** Intestazione comune del Laboratorio con le schede. */
@Component({
  selector: 'ab-lab-tabs',
  imports: [RouterLink, RouterLinkActive],
  template: `
    <div class="head">
      <h1 class="title">Laboratorio</h1>
      <p class="muted">Studia il passato di campionati e squadre. Solo numeri calcolati sui risultati: niente pronostici.</p>
    </div>
    <nav class="tabs" aria-label="Schede del Laboratorio">
      <a class="tab title" routerLink="/laboratorio/campionati" routerLinkActive="on" ariaCurrentWhenActive="page">Campionati</a>
      <a class="tab title" routerLink="/laboratorio/squadre" routerLinkActive="on" ariaCurrentWhenActive="page">Squadre</a>
      <span class="tab title soon" title="Prova una regola sulle stagioni passate: arriva nella Fase 7">Strategie · Fase 7</span>
    </nav>
  `,
  styles: `
    .head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; margin-bottom: 12px; }
    h1 { margin: 0; font-size: 34px; color: var(--amber); }
    p { margin: 0; font-size: 14px; }
    .tabs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 20px; }
    .tab {
      display: inline-flex; align-items: center; min-height: 40px; padding: 6px 14px;
      font-size: 18px; color: var(--text); text-decoration: none;
      border: 1px solid var(--line-strong); border-radius: 4px;
    }
    .tab.on { color: var(--bg); background: var(--amber); border-color: var(--amber); }
    .tab.soon { color: var(--dim); border-style: dashed; }
  `,
})
export class LabTabs {}
