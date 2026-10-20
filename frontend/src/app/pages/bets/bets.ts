import { HttpClient, httpResource } from '@angular/common/http';
import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { Bet, BudgetStatus, KIND_LABEL, MARKET_LABEL, STATUS_LABEL, euro, pickLabel } from '../../core/bets';
import { dayLabel, kickoffTime, odds, pct } from '../../core/format';
import { LIVE_REFRESH_MS, liveLabel } from '../../core/live';
import { ShowMore } from '../../shared/show-more';

type StatusFilter = 'open' | 'closed' | 'all';
type KindFilter = 'all' | 'real' | 'simulated';

/** Le mie schedine: elenco a destra, dettaglio a sinistra (come nel mockup). */
@Component({
  selector: 'ab-bets',
  imports: [RouterLink, ShowMore],
  templateUrl: './bets.html',
  styleUrl: './bets.scss',
})
export class Bets {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  /** Dalla rotta /schedine/:id */
  readonly id = input<string>();

  protected readonly bets = httpResource<Bet[]>(() => '/api/bets', { defaultValue: [] });
  protected readonly budget = httpResource<BudgetStatus>(() => '/api/budget');
  protected readonly statusFilter = signal<StatusFilter>('open');
  protected readonly kindFilter = signal<KindFilter>('all');
  protected readonly listOpen = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly fmt = { euro, odds, dayLabel, kickoffTime, pickLabel, pct, liveLabel };
  /** "Segui live": la pagina si aggiorna da sola ogni 30 secondi (D92). Si accende da sola se una partita è in corso */
  protected readonly follow = signal(true);
  protected readonly anyLive = computed(() => this.bets.value().some((b) => b.live));

  constructor() {
    effect((onCleanup) => {
      if (!this.follow() || !this.anyLive()) return;
      const timer = setInterval(() => this.bets.reload(), LIVE_REFRESH_MS);
      onCleanup(() => clearInterval(timer));
    });
  }
  protected readonly labels = { KIND_LABEL, MARKET_LABEL, STATUS_LABEL };

  protected readonly filtered = computed(() =>
    this.bets.value().filter(
      (b) =>
        (this.statusFilter() === 'all' || (this.statusFilter() === 'open') === (b.status === 'open')) &&
        (this.kindFilter() === 'all' || b.kind === this.kindFilter()),
    ),
  );
  protected readonly counts = computed(() => {
    const all = this.bets.value();
    return { open: all.filter((b) => b.status === 'open').length, closed: all.filter((b) => b.status !== 'open').length, all: all.length };
  });

  protected readonly selected = computed(() => {
    const all = this.bets.value();
    return all.find((b) => b.id === Number(this.id())) ?? this.filtered()[0] ?? null;
  });

  protected title(bet: Bet): string {
    const n = bet.selections.length;
    return n === 1 ? 'Singola' : `Multipla ${n}`;
  }

  /** Si può cancellare (per correggere un errore) finché è aperta e nessuna partita è iniziata */
  protected canDelete(bet: Bet): boolean {
    const now = Date.now();
    return bet.status === 'open' && bet.selections.every((s) => new Date(s.match.kickoff_at).getTime() > now);
  }

  protected async remove(bet: Bet): Promise<void> {
    if (!confirm('Cancellare questa schedina? Serve solo a correggere un errore di inserimento.')) return;
    try {
      await firstValueFrom(this.http.delete(`/api/bets/${bet.id}`));
      this.bets.reload();
      this.budget.reload();
      await this.router.navigate(['/schedine']);
    } catch {
      this.error.set('Non sono riuscito a cancellarla: forse una partita è già iniziata.');
    }
  }

  protected clvClass(clv: string | null): string {
    if (clv == null) return '';
    return Number(clv) > 0 ? 'pos' : Number(clv) < 0 ? 'neg' : '';
  }

  protected clvText(clv: string | null): string {
    if (clv == null) return '–';
    const pct = Number(clv) * 100;
    return `${pct > 0 ? '+' : pct < 0 ? '−' : ''}${Math.abs(pct).toLocaleString('it-IT', { maximumFractionDigits: 1 })}%`;
  }
}
