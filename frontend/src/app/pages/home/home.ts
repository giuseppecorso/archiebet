import { httpResource } from '@angular/common/http';
import { Component, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CompetitionGroup } from '../../core/football';
import { MatchRow } from '../../shared/match-row';

const ITALY_FIRST = ['ITA-A', 'ITA-B', 'ITA-C-A', 'ITA-C-B', 'ITA-C-C'];

/** Sotto il pallone (D190): solo le partite di oggi, con il pronostico più solido di Archie. */
@Component({
  selector: 'ab-home',
  imports: [RouterLink, MatchRow],
  templateUrl: './home.html',
  styleUrl: './home.scss',
})
export class Home {
  protected readonly upcoming = httpResource<CompetitionGroup[]>(() => '/api/matches?view=upcoming&limit=200', { defaultValue: [] });
  /** Il pronostico più solido di Archie per ogni partita di oggi */
  protected readonly headlines = httpResource<Record<number, { event: string; p_archie: number }>>(() => '/api/study/headlines?horizon=today', { defaultValue: {} });
  /** Partite di oggi, l'Italia in testa, al massimo 12 */
  protected readonly todayMatches = computed(() => {
    const picks = this.headlines.value();
    const end = new Date();
    end.setHours(24, 0, 0, 0);
    const groups = this.upcoming.value();
    const rank = (code: string) => (ITALY_FIRST.includes(code) ? ITALY_FIRST.indexOf(code) : 99);
    return groups
      .flatMap((g) => g.matches)
      .filter((m) => new Date(m.kickoff_at).getTime() < end.getTime())
      .filter((m) => !!m.odds_1x2 || !!picks[m.id]) // solo partite con le quote o con un pronostico di Archie
      .sort((a, b) => rank(a.competition.code) - rank(b.competition.code) || Number(!a.odds_1x2) - Number(!b.odds_1x2) || a.kickoff_at.localeCompare(b.kickoff_at))
      .slice(0, 12);
  });
}
