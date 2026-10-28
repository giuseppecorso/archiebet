import { HttpClient, HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { dayLabel } from '../core/format';

interface CoinsOut {
  balance: number;
  earned: number;
  spent: number;
  month_cost: number;
  counted_per_day: number;
  trial_days: number;
  premium_until: string;
  premium_active: boolean;
  subscriptions_enabled: boolean;
  recent: { bet_id: number; coins: number; placed_at: string }[];
}

/** ArchieCoins (D159): saldo, come si guadagnano, riscatto di un mese di Premium. */
@Component({
  selector: 'ab-coins-card',
  template: `
    @if (data.value(); as c) {
      <section class="panel box coins" aria-labelledby="coins-title">
        <div class="head">
          <h2 id="coins-title" class="title box-title">ArchieCoins</h2>
          <span class="led balance">{{ c.balance.toLocaleString('it-IT') }} <span aria-hidden="true">🪙</span></span>
        </div>
        <p class="muted small">
          Ogni giocata vinta vale <strong>10 monete × la quota</strong> (a quota 2,50 sono 25), qualunque sia la puntata:
          conta prevedere bene, non puntare tanto. Valgono le prime {{ c.counted_per_day }} giocate di ogni giorno.
        </p>
        <div class="redeem">
          <span>
            @if (c.subscriptions_enabled) {
              Premium {{ c.premium_active ? 'attivo fino a ' + day(c.premium_until).toLowerCase() : 'scaduto' }}
            } @else {
              Per ora tutte le funzioni sono gratis per tutti
            }
            · {{ c.month_cost.toLocaleString('it-IT') }} monete = 1 mese di Premium
          </span>
          <button type="button" class="btn-primary" [disabled]="c.balance < c.month_cost || busy()" (click)="redeem()">Riscatta un mese</button>
        </div>
        @if (msg(); as m) {
          <p class="small" [class.err]="!m.ok">{{ m.text }}</p>
        }
      </section>
    }
  `,
  styles: `
    .coins { margin-bottom: 12px; }
    .head { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }
    .balance { font-size: 26px; }
    .redeem { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 14px; font-size: 13px; }
    .redeem button { min-height: 34px; padding: 4px 14px; }
    .err { color: var(--loss); }
  `,
})
export class CoinsCard {
  private readonly http = inject(HttpClient);
  protected readonly data = httpResource<CoinsOut>(() => '/api/coins');
  protected readonly busy = signal(false);
  protected readonly msg = signal<{ ok: boolean; text: string } | null>(null);
  protected readonly day = dayLabel;

  protected async redeem(): Promise<void> {
    this.busy.set(true);
    try {
      const out = await firstValueFrom(this.http.post<CoinsOut>('/api/coins/redeem', {}));
      this.data.set(out);
      this.msg.set({ ok: true, text: `Fatto: Premium fino a ${dayLabel(out.premium_until).toLowerCase()}.` });
    } catch (e) {
      this.msg.set({ ok: false, text: e instanceof HttpErrorResponse && typeof e.error?.detail === 'string' ? e.error.detail : 'Riscatto non riuscito.' });
    } finally {
      this.busy.set(false);
    }
  }
}
