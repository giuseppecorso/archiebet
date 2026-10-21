import { httpResource } from '@angular/common/http';
import { Component, computed } from '@angular/core';
import { ago, num, pct, signedPct } from '../../core/format';
import { Est, LEAGUE_NAMES, Learning } from '../../core/lab';
import { LabTabs } from './lab-tabs';

/** Mesi della stagione, da agosto a giugno */
const SEASON_MONTHS = [8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6];
const MONTH_LABELS = ['', 'gen', 'feb', 'mar', 'apr', 'mag', 'giu', 'lug', 'ago', 'set', 'ott', 'nov', 'dic'];
const SELECTION_LABELS: Record<string, string> = { '1': '1', X: 'X', '2': '2', over: 'Over 2.5', under: 'Under 2.5' };

/** Laboratorio · Cosa impara Archie: le prove che Archie rifà da solo ogni settimana (Fase 7, D117-D121). */
@Component({
  selector: 'ab-lab-learning',
  imports: [LabTabs],
  templateUrl: './lab-learning.html',
  styleUrls: ['./lab.scss', './lab-learning.scss'],
})
export class LabLearning {
  protected readonly fmt = { ago, num, pct, signedPct };
  protected readonly months = SEASON_MONTHS;
  protected readonly monthLabels = MONTH_LABELS;
  protected readonly report = httpResource<Learning>(() => '/api/lab/learning');

  /** Mappa del valore: righe per campionato, colonne per mese (occasioni a stagione e CLV) */
  protected readonly valueMap = computed(() => {
    const vm = this.report.value()?.value_map;
    if (!vm) return [];
    const byLeague = new Map<string, Map<number, { per_season: number; clv: number }>>();
    for (const r of vm.rows) {
      if (!byLeague.has(r.league)) byLeague.set(r.league, new Map());
      byLeague.get(r.league)!.set(r.month, { per_season: r.per_season, clv: r.clv.mean });
    }
    return Object.keys(LEAGUE_NAMES)
      .filter((code) => byLeague.has(code))
      .map((code) => ({ code, name: LEAGUE_NAMES[code], cells: SEASON_MONTHS.map((m) => byLeague.get(code)!.get(m) ?? null) }));
  });
  protected readonly maxPerSeason = computed(() => Math.max(1, ...(this.report.value()?.value_map.rows.map((r) => r.per_season) ?? [1])));

  protected strategyName(s: { league: string; selection: string; band: [number, number]; moment: string; filter: string }): string {
    const band = s.band[1] >= 1000 ? `quota oltre ${num(s.band[0], 1)}` : `quota ${num(s.band[0], 1)}–${num(s.band[1], 1)}`;
    const league = s.league === 'tutti' ? 'tutti i campionati' : (LEAGUE_NAMES[s.league] ?? s.league);
    return `${SELECTION_LABELS[s.selection] ?? s.selection}, ${band}, ${league}, ${s.moment}, ${s.filter}`;
  }

  protected est(e: Est | null): string {
    if (!e) return '–';
    return e.se == null ? signedPct(e.mean) : `${signedPct(e.mean)} ± ${num(e.se * 100, 1)}`;
  }

  /** Intensità della cella (0-1) in base alle occasioni a stagione */
  protected heat(perSeason: number): number {
    return Math.min(1, perSeason / this.maxPerSeason());
  }
}
