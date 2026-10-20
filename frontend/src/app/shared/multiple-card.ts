import { httpResource } from '@angular/common/http';
import { Component, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Horizon as MultipleHorizon, MultiplesOut } from '../core/multiple';
import { MultipleView } from './multiple-view';

type Horizon = Extract<MultipleHorizon, 'today' | 'week'>;

/** Multipla del giorno in dashboard (specifiche sezione 5, D68): una per bookmaker di Giuse, oggi o nella settimana. */
@Component({
  selector: 'ab-multiple-card',
  imports: [RouterLink, MultipleView],
  template: `
    <section class="panel card" aria-labelledby="mult-title">
      <div class="head">
        <h2 id="mult-title" class="title">Multipla del giorno</h2>
        <div class="seg" role="tablist" aria-label="Orizzonte">
          <button type="button" role="tab" [attr.aria-selected]="horizon() === 'today'" (click)="horizon.set('today')">Oggi</button>
          <button type="button" role="tab" [attr.aria-selected]="horizon() === 'week'" (click)="horizon.set('week')">Settimana</button>
        </div>
      </div>
      @if (data.value(); as d) {
        <ab-multiple-view [data]="d" [empty]="emptyText()" />
      } @else if (data.isLoading()) {
        <p class="muted small">Archie sta cercando la multipla…</p>
      }
      <a class="gen" [routerLink]="['/pronostici']" [queryParams]="{ tab: 'multipla' }">Archie, fammi una multipla →</a>
    </section>
  `,
  styles: `
    .card { padding: 16px 20px; }
    .head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
    h2 { margin: 0; font-size: 20px; color: var(--amber); }
    .seg { display: flex; border: 1px solid var(--line-strong); border-radius: 4px; overflow: hidden; }
    .seg button {
      min-height: 30px; padding: 2px 10px; font: inherit; font-size: 12px; font-weight: 600;
      color: var(--text-2); background: transparent; border: 0; cursor: pointer;
    }
    .seg button + button { border-left: 1px solid var(--line-strong); }
    .seg button[aria-selected='true'] { color: var(--bg); background: var(--text); }
    .gen { display: inline-block; margin-top: 12px; font-size: 13px; font-weight: 700; color: var(--amber); }
  `,
})
export class MultipleCard {
  protected readonly horizon = signal<Horizon>('today');
  protected readonly data = httpResource<MultiplesOut>(() => `/api/picks/multiple?horizon=${this.horizon()}`);

  protected emptyText(): string {
    return `${this.horizon() === 'today' ? 'Oggi' : 'Questa settimana'} non c'è una multipla sensata: servono 4 partite al 65% o più, `
      + 'con quote nella norma e quota totale tra 3 e 5. Meglio non giocare, o guardare le singole nei Pronostici.';
  }
}
