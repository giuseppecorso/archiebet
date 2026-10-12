import { HttpClient, httpResource } from '@angular/common/http';
import { Component, effect, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { UserSettings } from '../../core/bets';
import { TeamListItem } from '../../core/lab';

/** Impostazioni personali: limiti (solo avvisi), bookmaker, squadra del cuore. */
@Component({
  selector: 'ab-settings',
  templateUrl: './settings.html',
  styleUrl: './settings.scss',
})
export class SettingsPage {
  private readonly http = inject(HttpClient);

  protected readonly current = httpResource<UserSettings>(() => '/api/settings');
  protected readonly teams = httpResource<TeamListItem[]>(() => '/api/lab/teams', { defaultValue: [] });

  protected readonly weekly = signal('');
  protected readonly monthly = signal('');
  protected readonly bookmakers = signal<string[]>([]);
  protected readonly favorite = signal<number | null>(null);
  protected readonly message = signal<{ ok: boolean; text: string } | null>(null);

  constructor() {
    // Riempie il modulo quando arrivano le impostazioni salvate
    effect(() => {
      const s = this.current.value();
      if (!s) return;
      this.weekly.set(s.weekly_budget ?? '');
      this.monthly.set(s.monthly_budget ?? '');
      this.bookmakers.set(s.bookmakers);
      this.favorite.set(s.favorite_team_id);
    });
  }

  protected toggleBookmaker(name: string): void {
    this.bookmakers.update((list) => (list.includes(name) ? list.filter((b) => b !== name) : [...list, name]));
  }

  private amount(text: string): string | null {
    const t = text.trim().replace(',', '.');
    return t === '' ? null : t;
  }

  protected async save(): Promise<void> {
    this.message.set(null);
    const body = {
      weekly_budget: this.amount(this.weekly()),
      monthly_budget: this.amount(this.monthly()),
      bookmakers: this.bookmakers(),
      favorite_team_id: this.favorite(),
    };
    try {
      await firstValueFrom(this.http.put<UserSettings>('/api/settings', body));
      this.current.reload();
      this.message.set({ ok: true, text: 'Impostazioni salvate.' });
    } catch {
      this.message.set({ ok: false, text: 'Non salvate: controlla che i limiti siano numeri (es. 50 o 50,00).' });
    }
  }
}
