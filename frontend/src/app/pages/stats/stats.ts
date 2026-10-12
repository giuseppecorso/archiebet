import { httpResource } from '@angular/common/http';
import { Component, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { BetSummary, BudgetStatus, SummaryOut, euro } from '../../core/bets';
import { pct } from '../../core/format';

type Period = SummaryOut['period'];

/** Le mie statistiche: riepilogo delle giocate, reali e simulate separate. */
@Component({
  selector: 'ab-stats',
  imports: [RouterLink],
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

  protected readonly fmt = { euro, pct };

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
