import { Component, computed, inject, input } from '@angular/core';
import { Market } from '../core/bets';
import { MatchCard } from '../core/football';
import { odds, signedPct } from '../core/format';
import { Offer, verdictClass } from '../core/picks';
import { SlipService } from '../core/slip';

/** Quota di un bookmaker cliccabile: un clic la mette nella schedina (o la toglie). */
@Component({
  selector: 'ab-offer',
  template: `
    <button
      type="button"
      [class]="'v offer-btn ' + verdictClass(offer().verdict)"
      [class.in-slip]="inSlip()"
      [attr.aria-pressed]="inSlip()"
      [title]="(inSlip() ? 'Togli dalla schedina' : 'Aggiungi alla schedina') + ' · valore ' + signedPct(offer().value)"
      (click)="toggle()"
    >
      {{ inSlip() ? '✓' : '+' }} {{ offer().bookmaker }} {{ odds(offer().price) }}
    </button>
  `,
  styles: `
    .offer-btn {
      padding: 3px 8px; font: inherit; font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap;
      color: var(--text); background: var(--chip); border: 1px solid var(--line-strong); border-radius: 4px; cursor: pointer;
      transition: border-color 0.15s, background 0.15s;
    }
    .offer-btn:hover { border-color: var(--amber); background: #1d3a27; }
    .offer-btn.valore { color: var(--value); border-color: var(--value); background: rgba(57, 255, 116, 0.08); }
    .offer-btn.norma { color: var(--text-2); }
    .offer-btn.poco { color: var(--loss); border-color: var(--line-muted); }
    .offer-btn.archie { color: var(--sky); border-color: #2f5a7a; border-style: dashed; }
    .offer-btn.in-slip { color: var(--bg); background: var(--amber); border-color: var(--amber); }
  `,
})
export class OfferButton {
  private readonly slip = inject(SlipService);
  readonly match = input.required<Pick<MatchCard, 'id' | 'home' | 'away' | 'kickoff_at' | 'competition'>>();
  readonly market = input.required<Market>();
  readonly pick = input.required<string>();
  readonly offer = input.required<Offer>();

  protected readonly odds = odds;
  protected readonly signedPct = signedPct;
  protected readonly verdictClass = verdictClass;
  protected readonly inSlip = computed(() => this.slip.has(this.match().id, this.market(), this.pick(), this.offer().bookmaker));

  protected toggle(): void {
    const m = this.match();
    this.slip.toggle({
      match: { id: m.id, home: m.home, away: m.away, kickoff_at: m.kickoff_at, competition: m.competition },
      market: this.market(),
      pick: this.pick(),
      odds: this.offer().price,
      bookmaker: this.offer().bookmaker,
    });
    this.slip.open.set(true);
  }
}
