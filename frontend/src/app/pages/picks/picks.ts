import { httpResource } from '@angular/common/http';
import { Component, computed, inject, input, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Market, pickLabel } from '../../core/bets';
import { dayLabel, fairOdds, kickoffTime, odds, pct, signedPct } from '../../core/format';
import { MarketPick, Pick, PicksOut } from '../../core/picks';
import { Radar } from '../radar/radar';

type Tab = 'pronostici' | 'occasioni';

const SELECTIONS: Record<MarketPick['market'], string[]> = { '1X2': ['1', 'X', '2'], DC: ['1X', 'X2', '12'], 'OU2.5': ['over', 'under'] };
const MARKET_LABEL: Record<MarketPick['market'], string> = { '1X2': 'Esito finale', DC: 'Doppia chance', 'OU2.5': 'Under / Over 2.5' };

/** Pronostici (D67): la stima migliore per ogni partita, con le quote di Sisal ed Eurobet. Scheda "Occasioni" = radar. */
@Component({
  selector: 'ab-picks',
  imports: [RouterLink, Radar],
  templateUrl: './picks.html',
  styleUrl: './picks.scss',
})
export class Picks {
  /** Dall'indirizzo: ?tab=occasioni */
  readonly tabParam = input<string | undefined>(undefined, { alias: 'tab' });
  protected readonly tab = computed<Tab>(() => (this.tabParam() === 'occasioni' ? 'occasioni' : 'pronostici'));

  protected readonly data = httpResource<PicksOut>(() => (this.tab() === 'pronostici' ? '/api/picks' : undefined));
  protected readonly country = signal<string>('');
  protected readonly open = signal<number[]>([]);

  protected readonly countries = computed(() => [...new Set((this.data.value()?.picks ?? []).map((p) => p.match.competition.country))]);
  /** Partite filtrate e raggruppate per giorno */
  protected readonly days = computed(() => {
    const groups: { day: string; picks: Pick[] }[] = [];
    for (const p of this.data.value()?.picks ?? []) {
      if (this.country() && p.match.competition.country !== this.country()) continue;
      const day = dayLabel(p.match.kickoff_at);
      const last = groups.at(-1);
      if (last?.day === day) last.picks.push(p);
      else groups.push({ day, picks: [p] });
    }
    return groups;
  });

  protected readonly fmt = { kickoffTime, odds, fairOdds, pct, signedPct };
  protected readonly selections = SELECTIONS;
  protected readonly marketLabel = MARKET_LABEL;

  private readonly router = inject(Router);

  protected setTab(tab: Tab): void {
    this.router.navigate([], { queryParams: { tab: tab === 'occasioni' ? 'occasioni' : null } });
  }

  protected market(p: Pick, market: MarketPick['market']): MarketPick | undefined {
    return p.markets.find((m) => m.market === market);
  }

  protected label(p: Pick, market: string, selection: string): string {
    return pickLabel(market as Market, selection, p.match);
  }

  protected isOpen(id: number): boolean {
    return this.open().includes(id);
  }

  protected toggle(id: number): void {
    this.open.update((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }
}
