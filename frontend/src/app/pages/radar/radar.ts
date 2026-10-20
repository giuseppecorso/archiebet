import { httpResource } from '@angular/common/http';
import { Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Market, pickLabel } from '../../core/bets';
import { dayLabel, fairOdds, kickoffTime, odds, pct, signedPct } from '../../core/format';
import { Occasion, RadarLive, RadarOut, RadarSignal, secondaryLabel } from '../../core/radar';

/** Radar delle quote: dove un bookmaker italiano paga più della quota giusta, e come va la simulazione dal vivo. */
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
