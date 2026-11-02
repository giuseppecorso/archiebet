import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { euro, pickLabel } from '../core/bets';
import { dayLabel, kickoffTime, odds } from '../core/format';
import { SlipService } from '../core/slip';

/** La schedina in costruzione, sempre visibile in basso a destra (chiusa: solo numero di partite e quota). */
@Component({
  selector: 'ab-slip-panel',
  imports: [FormsModule, RouterLink],
  templateUrl: './slip-panel.html',
  styleUrl: './slip-panel.scss',
})
export class SlipPanel {
  protected readonly slip = inject(SlipService);
  protected readonly fmt = { euro, odds, pickLabel, dayLabel, kickoffTime };
  protected readonly warnings = signal<string[]>([]);
  protected readonly error = signal<string | null>(null);
  protected readonly busy = signal(false);

  protected setOdds(matchId: number, text: string): void {
    const value = Number(text.replace(',', '.'));
    if (value > 1) this.slip.setOdds(matchId, value);
  }

  protected clear(): void {
    this.slip.clear();
    this.warnings.set([]);
  }

  /** Prima controlla il regolamento: gli avvisi si mostrano, al secondo clic si registra comunque (D114) */
  protected async register(): Promise<void> {
    this.error.set(null);
    if (!this.slip.summary().valid) {
      this.error.set('Controlla quote (maggiori di 1) e importo.');
      return;
    }
    this.busy.set(true);
    try {
      if (!this.warnings().length) {
        const found = await this.slip.check();
        if (found.length) {
          this.warnings.set(found);
          return;
        }
      }
      const created = await this.slip.register();
      this.warnings.set([]);
      this.slip.open.set(false);
      this.slip.notify(`Giocata registrata: ${created.bet.selections.length === 1 ? '1 partita' : created.bet.selections.length + ' partite'} a quota ${odds(+created.bet.total_odds)}. La trovi in Il mio Archie.`);
    } catch (e) {
      const detail = e instanceof HttpErrorResponse ? e.error?.detail : null;
      this.error.set(typeof detail === 'string' ? detail : 'Non sono riuscito a registrare la schedina.');
    } finally {
      this.busy.set(false);
    }
  }
}
