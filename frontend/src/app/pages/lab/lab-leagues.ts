import { httpResource } from '@angular/common/http';
import { Component, computed, inject, input, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { num, pct } from '../../core/format';
import { CompetitionSeasons, SeasonDetail, SeasonTrend, seasonParam } from '../../core/lab';
import { ShowMore } from '../../shared/show-more';
import { LabTabs } from './lab-tabs';

/** Laboratorio · Campionati: numeri e classifica di un campionato in una stagione, e andamento negli anni. */
@Component({
  selector: 'ab-lab-leagues',
  imports: [LabTabs, RouterLink, ShowMore],
  templateUrl: './lab-leagues.html',
  styleUrl: './lab.scss',
})
export class LabLeagues {
  private readonly router = inject(Router);

  /** Dai parametri dell'indirizzo: ?c=ITA-C-C&s=2024-25 */
  readonly c = input<string>();
  readonly s = input<string>();

  protected readonly fmt = { num, pct };
  protected readonly trendOpen = signal(false);
  protected readonly tableOpen = signal(false);
  protected readonly catalog = httpResource<CompetitionSeasons[]>(() => '/api/lab/competitions', { defaultValue: [] });

  protected readonly current = computed(() => {
    const all = this.catalog.value();
    return all.find((x) => x.competition.code === this.c()) ?? all[0];
  });
  protected readonly season = computed(() => {
    const cur = this.current();
    if (!cur) return undefined;
    const wanted = this.s()?.replace('-', '/');
    return cur.seasons.find((x) => x.season === wanted)?.season ?? cur.seasons[0]?.season;
  });

  protected readonly detail = httpResource<SeasonDetail>(() => {
    const cur = this.current();
    const season = this.season();
    return cur && season ? `/api/lab/competitions/${cur.competition.code}/seasons/${seasonParam(season)}` : undefined;
  });
  protected readonly trend = httpResource<SeasonTrend[]>(() => {
    const cur = this.current();
    return cur ? `/api/lab/competitions/${cur.competition.code}/trend` : undefined;
  });
  protected readonly trendNewestFirst = computed(() => [...(this.trend.value() ?? [])].reverse());

  protected select(code: string, season?: string): void {
    void this.router.navigate([], { queryParams: { c: code, s: season ? seasonParam(season) : null } });
  }

  protected percent(value: number | null): number {
    return Math.round((value ?? 0) * 100);
  }
}
