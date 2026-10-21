import { HttpClient, HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { MatchCard } from '../../core/football';
import { dayLabel, kickoffTime, num, odds, pct } from '../../core/format';
import { Crest } from '../../shared/crest';
import { Subnav } from '../../shared/subnav';
import { PRONOSTICI_TABS } from '../../core/sections';

/** Risposta di /api/play/simulate (D115) */
export interface Simulation {
  match: MatchCard;
  n: number;
  minute: number;
  score: [number, number];
  rates: [number, number];
  remaining: [number, number];
  p_home: number;
  p_draw: number;
  p_away: number;
  p_over25: number;
  p_gg: number;
  avg_goals: [number, number];
  top_scores: [number, number, number][];
  sample: { minute: number; side: 'home' | 'away' }[];
}



/** Punteggio della partita "dal vivo" al minuto indicato, dai gol simulati */
export function liveScore(sim: Pick<Simulation, 'score' | 'sample'>, minute: number): [number, number] {
  const goals = sim.sample.filter((g) => g.minute <= minute);
  return [sim.score[0] + goals.filter((g) => g.side === 'home').length, sim.score[1] + goals.filter((g) => g.side === 'away').length];
}


@Component({
  selector: 'ab-play',
  imports: [FormsModule, Crest, Subnav],
  templateUrl: './play.html',
  styleUrl: './play.scss',
})
export class Play implements OnDestroy {
  protected readonly tabs = PRONOSTICI_TABS;
  protected readonly fmt = { odds, num, pct, dayLabel, kickoffTime };
  private readonly http = inject(HttpClient);

  // --- Simulatore ---
  protected readonly matches = httpResource<MatchCard[]>(() => '/api/play/matches', { defaultValue: [] });
  /** Partite raggruppate per campionato, nell'ordine in cui arrivano (per data) */
  protected readonly matchGroups = computed(() => {
    const groups = new Map<string, MatchCard[]>();
    for (const m of this.matches.value()) groups.set(m.competition.name, [...(groups.get(m.competition.name) ?? []), m]);
    return [...groups].map(([name, matches]) => ({ name, matches }));
  });
  protected matchId: number | null = null;
  protected whatIfMinute = 0;
  protected whatIfHome = 0;
  protected whatIfAway = 0;
  protected readonly sim = signal<Simulation | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly clock = signal<number | null>(null); // minuto della partita "dal vivo"
  private timer: ReturnType<typeof setInterval> | null = null;
  protected readonly board = computed<[number, number] | null>(() => {
    const s = this.sim();
    const m = this.clock();
    return s && m != null ? liveScore(s, m) : null;
  });

  protected async simulate(minute = 0, home = 0, away = 0): Promise<void> {
    if (!this.matchId) return;
    this.stopLive();
    this.busy.set(true);
    this.error.set(null);
    try {
      const url = `/api/play/simulate?match_id=${this.matchId}&minute=${minute}&home=${home}&away=${away}`;
      this.sim.set(await firstValueFrom(this.http.get<Simulation>(url)));
    } catch (e) {
      const detail = e instanceof HttpErrorResponse ? e.error?.detail : null;
      this.error.set(typeof detail === 'string' ? detail : 'Simulazione non riuscita.');
    } finally {
      this.busy.set(false);
    }
  }

  protected whatIf(): Promise<void> {
    return this.simulate(Math.max(0, Math.min(90, +this.whatIfMinute || 0)), Math.max(0, +this.whatIfHome || 0), Math.max(0, +this.whatIfAway || 0));
  }

  /** Una partita simulata minuto per minuto sul tabellone: circa 20 secondi */
  protected playLive(): void {
    const s = this.sim();
    if (!s) return;
    this.stopLive();
    this.clock.set(s.minute);
    this.timer = setInterval(() => {
      const next = (this.clock() ?? 0) + 1;
      this.clock.set(Math.min(next, 90));
      if (next >= 90) this.stopLive(false);
    }, 220);
  }

  protected stopLive(reset = true): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    if (reset) this.clock.set(null);
  }

  protected goalsUpTo(minute: number): { minute: number; side: string }[] {
    return (this.sim()?.sample ?? []).filter((g) => g.minute <= minute);
  }

  ngOnDestroy(): void {
    this.stopLive();
  }

}
