import { HttpClient, HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { MatchCard } from '../../core/football';
import { dayLabel, kickoffTime, num, odds, pct } from '../../core/format';
import { Crest } from '../../shared/crest';

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

interface ChallengeRow {
  match: MatchCard;
  probabilities: Record<string, number> | null;
  fair_odds: Record<string, number> | null;
  my_pick: string | null;
  archie_pick: string | null;
  open: boolean;
  credits: number | null;
}

interface ChallengeOut {
  stake: number;
  rows: ChallengeRow[];
  standings: { name: string; picks: number; correct: number; hit_rate: number | null; credits: number }[];
}

/** Punteggio della partita "dal vivo" al minuto indicato, dai gol simulati */
export function liveScore(sim: Pick<Simulation, 'score' | 'sample'>, minute: number): [number, number] {
  const goals = sim.sample.filter((g) => g.minute <= minute);
  return [sim.score[0] + goals.filter((g) => g.side === 'home').length, sim.score[1] + goals.filter((g) => g.side === 'away').length];
}

const COMPETITIONS = [
  ['ITA-A', 'Serie A'], ['ITA-B', 'Serie B'], ['ITA-C-A', 'Serie C · A'], ['ITA-C-B', 'Serie C · B'], ['ITA-C-C', 'Serie C · C'],
  ['ENG-1', 'Premier League'], ['ESP-1', 'LaLiga'], ['GER-1', 'Bundesliga'], ['FRA-1', 'Ligue 1'],
];

@Component({
  selector: 'ab-play',
  imports: [FormsModule, Crest],
  templateUrl: './play.html',
  styleUrl: './play.scss',
})
export class Play implements OnDestroy {
  protected readonly tab = signal<'sim' | 'sfida'>('sim');
  protected readonly fmt = { odds, num, pct, dayLabel, kickoffTime };
  protected readonly competitions = COMPETITIONS;
  private readonly http = inject(HttpClient);

  // --- Simulatore ---
  protected readonly matches = httpResource<MatchCard[]>(() => '/api/play/matches', { defaultValue: [] });
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

  // --- Sfida contro Archie ---
  protected readonly competition = signal('ITA-A');
  protected readonly challenge = httpResource<ChallengeOut>(() => `/api/play/challenge?competition=${this.competition()}`);
  protected readonly pickError = signal<string | null>(null);

  protected async pick(row: ChallengeRow, selection: string): Promise<void> {
    this.pickError.set(null);
    try {
      await firstValueFrom(this.http.post('/api/play/challenge', { match_id: row.match.id, selection }));
      this.challenge.reload();
    } catch (e) {
      const detail = e instanceof HttpErrorResponse ? e.error?.detail : null;
      this.pickError.set(typeof detail === 'string' ? detail : 'Scelta non salvata.');
    }
  }
}
