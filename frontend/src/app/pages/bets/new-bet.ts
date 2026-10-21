import { HttpClient, HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { BetCreated, BetKind, MARKET_LABEL, Market, Prefill, UserSettings, euro, pickLabel, preview } from '../../core/bets';
import { CompetitionGroup, MatchCard } from '../../core/football';
import { dayLabel, kickoffTime, odds } from '../../core/format';

interface Row {
  match: MatchCard;
  market: Market;
  pick: string;
  odds: string; // testo scritto dall'utente, con virgola o punto
  prefill: Prefill['odds'];
}

const MARKETS: Record<Market, string[]> = {
  '1X2': ['1', 'X', '2'], DC: ['1X', 'X2', '12'], 'OU1.5': ['over', 'under'], 'OU2.5': ['over', 'under'], 'OU3.5': ['over', 'under'], GG: ['yes', 'no'],
};

/** "1,85" o "1.85" → 1.85 (NaN se non è un numero) */
export function parseDecimal(text: string): number {
  return Number(text.trim().replace(',', '.'));
}

@Component({
  selector: 'ab-new-bet',
  imports: [RouterLink],
  templateUrl: './new-bet.html',
  styleUrl: './new-bet.scss',
})
export class NewBet {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  /** ?m=123: partita da aggiungere subito (dal pulsante "Gioca questa partita") */
  readonly m = input<string>();

  protected readonly markets = MARKETS;
  protected readonly marketList = Object.keys(MARKETS) as Market[];
  protected readonly fmt = { odds, euro, dayLabel, kickoffTime, pickLabel, MARKET_LABEL };

  protected readonly upcoming = httpResource<CompetitionGroup[]>(() => '/api/matches?view=upcoming&limit=200', { defaultValue: [] });
  protected readonly settings = httpResource<UserSettings>(() => '/api/settings');

  protected readonly kind = signal<BetKind>('simulated');
  protected readonly rows = signal<Row[]>([]);
  protected readonly stake = signal('10');
  protected readonly bookmaker = signal('');
  protected readonly note = signal('');
  protected readonly search = signal('');
  protected readonly error = signal<string | null>(null);
  protected readonly busy = signal(false);

  protected readonly candidates = computed(() => {
    const chosen = new Set(this.rows().map((r) => r.match.id));
    const q = this.search().trim().toLowerCase();
    return this.upcoming
      .value()
      .flatMap((g) => g.matches)
      .filter((m) => m.status === 'scheduled' && !chosen.has(m.id))
      .filter((m) => !q || `${m.home.name} ${m.away.name} ${m.competition.name}`.toLowerCase().includes(q))
      .sort((a, b) => a.kickoff_at.localeCompare(b.kickoff_at));
  });

  /** Bookmaker: prima quelli scelti nelle impostazioni, poi gli altri */
  protected readonly bookmakers = computed(() => {
    const s = this.settings.value();
    if (!s) return [];
    return [...s.bookmakers, ...s.available_bookmakers.filter((b) => !s.bookmakers.includes(b))];
  });

  protected readonly summary = computed(() => {
    const values = this.rows().map((r) => parseDecimal(r.odds));
    const stake = parseDecimal(this.stake());
    const valid = values.length > 0 && values.every((v) => v > 1) && stake > 0;
    return { valid, ...preview(valid ? values : [1], valid ? stake : 0) };
  });

  constructor() {
    // Partita passata nell'indirizzo: la aggiungo appena l'elenco è caricato
    effect(() => {
      const wanted = Number(this.m());
      const match = this.upcoming.value().flatMap((g) => g.matches).find((x) => x.id === wanted);
      if (match && untracked(() => !this.rows().some((r) => r.match.id === wanted))) {
        untracked(() => void this.add(match));
      }
    });
  }

  protected async add(match: MatchCard): Promise<void> {
    this.search.set('');
    let prefill: Prefill['odds'] = {};
    try {
      prefill = (await firstValueFrom(this.http.get<Prefill>(`/api/matches/${match.id}/prefill`))).odds;
    } catch {
      // senza quote si scrive a mano
    }
    const row: Row = { match, market: '1X2', pick: '1', odds: '', prefill };
    row.odds = this.suggested(row);
    this.rows.update((rows) => [...rows, row]);
  }

  protected remove(index: number): void {
    this.rows.update((rows) => rows.filter((_, i) => i !== index));
  }

  protected setMarket(index: number, market: Market): void {
    this.update(index, (row) => {
      row.market = market;
      row.pick = MARKETS[market][0];
      row.odds = this.suggested(row);
    });
  }

  protected setPick(index: number, pick: string): void {
    this.update(index, (row) => {
      row.pick = pick;
      row.odds = this.suggested(row);
    });
  }

  protected setOdds(index: number, value: string): void {
    this.update(index, (row) => (row.odds = value));
  }

  /** Cambia una riga creando una copia (i signal si accorgono del cambiamento solo con oggetti nuovi) */
  private update(index: number, change: (row: Row) => void): void {
    this.rows.update((rows) =>
      rows.map((r, i) => {
        if (i !== index) return r;
        const copy = { ...r };
        change(copy);
        return copy;
      }),
    );
  }

  /** Quota media di mercato disponibile per quell'esito, come testo; vuota se non c'è */
  protected suggested(row: Row): string {
    const value = row.prefill[row.market]?.[row.pick];
    return value ? value.toFixed(2) : '';
  }

  /** Avvisi del regolamento personale (D114): la prima volta si mostrano, al secondo clic si registra comunque */
  protected readonly ruleWarnings = signal<string[]>([]);

  protected async submit(): Promise<void> {
    this.error.set(null);
    if (!this.summary().valid) {
      this.error.set('Controlla quote (maggiori di 1) e importo.');
      return;
    }
    this.busy.set(true);
    try {
      if (!this.ruleWarnings().length) {
        const draft = {
          stake: parseDecimal(this.stake()).toFixed(2),
          selections: this.rows().map((r) => ({ match_id: r.match.id, market: r.market, pick: r.pick, odds: parseDecimal(r.odds) })),
        };
        const check = await firstValueFrom(this.http.post<{ warnings: string[] }>('/api/rules/check', draft));
        if (check.warnings.length) {
          this.ruleWarnings.set(check.warnings);
          return;
        }
      }
      const body = {
        kind: this.kind(),
        stake: parseDecimal(this.stake()).toFixed(2),
        bookmaker: this.bookmaker() || null,
        note: this.note().trim() || null,
        selections: this.rows().map((r) => ({ match_id: r.match.id, market: r.market, pick: r.pick, odds: parseDecimal(r.odds).toFixed(3) })),
      };
      const created = await firstValueFrom(this.http.post<BetCreated>('/api/bets', body));
      await this.router.navigate(['/schedine', created.bet.id]);
    } catch (e) {
      const detail = e instanceof HttpErrorResponse ? e.error?.detail : null;
      this.error.set(typeof detail === 'string' ? detail : 'Non sono riuscito a registrare la giocata: controlla i dati.');
    } finally {
      this.busy.set(false);
    }
  }
}
