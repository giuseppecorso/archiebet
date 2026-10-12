import { httpResource } from '@angular/common/http';
import { Component, computed, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatchCard } from '../../core/football';
import { TeamHistory, TeamListItem, seasonParam } from '../../core/lab';
import { MatchRow } from '../../shared/match-row';
import { LabTabs } from './lab-tabs';

/** Laboratorio · Squadre: ricerca, storia stagione per stagione, partite di una stagione. */
@Component({
  selector: 'ab-lab-teams',
  imports: [LabTabs, RouterLink, MatchRow],
  templateUrl: './lab-teams.html',
  styleUrl: './lab.scss',
})
export class LabTeams {
  /** Dalla rotta /laboratorio/squadre/:id */
  readonly id = input<string>();
  /** Stagione aperta, dall'indirizzo: ?s=2024-25 */
  readonly s = input<string>();

  protected readonly search = signal('');
  protected readonly teams = httpResource<TeamListItem[]>(() => '/api/lab/teams', { defaultValue: [] });
  protected readonly filtered = computed(() => {
    const q = this.search().trim().toLowerCase();
    return q ? this.teams.value().filter((t) => t.name.toLowerCase().includes(q)) : this.teams.value();
  });

  protected readonly history = httpResource<TeamHistory>(() => (this.id() ? `/api/lab/teams/${this.id()}` : undefined));
  protected readonly openSeason = computed(() => this.s()?.replace('-', '/') ?? this.history.value()?.seasons[0]?.season);
  protected readonly matches = httpResource<MatchCard[]>(() => {
    const season = this.openSeason();
    return this.id() && season ? `/api/lab/teams/${this.id()}/matches?season=${seasonParam(season)}` : undefined;
  });

  protected readonly seasonParam = seasonParam;

  /** Risultato della squadra in una partita, dal suo punto di vista (per riassumere la stagione) */
  protected readonly record = computed(() => {
    const id = Number(this.id());
    const games = (this.matches.value() ?? []).filter((m) => m.status === 'finished');
    const home = games.filter((m) => m.home.id === id);
    const away = games.filter((m) => m.away.id === id);
    const points = (list: MatchCard[], side: 'home' | 'away') =>
      list.reduce((sum, m) => {
        const mine = side === 'home' ? m.home_goals! : m.away_goals!;
        const theirs = side === 'home' ? m.away_goals! : m.home_goals!;
        return sum + (mine > theirs ? 3 : mine === theirs ? 1 : 0);
      }, 0);
    return { home: home.length, homePoints: points(home, 'home'), away: away.length, awayPoints: points(away, 'away') };
  });
}
