import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { BetCreated, BetKind, Market, preview } from './bets';
import { MatchCard } from './football';

/** Una partita nella schedina in costruzione: un solo esito per partita. */
export interface SlipLeg {
  match: Pick<MatchCard, 'id' | 'home' | 'away' | 'kickoff_at' | 'competition'>;
  market: Market;
  pick: string;
  odds: number;
  bookmaker: string | null;
}

const STORAGE_KEY = 'archiebet.slip';

function load(): SlipLeg[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const legs = raw ? (JSON.parse(raw) as SlipLeg[]) : [];
    // Le partite già iniziate non si possono più giocare
    return legs.filter((l) => new Date(l.match.kickoff_at).getTime() > Date.now());
  } catch {
    return [];
  }
}

/**
 * Schedina in costruzione (sempre visibile in basso a destra): si riempie con un clic sulle quote in Pronostici e nella
 * pagina partita, resta salvata nel browser finché non la registri o la svuoti.
 */
@Injectable({ providedIn: 'root' })
export class SlipService {
  private readonly http = inject(HttpClient);
  readonly legs = signal<SlipLeg[]>(load());
  readonly open = signal(false);
  readonly stake = signal('10');
  readonly kind = signal<BetKind>('simulated');

  readonly totalOdds = computed(() => this.legs().reduce((acc, l) => acc * l.odds, 1));
  readonly summary = computed(() => {
    const stake = Number(this.stake().replace(',', '.'));
    const legs = this.legs();
    const valid = legs.length > 0 && legs.every((l) => l.odds > 1) && stake > 0;
    return { valid, ...preview(valid ? legs.map((l) => l.odds) : [1], valid ? stake : 0) };
  });
  /** Il bookmaker della schedina: quello di tutte le quote scelte, se è lo stesso */
  readonly bookmaker = computed(() => {
    const names = new Set(this.legs().map((l) => l.bookmaker));
    return names.size === 1 ? [...names][0] : null;
  });

  has(matchId: number, market: Market, pick: string, bookmaker?: string | null): boolean {
    return this.legs().some((l) => l.match.id === matchId && l.market === market && l.pick === pick && (bookmaker === undefined || l.bookmaker === bookmaker));
  }

  /** Aggiunge l'esito (sostituisce quello già scelto per la stessa partita); se è già nella schedina lo toglie. */
  toggle(leg: SlipLeg): void {
    if (this.has(leg.match.id, leg.market, leg.pick, leg.bookmaker)) {
      this.remove(leg.match.id);
      return;
    }
    this.save([...this.legs().filter((l) => l.match.id !== leg.match.id), leg]);
  }

  remove(matchId: number): void {
    this.save(this.legs().filter((l) => l.match.id !== matchId));
  }

  setOdds(matchId: number, odds: number): void {
    this.save(this.legs().map((l) => (l.match.id === matchId ? { ...l, odds } : l)));
  }

  clear(): void {
    this.save([]);
  }

  /** Avvisi del regolamento personale (D114) per la schedina com'è adesso */
  async check(): Promise<string[]> {
    const draft = { stake: Number(this.stake().replace(',', '.')).toFixed(2), selections: this.selections(false) };
    return (await firstValueFrom(this.http.post<{ warnings: string[] }>('/api/rules/check', draft))).warnings;
  }

  /** Registra la schedina (reale o simulata) e la svuota */
  async register(): Promise<BetCreated> {
    const body = {
      kind: this.kind(),
      stake: Number(this.stake().replace(',', '.')).toFixed(2),
      bookmaker: this.bookmaker(),
      note: null,
      selections: this.selections(true),
    };
    const created = await firstValueFrom(this.http.post<BetCreated>('/api/bets', body));
    this.clear();
    return created;
  }

  private selections(asText: boolean) {
    return this.legs().map((l) => ({ match_id: l.match.id, market: l.market, pick: l.pick, odds: asText ? l.odds.toFixed(3) : l.odds }));
  }

  private save(legs: SlipLeg[]): void {
    this.legs.set(legs);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(legs));
    } catch {
      // senza memoria del browser la schedina vale solo per questa visita
    }
  }
}
