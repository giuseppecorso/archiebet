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
    .offer-btn { font: inherit; cursor: pointer; border: 1px solid transparent; }
    .offer-btn:hover { border-color: var(--amber); }
    .offer-btn.in-slip { outline: 2px solid var(--amber); outline-offset: 1px; }
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
