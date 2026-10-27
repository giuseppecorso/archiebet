import { httpResource } from '@angular/common/http';
import { Component, computed, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Market, pickLabel } from '../../core/bets';
import { dayLabel, fairOdds, kickoffTime, odds, pct, signedPct } from '../../core/format';
import { Occasion, RadarLive, RadarOut, RadarSignal, secondaryLabel } from '../../core/radar';

/** Occasioni: quote che pagano più del giusto, una carta per partita con lo studio accanto (D152). */
@Component({
  selector: 'ab-radar',
  imports: [RouterLink],
  templateUrl: './radar.html',
  styleUrl: './radar.scss',
})
export class Radar {
  /** true = scheda dentro la pagina Pronostici (senza titolo proprio) */
  readonly embedded = input(false);
  protected readonly radar = httpResource<RadarOut>(() => '/api/radar');
  protected readonly fmt = { dayLabel, kickoffTime, odds, fairOdds, pct, signedPct };

  /** Occasioni principali, una carta per partita: la migliore in grande (prima quelle su cui lo studio è d'accordo), le altre sotto */
  protected readonly cards = computed(() => {
    const byMatch = new Map<number, Occasion[]>();
    for (const o of this.radar.value()?.upcoming ?? []) {
      if (o.secondary) continue;
      byMatch.set(o.match_id, [...(byMatch.get(o.match_id) ?? []), o]);
    }
    return [...byMatch.values()]
      .map((list) => {
        const sorted = [...list].sort((a, b) => Number(this.agrees(b)) - Number(this.agrees(a)) || Number(a.suspicious) - Number(b.suspicious) || b.value - a.value);
        return { best: sorted[0], others: sorted.slice(1) };
      })
      .sort((a, b) => a.best.kickoff_at.localeCompare(b.best.kickoff_at));
  });
  /** Angoli e cartellini: in prova, in fondo */
  protected readonly secondary = computed(() => (this.radar.value()?.upcoming ?? []).filter((o) => o.secondary));
  private readonly opened = signal<number[]>([]);

  /** Lo studio ritiene l'esito probabile almeno quanto Pinnacle */
  protected agrees(o: Occasion): boolean {
    return o.p_study != null && o.p_study >= o.fair_probability;
  }

  protected isOpen(id: number): boolean {
    return this.opened().includes(id);
  }

  protected toggle(id: number): void {
    this.opened.update((list) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]));
  }

  /** Avanzamento verso le giocate necessarie per il giudizio (0-100) */
  protected readonly progress = computed(() => {
    const live = this.radar.value()?.live;
    return live ? Math.min(100, Math.round((live.n / live.target) * 100)) : 0;
  });

  protected pick(s: RadarSignal | Occasion): string {
    return secondaryLabel(s.market, s.selection, s.home.name, s.away.name) ?? pickLabel(s.market as Market, s.selection, s);
  }

  /** Avanzamento di una simulazione verso le giocate del giudizio (0-100) */
  protected progressOf(live: RadarLive | undefined): number {
    return live ? Math.min(100, Math.round((live.n / live.target) * 100)) : 0;
  }

  protected sign(value: number | null): 'pos' | 'neg' | '' {
    return value == null ? '' : value > 0 ? 'pos' : value < 0 ? 'neg' : '';
  }

  /** Percentuale senza segno con un decimale: 0.02 → "2,0%" */
  protected unsigned(value: number | null): string {
    return value == null ? '–' : signedPct(Math.abs(value)).replace('+', '');
  }
}
