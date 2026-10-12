import { httpResource } from '@angular/common/http';
import { Component, computed, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { BetGroup, BetKind, BetSummary, Breakdown, BudgetStatus, SelectionGroup, SummaryOut, euro } from '../../core/bets';
import { num, pct } from '../../core/format';
import { ShowMore } from '../../shared/show-more';

type Period = SummaryOut['period'];
type Dim = 'by_size' | 'by_market' | 'by_competition' | 'by_bookmaker';

/** Le mie statistiche: riepilogo, dove vinci e dove perdi, abitudini. Reali e simulate sempre separate. */
@Component({
  selector: 'ab-stats',
  imports: [RouterLink, ShowMore],
  templateUrl: './stats.html',
  styleUrl: './stats.scss',
})
export class Stats {
  protected readonly periods: [Period, string][] = [
    ['week', 'Settimana'],
    ['30d', 'Ultimi 30 giorni'],
    ['season', 'Stagione'],
    ['all', 'Sempre'],
  ];
  protected readonly period = signal<Period>('all');
  protected readonly summary = httpResource<SummaryOut>(() => `/api/bets/summary?period=${this.period()}`);
  protected readonly budget = httpResource<BudgetStatus>(() => '/api/budget');

  /** Dove vinci e dove perdi */
  protected readonly dims: [Dim, string][] = [
    ['by_size', 'Numero di partite'],
    ['by_market', 'Mercato'],
    ['by_competition', 'Campionato'],
    ['by_bookmaker', 'Bookmaker'],
  ];
  protected readonly dim = signal<Dim>('by_size');
  protected readonly kind = signal<BetKind>('real');
  protected readonly groupsOpen = signal(false);
  protected readonly breakdown = httpResource<Breakdown>(() => `/api/bets/breakdown?kind=${this.kind()}&period=${this.period()}`);

  /** Numero di partite e bookmaker guardano la schedina intera; mercato e campionato le singole selezioni */
  protected readonly betRows = computed<BetGroup[] | null>(() => {
    const bd = this.breakdown.value();
    const d = this.dim();
    return bd && (d === 'by_size' || d === 'by_bookmaker') ? bd[d] : null;
  });
  protected readonly selectionRows = computed<SelectionGroup[] | null>(() => {
    const bd = this.breakdown.value();
    const d = this.dim();
    return bd && (d === 'by_market' || d === 'by_competition') ? bd[d] : null;
  });

  protected readonly fmt = { euro, pct, num };

  protected setDim(d: Dim): void {
    this.dim.set(d);
    this.groupsOpen.set(false);
  }

  protected sign(value: string | number | null): 'pos' | 'neg' | '' {
    const n = Number(value ?? 0);
    return n > 0 ? 'pos' : n < 0 ? 'neg' : '';
  }

  /** Rendimento e CLV come percentuali con segno: 0.1 → "+10,0%" */
  protected signedPct(value: number | null): string {
    if (value == null) return '–';
    const p = value * 100;
    return `${p > 0 ? '+' : p < 0 ? '−' : ''}${Math.abs(p).toLocaleString('it-IT', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
  }

  protected cards(s: SummaryOut): [string, string, BetSummary][] {
    return [
      ['Reali', 'Soldi veri', s.real],
      ['Simulate', 'Crediti finti, portafoglio separato', s.simulated],
    ];
  }
}
